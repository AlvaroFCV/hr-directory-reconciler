"""Estructuras de datos compartidas por el cargador, las reglas y los reportes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

SEVERITY_ORDER = {"CRÍTICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3, "INFO": 4}


@dataclass
class Employee:
    row: int  # fila en el archivo de origen (1 = encabezado)
    raw: dict[str, str]  # campo canónico -> valor original como texto
    id_key: str
    email_key: str
    status: str  # 'active' | 'terminated' | 'unknown'
    hire_date: date | None
    termination_date: date | None
    manager_key: str

    @property
    def employee_id(self) -> str:
        return self.raw.get("employee_id", "")

    @property
    def name(self) -> str:
        full = self.raw.get("full_name", "")
        if full:
            return full
        return " ".join(
            p for p in (self.raw.get("first_name", ""), self.raw.get("last_name", "")) if p
        )


@dataclass
class Account:
    row: int
    raw: dict[str, str]
    account_key: str
    id_key: str
    email_key: str
    enabled: bool
    last_logon: datetime | None
    manager_ref: str  # CN si venía como DN, o el valor tal cual

    @property
    def account(self) -> str:
        return self.raw.get("account", "").strip()

    @property
    def display_name(self) -> str:
        return self.raw.get("display_name", "")


@dataclass
class Dataset:
    employees: list[Employee]
    accounts: list[Account]
    hr_fields: set[str]  # campos canónicos presentes en la nómina
    directory_fields: set[str]  # campos canónicos presentes en el directorio
    warnings: list[str] = field(default_factory=list)

    @property
    def has_last_logon(self) -> bool:
        return "last_logon" in self.directory_fields


@dataclass
class Finding:
    rule: str  # 'R1', 'R2b', ...
    severity: str
    issue: str  # subtipo o atributo
    detail: str
    employee_id: str = ""
    employee_name: str = ""
    account: str = ""
    hr_value: str = ""
    directory_value: str = ""
    days: int | None = None
    termination_date: str = ""
    last_logon: str = ""
    source: str = ""  # filas de origen, p. ej. 'nómina fila 12; directorio fila 40'


@dataclass
class Exclusion:
    kind: str  # 'cuenta' | 'empleado'
    identifier: str
    name: str
    reason: str
    scope: str  # reglas afectadas


@dataclass
class InputFile:
    role: str  # 'nómina' | 'directorio'
    path: str
    sha256: str
    size: int
    rows: int


@dataclass
class Result:
    findings: list[Finding]
    exclusions: list[Exclusion]
    as_of: date
    inputs: list[InputFile]
    skipped_rules: dict[str, str]  # regla -> motivo por el que se omitió
    warnings: list[str]
    stats: dict[str, int]

    def by_rule(self, rule: str) -> list[Finding]:
        return [f for f in self.findings if f.rule == rule]
