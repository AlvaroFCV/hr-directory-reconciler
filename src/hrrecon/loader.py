"""Lectura de exportaciones CSV/Excel y mapeo a campos canónicos. Solo lectura."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .config import DIRECTORY_REQUIRED, HR_REQUIRED, Config, SourceConfig
from .models import Account, Dataset, Employee
from .normalize import (
    manager_reference,
    normalize_account,
    normalize_email,
    normalize_id,
    normalize_text,
    parse_bool,
    parse_date,
    parse_datetime,
    to_str,
)

EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}


class InputError(ValueError):
    """Problema con un archivo de entrada (no existe, faltan columnas, etc.)."""


def read_table(src: SourceConfig) -> pd.DataFrame:
    """Lee un CSV o Excel como texto, sin interpretar tipos (los IDs conservan sus ceros)."""
    path = Path(src.file)
    if not path.is_file():
        raise InputError(f"No existe el archivo de entrada: {path}")
    if path.suffix.lower() in EXCEL_SUFFIXES:
        sheet = src.sheet if src.sheet is not None else 0
        try:
            df = pd.read_excel(path, sheet_name=sheet, dtype=object)
        except ValueError as exc:
            raise InputError(f"No se pudo leer la hoja {sheet!r} de {path.name}: {exc}") from exc
    else:
        delimiter = src.delimiter
        if not delimiter:
            with path.open(encoding=src.encoding, newline="") as fh:
                sample = fh.read(4096)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        df = pd.read_csv(
            path, sep=delimiter, dtype=str, keep_default_na=False, encoding=src.encoding
        )
    df = df.dropna(how="all")
    return df


def _map_columns(df: pd.DataFrame, mapping: dict[str, str], required: tuple[str, ...], role: str):
    """Devuelve {campo_canónico: columna_real}. Ignora mayúsculas y espacios en encabezados."""
    actual = {normalize_text(c): c for c in df.columns}
    resolved: dict[str, str] = {}
    missing_required, missing_optional = [], []
    for field_name, header in mapping.items():
        col = actual.get(normalize_text(header))
        if col is not None:
            resolved[field_name] = col
        elif field_name in required:
            missing_required.append(f"{field_name} -> '{header}'")
        else:
            missing_optional.append(f"{field_name} -> '{header}'")
    if missing_required:
        raise InputError(
            f"Faltan columnas obligatorias en {role}: {', '.join(missing_required)}. "
            f"Columnas disponibles: {', '.join(map(str, df.columns))}"
        )
    warnings = [f"{role}: columna opcional no encontrada, se omite: {m}" for m in missing_optional]
    return resolved, warnings


def _raw_rows(df: pd.DataFrame, columns: dict[str, str]):
    for idx, row in df.iterrows():
        raw = {f: to_str(row[c]) for f, c in columns.items()}
        # Las fechas de Excel llegan como Timestamp; se conservan para parsearlas sin pérdida.
        cells = {f: row[c] for f, c in columns.items()}
        yield int(idx) + 2, raw, cells


def load_hr(cfg: Config) -> tuple[list[Employee], set[str], list[str], int]:
    df = read_table(cfg.hr)
    columns, warnings = _map_columns(df, cfg.hr.columns, HR_REQUIRED, "nómina")
    active = {normalize_text(v) for v in cfg.hr.active_values}
    terminated = {normalize_text(v) for v in cfg.hr.terminated_values}
    employees = []
    for row, raw, cells in _raw_rows(df, columns):
        status_norm = normalize_text(raw.get("status", ""))
        status = (
            "active"
            if status_norm in active
            else "terminated"
            if status_norm in terminated
            else "unknown"
        )
        for key in ("hire_date", "termination_date"):
            if key in cells and parse_date(cells[key], cfg.date_formats):
                raw[key] = parse_date(cells[key], cfg.date_formats).isoformat()
        employees.append(
            Employee(
                row=row,
                raw=raw,
                id_key=normalize_id(raw.get("employee_id"), cfg.id_options),
                email_key=normalize_email(raw.get("email")),
                status=status,
                hire_date=parse_date(cells.get("hire_date"), cfg.date_formats),
                termination_date=parse_date(cells.get("termination_date"), cfg.date_formats),
                manager_key=normalize_id(raw.get("manager_id"), cfg.id_options),
            )
        )
    return employees, set(columns), warnings, len(df)


def load_directory(cfg: Config) -> tuple[list[Account], set[str], list[str], int]:
    df = read_table(cfg.directory)
    columns, warnings = _map_columns(df, cfg.directory.columns, DIRECTORY_REQUIRED, "directorio")
    accounts = []
    for row, raw, cells in _raw_rows(df, columns):
        if not raw.get("account", "").strip():
            warnings.append(f"directorio fila {row}: cuenta vacía, se ignora")
            continue
        accounts.append(
            Account(
                row=row,
                raw=raw,
                account_key=normalize_account(raw["account"]),
                id_key=normalize_id(raw.get("employee_id"), cfg.id_options),
                email_key=normalize_email(raw.get("email")),
                enabled=parse_bool(raw.get("enabled", ""), cfg.directory.enabled_values),
                last_logon=parse_datetime(cells.get("last_logon"), cfg.date_formats),
                manager_ref=manager_reference(raw.get("manager", "")),
            )
        )
    return accounts, set(columns), warnings, len(df)


def load_dataset(cfg: Config) -> Dataset:
    employees, hr_fields, w1, _ = load_hr(cfg)
    accounts, dir_fields, w2, _ = load_directory(cfg)
    return Dataset(employees, accounts, hr_fields, dir_fields, warnings=w1 + w2)
