import csv
from datetime import date
from pathlib import Path

import pytest

from hrrecon.config import config_from_dict, load_config
from hrrecon.engine import reconcile
from hrrecon.generator import generate
from hrrecon.normalize import IdOptions, normalize_id

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 10, 1)


def nid(value: str) -> str:
    return normalize_id(value, IdOptions(zfill=6))


@pytest.fixture(scope="session")
def sample(tmp_path_factory):
    """Datos ficticios generados + resultado de conciliarlos con la configuración de ejemplo."""
    out = tmp_path_factory.mktemp("sample")
    expected = generate(out, n_employees=500, seed=42, as_of=AS_OF)
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    cfg.hr.file = out / "nomina.xlsx"
    cfg.directory.file = out / "directorio.csv"
    cfg.output.dir = out / "output"
    cfg.output.evidence_log = out / "output" / "evidence_log.jsonl"
    result = reconcile(cfg, as_of=AS_OF)
    return result, expected, cfg


def employee_ids(result, rule, issue=None, severity=None):
    return sorted(
        {
            nid(f.employee_id)
            for f in result.findings
            if f.rule == rule
            and (issue is None or f.issue == issue)
            and (severity is None or f.severity == severity)
        }
    )


def account_names(result, rule):
    return sorted({f.account for f in result.findings if f.rule == rule})


HR_HEADERS = ["ID", "Nombre", "Estado", "Cargo", "Depto", "Jefe", "Correo", "Ingreso", "Salida"]
DIR_HEADERS = [
    "Cuenta",
    "EmpID",
    "Habilitada",
    "Nombre",
    "Cargo",
    "Depto",
    "Jefe",
    "Correo",
    "UltimoLogon",
]


def base_config(tmp_path: Path, with_logon=True, **overrides) -> dict:
    dir_columns = {
        "account": "Cuenta",
        "employee_id": "EmpID",
        "enabled": "Habilitada",
        "display_name": "Nombre",
        "title": "Cargo",
        "department": "Depto",
        "manager": "Jefe",
        "email": "Correo",
    }
    if with_logon:
        dir_columns["last_logon"] = "UltimoLogon"
    data = {
        "hr": {
            "file": "hr.csv",
            "delimiter": ",",
            "columns": {
                "employee_id": "ID",
                "full_name": "Nombre",
                "status": "Estado",
                "title": "Cargo",
                "department": "Depto",
                "manager_id": "Jefe",
                "email": "Correo",
                "hire_date": "Ingreso",
                "termination_date": "Salida",
            },
            "status_values": {"active": ["activo"], "terminated": ["baja"]},
        },
        "directory": {"file": "ad.csv", "delimiter": ",", "columns": dir_columns},
        "matching": {"keys": ["employee_id", "email"], "id_format": {"zfill": 6}},
        "exclusions": {
            "service_accounts": {"account_patterns": ["^svc_"], "accounts": ["scanner.piso3"]},
            "accounts": ["recepcion.general"],
            "titles_no_account_required": ["Pasante"],
        },
        "rules": {"as_of": AS_OF.isoformat()},
    }
    data.update(overrides)
    return data


def run_case(tmp_path: Path, hr_rows, dir_rows, with_logon=True, **overrides):
    """Concilia un caso pequeño escrito a mano. Filas como dict con claves de los encabezados."""
    with (tmp_path / "hr.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, HR_HEADERS)
        w.writeheader()
        w.writerows(hr_rows)
    headers = DIR_HEADERS if with_logon else DIR_HEADERS[:-1]
    with (tmp_path / "ad.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(dir_rows)
    cfg = config_from_dict(base_config(tmp_path, with_logon, **overrides), tmp_path)
    return reconcile(cfg)


def emp(
    id_,
    name="Ana Muñoz",
    status="Activo",
    title="Analista",
    dept="Finanzas",
    boss="",
    email=None,
    hire="01/01/2020",
    term="",
):
    return {
        "ID": id_,
        "Nombre": name,
        "Estado": status,
        "Cargo": title,
        "Depto": dept,
        "Jefe": boss,
        "Correo": email if email is not None else f"u{nid(id_)}@x.example",
        "Ingreso": hire,
        "Salida": term,
    }


def acc(
    account,
    id_,
    name="Ana Muñoz",
    enabled="True",
    title="Analista",
    dept="Finanzas",
    boss="",
    email=None,
    logon="2026-09-28 09:00:00",
):
    return {
        "Cuenta": account,
        "EmpID": id_,
        "Habilitada": enabled,
        "Nombre": name,
        "Cargo": title,
        "Depto": dept,
        "Jefe": boss,
        "Correo": email if email is not None else f"u{nid(id_)}@x.example",
        "UltimoLogon": logon,
    }
