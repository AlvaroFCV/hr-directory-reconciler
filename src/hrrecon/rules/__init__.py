"""Registro de reglas, en el orden en que aparecen en los reportes."""

from __future__ import annotations

from . import (
    attribute_drift,
    data_quality,
    missing_account,
    orphan_accounts,
    post_termination_logon,
    stale_accounts,
    terminated_active,
)
from .base import Rule

RULES: list[Rule] = [
    Rule(
        "R1",
        "Bajas con cuenta habilitada",
        "Empleados dados de baja en nómina cuya cuenta sigue habilitada en el directorio. "
        "Las bajas con fecha futura (programadas) no se reportan.",
        "Deshabilitar la cuenta de inmediato y revisar su actividad desde la fecha de baja.",
        terminated_active.run,
    ),
    Rule(
        "R6",
        "Inicio de sesión posterior a la baja",
        "Cuentas (habilitadas o no) con un último inicio de sesión posterior a la fecha de baja.",
        "Tratar como posible incidente de seguridad: revisar registros y notificar a Seguridad.",
        post_termination_logon.run,
        requires_last_logon=True,
    ),
    Rule(
        "R2",
        "Empleados activos sin cuenta",
        "Empleados activos sin cuenta en el directorio. Se omiten las altas con fecha futura y "
        "los cargos configurados como 'sin cuenta obligatoria' (p. ej. pasantes).",
        "Confirmar con RR.HH. y crear la cuenta según el proceso de alta.",
        missing_account.run_missing,
    ),
    Rule(
        "R2b",
        "Empleados activos con cuenta deshabilitada",
        "Empleados activos cuyas cuentas están todas deshabilitadas.",
        "Verificar si es una suspensión intencional o un error en el proceso.",
        missing_account.run_disabled,
    ),
    Rule(
        "R3",
        "Diferencias de atributos",
        "Cargo, departamento, jefe o correo distintos entre nómina y directorio, después de "
        "normalizar tildes, mayúsculas, espacios y formatos.",
        "Actualizar el directorio desde la fuente oficial (nómina); revisar permisos por rol.",
        attribute_drift.run,
    ),
    Rule(
        "R4",
        "Cuentas sin empleado asociado",
        "Cuentas del directorio que no corresponden a ningún empleado de nómina. Excluye "
        "cuentas de servicio y cuentas especiales configuradas.",
        "Identificar al responsable; deshabilitar y eliminar las que no se justifiquen.",
        orphan_accounts.run,
    ),
    Rule(
        "R7",
        "Cuentas habilitadas sin uso",
        "Cuentas habilitadas sin inicio de sesión en el periodo configurado.",
        "Confirmar con el jefe si la cuenta sigue siendo necesaria; deshabilitar si no.",
        stale_accounts.run,
        requires_last_logon=True,
    ),
    Rule(
        "R5",
        "Calidad de datos",
        "Códigos duplicados, filas sin código, estados no reconocidos, varias cuentas "
        "habilitadas para un empleado, correos duplicados y emparejamientos por correo.",
        "Corregir los datos en el sistema de origen para que la conciliación sea confiable.",
        data_quality.run,
    ),
]

RULES_BY_CODE = {r.code: r for r in RULES}

ISSUE_LABELS = {
    "terminated_enabled": "Baja con cuenta habilitada",
    "logon_after_termination": "Uso posterior a la baja",
    "no_account": "Sin cuenta",
    "only_disabled": "Cuenta deshabilitada",
    "title": "Cargo",
    "department": "Departamento",
    "manager": "Jefe",
    "email": "Correo",
    "orphan": "Cuenta huérfana",
    "stale_account": "Cuenta sin uso",
    "duplicate_hr_id": "Código duplicado en nómina",
    "missing_employee_id": "Fila sin código",
    "unknown_status": "Estado no reconocido",
    "terminated_without_date": "Baja sin fecha de salida",
    "status_date_inconsistent": "Estado y fecha inconsistentes",
    "multiple_enabled_accounts": "Varias cuentas habilitadas",
    "duplicate_email_hr": "Correo duplicado en nómina",
    "duplicate_email_directory": "Correo duplicado en directorio",
    "matched_by_email": "Emparejado por correo",
}

__all__ = ["RULES", "RULES_BY_CODE", "ISSUE_LABELS", "Rule"]
