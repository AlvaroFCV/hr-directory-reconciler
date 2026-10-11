"""Carga y validación del archivo de configuración YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .normalize import DEFAULT_DATE_FORMATS, IdOptions, TextOptions, parse_date

HR_FIELDS = (
    "employee_id",
    "first_name",
    "last_name",
    "full_name",
    "status",
    "title",
    "department",
    "manager_id",
    "email",
    "hire_date",
    "termination_date",
)
HR_REQUIRED = ("employee_id", "status")

DIRECTORY_FIELDS = (
    "account",
    "employee_id",
    "enabled",
    "display_name",
    "title",
    "department",
    "manager",
    "email",
    "last_logon",
)
DIRECTORY_REQUIRED = ("account", "enabled")

COMPARABLE_ATTRIBUTES = ("title", "department", "manager", "email")


class ConfigError(ValueError):
    """Error de configuración con un mensaje legible para el usuario."""


@dataclass
class SourceConfig:
    file: Path
    columns: dict[str, str]
    sheet: str | int | None = None
    encoding: str = "utf-8-sig"
    delimiter: str | None = None


@dataclass
class HrConfig(SourceConfig):
    active_values: list[str] = field(default_factory=lambda: ["activo"])
    terminated_values: list[str] = field(default_factory=lambda: ["baja", "inactivo"])


@dataclass
class DirectoryConfig(SourceConfig):
    enabled_values: list[str] = field(default_factory=lambda: ["true", "1", "habilitado"])


@dataclass
class ExclusionsConfig:
    service_account_patterns: list[str] = field(default_factory=list)
    service_accounts: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    employee_ids: list[str] = field(default_factory=list)
    titles_no_account_required: list[str] = field(default_factory=list)


@dataclass
class RulesConfig:
    as_of: date | None = None
    termination_escalation_days: int = 7
    stale_account_days: int = 90


@dataclass
class OutputConfig:
    dir: Path
    evidence_log: Path
    basename: str = "reporte_conciliacion"


@dataclass
class Config:
    hr: HrConfig
    directory: DirectoryConfig
    match_keys: list[str]
    id_options: IdOptions
    text_options: TextOptions
    compare_attributes: list[str]
    exclusions: ExclusionsConfig
    rules: RulesConfig
    output: OutputConfig
    date_formats: tuple[str, ...] = DEFAULT_DATE_FORMATS
    source_path: Path | None = None


def _as_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ConfigError(f"'{name}' debe ser una lista")
    return [str(v) for v in value]


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _columns(section: dict, name: str, allowed: tuple[str, ...], required: tuple[str, ...]):
    columns = section.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise ConfigError(f"'{name}.columns' es obligatorio y debe ser un mapa campo: columna")
    unknown = sorted(set(columns) - set(allowed))
    if unknown:
        raise ConfigError(
            f"Campos desconocidos en '{name}.columns': {', '.join(unknown)}. "
            f"Permitidos: {', '.join(allowed)}"
        )
    missing = [f for f in required if not columns.get(f)]
    if missing:
        raise ConfigError(f"Faltan campos obligatorios en '{name}.columns': {', '.join(missing)}")
    return {k: str(v) for k, v in columns.items() if v}


def config_from_dict(data: dict, base_dir: Path) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("La configuración debe ser un mapa YAML")
    hr_raw = data.get("hr") or {}
    dir_raw = data.get("directory") or {}
    for name, section in (("hr", hr_raw), ("directory", dir_raw)):
        if not section.get("file"):
            raise ConfigError(f"'{name}.file' es obligatorio")

    status = hr_raw.get("status_values") or {}
    hr = HrConfig(
        file=_resolve(base_dir, hr_raw["file"]),
        columns=_columns(hr_raw, "hr", HR_FIELDS, HR_REQUIRED),
        sheet=hr_raw.get("sheet"),
        encoding=hr_raw.get("encoding", "utf-8-sig"),
        delimiter=hr_raw.get("delimiter"),
        active_values=_as_list(status.get("active", ["activo"]), "hr.status_values.active"),
        terminated_values=_as_list(
            status.get("terminated", ["baja", "inactivo"]), "hr.status_values.terminated"
        ),
    )
    directory = DirectoryConfig(
        file=_resolve(base_dir, dir_raw["file"]),
        columns=_columns(dir_raw, "directory", DIRECTORY_FIELDS, DIRECTORY_REQUIRED),
        sheet=dir_raw.get("sheet"),
        encoding=dir_raw.get("encoding", "utf-8-sig"),
        delimiter=dir_raw.get("delimiter"),
        enabled_values=_as_list(
            dir_raw.get("enabled_values", ["true", "1", "habilitado"]),
            "directory.enabled_values",
        ),
    )

    matching = data.get("matching") or {}
    match_keys = _as_list(matching.get("keys", ["employee_id", "email"]), "matching.keys")
    bad_keys = sorted(set(match_keys) - {"employee_id", "email"})
    if bad_keys or not match_keys:
        raise ConfigError("'matching.keys' solo admite: employee_id, email")
    id_fmt = matching.get("id_format") or {}
    id_options = IdOptions(
        zfill=int(id_fmt.get("zfill", 0) or 0),
        strip_non_digits=bool(id_fmt.get("strip_non_digits", False)),
        uppercase=bool(id_fmt.get("uppercase", True)),
        remove_chars=str(id_fmt.get("remove_chars", " -.")),
    )

    norm = data.get("normalization") or {}
    text_options = TextOptions(
        strip_accents=bool(norm.get("strip_accents", True)),
        casefold=bool(norm.get("casefold", True)),
        collapse_spaces=bool(norm.get("collapse_spaces", True)),
    )
    date_formats = tuple(_as_list(norm.get("date_formats"), "normalization.date_formats")) or (
        DEFAULT_DATE_FORMATS
    )

    compare = _as_list(
        data.get("compare_attributes", list(COMPARABLE_ATTRIBUTES)), "compare_attributes"
    )
    bad_attrs = sorted(set(compare) - set(COMPARABLE_ATTRIBUTES))
    if bad_attrs:
        raise ConfigError(
            f"'compare_attributes' no admite: {', '.join(bad_attrs)}. "
            f"Permitidos: {', '.join(COMPARABLE_ATTRIBUTES)}"
        )

    exc = data.get("exclusions") or {}
    svc = exc.get("service_accounts") or {}
    exclusions = ExclusionsConfig(
        service_account_patterns=_as_list(
            svc.get("account_patterns"), "exclusions.service_accounts.account_patterns"
        ),
        service_accounts=_as_list(svc.get("accounts"), "exclusions.service_accounts.accounts"),
        accounts=_as_list(exc.get("accounts"), "exclusions.accounts"),
        employee_ids=_as_list(exc.get("employee_ids"), "exclusions.employee_ids"),
        titles_no_account_required=_as_list(
            exc.get("titles_no_account_required"), "exclusions.titles_no_account_required"
        ),
    )

    rules_raw = data.get("rules") or {}
    as_of_raw = rules_raw.get("as_of")
    as_of = None
    if as_of_raw not in (None, ""):
        as_of = parse_date(as_of_raw)
        if as_of is None:
            raise ConfigError(f"'rules.as_of' no es una fecha válida: {as_of_raw!r}")
    try:
        rules = RulesConfig(
            as_of=as_of,
            termination_escalation_days=int(rules_raw.get("termination_escalation_days", 7)),
            stale_account_days=int(rules_raw.get("stale_account_days", 90)),
        )
    except (TypeError, ValueError) as exc_:
        raise ConfigError(f"Valor numérico inválido en 'rules': {exc_}") from exc_

    out_raw = data.get("output") or {}
    out_dir = _resolve(base_dir, out_raw.get("dir", "output"))
    log = out_raw.get("evidence_log")
    output = OutputConfig(
        dir=out_dir,
        evidence_log=_resolve(base_dir, log) if log else out_dir / "evidence_log.jsonl",
        basename=str(out_raw.get("basename", "reporte_conciliacion")),
    )

    return Config(
        hr=hr,
        directory=directory,
        match_keys=match_keys,
        id_options=id_options,
        text_options=text_options,
        compare_attributes=compare,
        exclusions=exclusions,
        rules=rules,
        output=output,
        date_formats=date_formats,
    )


def load_config(path: str | Path) -> Config:
    """Lee el YAML. Las rutas relativas se resuelven respecto a la carpeta del YAML."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"No existe el archivo de configuración: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido en {path}: {exc}") from exc
    cfg = config_from_dict(data or {}, path.resolve().parent)
    cfg.source_path = path.resolve()
    return cfg
