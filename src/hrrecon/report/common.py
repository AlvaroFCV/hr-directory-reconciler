"""Datos compartidos por los reportes HTML y Excel: columnas por regla y resúmenes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..models import Finding, Result
from ..rules import ISSUE_LABELS, RULES, Rule

SEVERITIES = ["CRÍTICA", "ALTA", "MEDIA", "BAJA"]

# (encabezado, atributo de Finding)
_SEV = ("Severidad", "severity")
_ID = ("Código", "employee_id")
_NAME = ("Empleado", "employee_name")
_ACC = ("Cuenta", "account")
_DETAIL = ("Detalle", "detail")
_LOGON = ("Último inicio de sesión", "last_logon")
_SRC = ("Origen", "source")

COLUMNS: dict[str, list[tuple[str, str]]] = {
    "R1": [
        _SEV,
        _ID,
        _NAME,
        _ACC,
        ("Fecha de baja", "termination_date"),
        ("Días desde la baja", "days"),
        _LOGON,
        _DETAIL,
        _SRC,
    ],
    "R6": [
        _SEV,
        _ID,
        _NAME,
        _ACC,
        ("Fecha de baja", "termination_date"),
        ("Días tras la baja", "days"),
        _LOGON,
        ("Estado cuenta", "directory_value"),
        _DETAIL,
        _SRC,
    ],
    "R2": [_SEV, _ID, _NAME, ("Cargo", "hr_value"), _DETAIL, _SRC],
    "R2b": [_SEV, _ID, _NAME, _ACC, _LOGON, _DETAIL, _SRC],
    "R3": [
        _SEV,
        _ID,
        _NAME,
        _ACC,
        ("Atributo", "issue"),
        ("Valor en nómina", "hr_value"),
        ("Valor en directorio", "directory_value"),
        _DETAIL,
        _SRC,
    ],
    "R4": [
        _SEV,
        _ACC,
        ("Nombre en directorio", "employee_name"),
        ("employeeID", "employee_id"),
        ("Estado cuenta", "directory_value"),
        _LOGON,
        _DETAIL,
        _SRC,
    ],
    "R7": [_SEV, _ACC, _ID, _NAME, _LOGON, ("Días sin uso", "days"), _DETAIL, _SRC],
    "R5": [
        _SEV,
        ("Problema", "issue"),
        _ID,
        _NAME,
        _ACC,
        ("Valor (nómina)", "hr_value"),
        ("Valor (directorio)", "directory_value"),
        _DETAIL,
        _SRC,
    ],
}

SHEET_NAMES = {
    "R1": "R1 Bajas con cuenta",
    "R6": "R6 Uso tras la baja",
    "R2": "R2 Activos sin cuenta",
    "R2b": "R2b Cuenta deshabilitada",
    "R3": "R3 Atributos",
    "R4": "R4 Cuentas huérfanas",
    "R7": "R7 Cuentas sin uso",
    "R5": "R5 Calidad de datos",
}


def cell_value(f: Finding, attr: str):
    value = getattr(f, attr)
    if attr == "issue":
        return ISSUE_LABELS.get(value, value)
    if value is None:
        return "" if attr != "days" else "—"
    return value


@dataclass
class CategorySummary:
    rule: Rule
    findings: list[Finding]
    counts: dict[str, int]
    skipped: str | None

    @property
    def total(self) -> int:
        return len(self.findings)


def categories(result: Result) -> list[CategorySummary]:
    out = []
    for rule in RULES:
        found = result.by_rule(rule.code)
        counts = Counter(f.severity for f in found)
        out.append(
            CategorySummary(
                rule=rule,
                findings=found,
                counts={s: counts.get(s, 0) for s in SEVERITIES},
                skipped=result.skipped_rules.get(rule.code),
            )
        )
    return out


def severity_totals(result: Result) -> dict[str, int]:
    counts = Counter(f.severity for f in result.findings)
    return {s: counts.get(s, 0) for s in SEVERITIES}


def key_messages(result: Result) -> list[str]:
    """Frases breves para el resumen ejecutivo."""
    msgs = []
    r1 = result.by_rule("R1")
    if r1:
        crit = sum(f.severity == "CRÍTICA" for f in r1)
        oldest = max((f.days for f in r1 if f.days is not None), default=None)
        msg = f"{len(r1)} cuenta(s) de personas dadas de baja siguen habilitadas"
        if crit:
            msg += f"; {crit} superan el umbral de días o registran uso tras la baja"
        if oldest is not None:
            msg += f" (la más antigua, hace {oldest} días)"
        msgs.append(msg + ".")
    r6 = result.by_rule("R6")
    if r6:
        msgs.append(
            f"{len(r6)} cuenta(s) registran inicio de sesión posterior a la baja: "
            "posible uso indebido que requiere revisión de Seguridad."
        )
    r4 = [f for f in result.by_rule("R4") if f.severity == "ALTA"]
    if r4:
        msgs.append(f"{len(r4)} cuenta(s) habilitadas no corresponden a ningún empleado.")
    r2 = result.by_rule("R2")
    if r2:
        msgs.append(f"{len(r2)} empleado(s) activos no tienen cuenta en el directorio.")
    r3 = result.by_rule("R3")
    if r3:
        people = len({f.employee_id for f in r3})
        msgs.append(
            f"{len(r3)} diferencia(s) de cargo, departamento, jefe o correo en {people} "
            "empleado(s): pueden implicar permisos que no corresponden al rol actual."
        )
    if not msgs:
        msgs.append("No se encontraron hallazgos de riesgo en las reglas evaluadas.")
    return msgs
