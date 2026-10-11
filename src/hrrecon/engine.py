"""Motor de conciliación: empareja empleados y cuentas, aplica exclusiones y reglas."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import Config
from .evidence import sha256_file
from .models import SEVERITY_ORDER, Account, Dataset, Employee, Exclusion, InputFile, Result
from .normalize import is_dn, normalize_account, normalize_id, normalize_text

# Estados efectivos de un empleado a la fecha de corte.
ACTIVE = "active"
TERMINATED = "terminated"
SCHEDULED_TERMINATION = "scheduled_termination"
SCHEDULED_HIRE = "scheduled_hire"
UNKNOWN = "unknown"
NO_ID = "no_id"


@dataclass
class Context:
    cfg: Config
    data: Dataset
    as_of: date
    primary: dict[str, Employee] = field(default_factory=dict)  # id_key -> empleado principal
    rows_by_id: dict[str, list[Employee]] = field(default_factory=dict)
    accounts_of: dict[int, list[Account]] = field(default_factory=dict)  # fila empleado -> cuentas
    match_method: dict[int, str] = field(default_factory=dict)  # fila cuenta -> 'id' | 'email'
    owner_of: dict[int, Employee] = field(default_factory=dict)  # fila cuenta -> empleado
    excluded_accounts: set[int] = field(default_factory=set)
    excluded_employees: set[int] = field(default_factory=set)
    exclusions: list[Exclusion] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    # ---------- utilidades para las reglas ----------
    def state(self, e: Employee) -> str:
        if not e.id_key:
            return NO_ID
        term = e.termination_date
        if e.status == "terminated":
            if term and term > self.as_of:
                return SCHEDULED_TERMINATION
            return TERMINATED
        if e.status == "active":
            if term and term <= self.as_of:
                return TERMINATED  # estado y fecha inconsistentes: prevalece la fecha
            if e.hire_date and e.hire_date > self.as_of:
                return SCHEDULED_HIRE
            return ACTIVE
        return UNKNOWN

    def subjects(self):
        """Empleados principales que participan en las reglas (sin excluidos)."""
        for e in self.primary.values():
            if e.row not in self.excluded_employees:
                yield e

    def accounts(self, e: Employee) -> list[Account]:
        return self.accounts_of.get(e.row, [])

    def unassigned_accounts(self) -> list[Account]:
        return [
            a
            for a in self.data.accounts
            if a.row not in self.owner_of and a.row not in self.excluded_accounts
        ]

    def active_accounts(self) -> list[Account]:
        return [a for a in self.data.accounts if a.row not in self.excluded_accounts]

    def text_equal(self, a: str, b: str) -> bool:
        opts = self.cfg.text_options
        return normalize_text(a, opts) == normalize_text(b, opts)

    def is_title_without_account(self, e: Employee) -> bool:
        titles = self.cfg.exclusions.titles_no_account_required
        title = normalize_text(e.raw.get("title", ""), self.cfg.text_options)
        return bool(title) and title in {normalize_text(t, self.cfg.text_options) for t in titles}

    # ---------- resolución del jefe en el directorio ----------
    def build_manager_index(self) -> None:
        self._by_account = {a.account_key: a for a in self.active_accounts()}
        by_name: dict[str, list[Account]] = defaultdict(list)
        for a in self.active_accounts():
            if a.display_name:
                by_name[normalize_text(a.display_name)].append(a)
        self._by_name = by_name
        self._known_ids = set(self.primary) | {a.id_key for a in self.data.accounts if a.id_key}

    def _account_owner_id(self, a: Account) -> str:
        owner = self.owner_of.get(a.row)
        return owner.id_key if owner else a.id_key

    def resolve_manager(self, raw_value: str, ref: str) -> str | None:
        """Devuelve el código (normalizado) del jefe referenciado en el directorio, o None."""
        if not ref.strip():
            return ""
        by_name = self._by_name.get(normalize_text(ref), [])
        if is_dn(raw_value):
            if len(by_name) == 1:
                return self._account_owner_id(by_name[0]) or None
            acc = self._by_account.get(normalize_account(ref))
            return (self._account_owner_id(acc) or None) if acc else None
        acc = self._by_account.get(normalize_account(ref))
        if acc:
            return self._account_owner_id(acc) or None
        as_id = normalize_id(ref, self.cfg.id_options)
        if as_id in self._known_ids:
            return as_id
        if len(by_name) == 1:
            return self._account_owner_id(by_name[0]) or None
        return None


def _apply_account_exclusions(ctx: Context) -> None:
    exc = ctx.cfg.exclusions
    patterns = [re.compile(p, re.IGNORECASE) for p in exc.service_account_patterns]
    service = {normalize_account(a) for a in exc.service_accounts}
    special = {normalize_account(a) for a in exc.accounts}
    for a in ctx.data.accounts:
        reason = None
        if a.account_key in service:
            reason = "Cuenta de servicio (lista configurada)"
        else:
            for pat in patterns:
                if pat.search(a.account):
                    reason = f"Cuenta de servicio (patrón '{pat.pattern}')"
                    break
        if reason is None and a.account_key in special:
            reason = "Cuenta especial (lista de exclusiones)"
        if reason:
            ctx.excluded_accounts.add(a.row)
            ctx.exclusions.append(
                Exclusion("cuenta", a.account, a.display_name, reason, "Todas las reglas")
            )


def _select_primary(ctx: Context) -> None:
    rows_by_id: dict[str, list[Employee]] = defaultdict(list)
    for e in ctx.data.employees:
        if e.id_key:
            rows_by_id[e.id_key].append(e)
    ctx.rows_by_id = dict(rows_by_id)
    for key, rows in rows_by_id.items():
        # Con códigos duplicados (p. ej. un reingreso) se usa la fila vigente; R5 lo reporta.
        active = [r for r in rows if r.status == "active"]
        ctx.primary[key] = active[0] if active else rows[-1]

    excluded_ids = {normalize_id(i, ctx.cfg.id_options) for i in ctx.cfg.exclusions.employee_ids}
    for key in sorted(excluded_ids & set(ctx.primary)):
        e = ctx.primary[key]
        ctx.excluded_employees.add(e.row)
        ctx.exclusions.append(
            Exclusion(
                "empleado",
                e.employee_id,
                e.name,
                "Empleado en lista de exclusiones",
                "Todas las reglas",
            )
        )


def _match(ctx: Context) -> None:
    by_id: dict[str, list[Account]] = defaultdict(list)
    for a in ctx.active_accounts():
        if a.id_key:
            by_id[a.id_key].append(a)

    def assign(e: Employee, a: Account, method: str) -> None:
        ctx.accounts_of.setdefault(e.row, []).append(a)
        ctx.owner_of[a.row] = e
        ctx.match_method[a.row] = method

    if "employee_id" in ctx.cfg.match_keys:
        for key, e in ctx.primary.items():
            for a in by_id.get(key, []):
                assign(e, a, "id")

    if "email" in ctx.cfg.match_keys and "email" in ctx.data.directory_fields:
        by_email: dict[str, list[Account]] = defaultdict(list)
        for a in ctx.unassigned_accounts():
            if a.email_key:
                by_email[a.email_key].append(a)
        for e in ctx.primary.values():
            if e.row in ctx.accounts_of or not e.email_key:
                continue
            candidates = by_email.get(e.email_key, [])
            if len(candidates) == 1 and candidates[0].row not in ctx.owner_of:
                assign(e, candidates[0], "email")

    # Las cuentas de empleados excluidos tampoco se evalúan (ni como huérfanas).
    for row in ctx.excluded_employees:
        for a in ctx.accounts_of.get(row, []):
            ctx.excluded_accounts.add(a.row)


def _scheduled_exclusions(ctx: Context) -> None:
    for e in ctx.subjects():
        state = ctx.state(e)
        if state == SCHEDULED_TERMINATION:
            ctx.exclusions.append(
                Exclusion(
                    "empleado",
                    e.employee_id,
                    e.name,
                    f"Baja programada para {e.termination_date.isoformat()}",
                    "R1",
                )
            )
        elif state == SCHEDULED_HIRE:
            ctx.exclusions.append(
                Exclusion(
                    "empleado",
                    e.employee_id,
                    e.name,
                    f"Alta programada para {e.hire_date.isoformat()}",
                    "R2/R2b",
                )
            )
        elif state == ACTIVE and ctx.is_title_without_account(e):
            if not any(a.enabled for a in ctx.accounts(e)):
                ctx.exclusions.append(
                    Exclusion(
                        "empleado",
                        e.employee_id,
                        e.name,
                        f"Cargo sin cuenta obligatoria: {e.raw.get('title', '').strip()}",
                        "R2/R2b",
                    )
                )


def build_context(cfg: Config, data: Dataset, as_of: date | None = None) -> Context:
    ctx = Context(cfg=cfg, data=data, as_of=as_of or cfg.rules.as_of or date.today())
    _apply_account_exclusions(ctx)
    _select_primary(ctx)
    _match(ctx)
    ctx.build_manager_index()
    _scheduled_exclusions(ctx)
    return ctx


def _stats(ctx: Context) -> dict[str, int]:
    states = [ctx.state(e) for e in ctx.primary.values()]
    accounts = ctx.data.accounts
    return {
        "Filas en nómina": len(ctx.data.employees),
        "Empleados únicos": len(ctx.primary),
        "Empleados activos": states.count(ACTIVE),
        "Empleados de baja": states.count(TERMINATED),
        "Cuentas en directorio": len(accounts),
        "Cuentas habilitadas": sum(a.enabled for a in accounts),
        "Cuentas emparejadas": len(ctx.owner_of),
        "Cuentas excluidas": len(ctx.excluded_accounts),
    }


def reconcile(cfg: Config, data: Dataset | None = None, as_of: date | None = None) -> Result:
    """Ejecuta la conciliación completa y devuelve un Result (no escribe archivos)."""
    from .loader import load_dataset
    from .rules import RULES

    if data is None:
        data = load_dataset(cfg)
    ctx = build_context(cfg, data, as_of)
    findings = []
    for rule in RULES:
        if rule.requires_last_logon and not data.has_last_logon:
            ctx.skipped[rule.code] = (
                "El directorio no incluye la columna de último inicio de sesión (last_logon)."
            )
            continue
        findings.extend(rule.run(ctx))
    rule_order = {r.code: i for i, r in enumerate(RULES)}
    findings.sort(
        key=lambda f: (
            rule_order[f.rule],
            SEVERITY_ORDER[f.severity],
            f.issue,
            f.employee_id,
            f.account,
        )
    )
    inputs = []
    for role, src, rows in (
        ("nómina", cfg.hr.file, len(data.employees)),
        ("directorio", cfg.directory.file, len(data.accounts)),
    ):
        if src.is_file():
            inputs.append(InputFile(role, str(src), sha256_file(src), src.stat().st_size, rows))
    return Result(
        findings=findings,
        exclusions=ctx.exclusions,
        as_of=ctx.as_of,
        inputs=inputs,
        skipped_rules=ctx.skipped,
        warnings=data.warnings,
        stats=_stats(ctx),
    )
