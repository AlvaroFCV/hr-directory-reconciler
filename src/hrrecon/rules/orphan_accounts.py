"""R4: cuentas del directorio sin empleado asociado (excluye servicio y especiales)."""

from __future__ import annotations

from ..engine import Context
from .base import finding


def run(ctx: Context) -> list:
    out = []
    for a in ctx.unassigned_accounts():
        emp = a.raw.get("employee_id", "").strip()
        if emp:
            detail = f"El employeeID '{emp}' no existe en la nómina."
        else:
            detail = "Sin employeeID y sin correo que coincida con un empleado."
        if not a.enabled:
            detail += " Cuenta deshabilitada: candidata a depuración."
        out.append(
            finding(
                "R4",
                "ALTA" if a.enabled else "BAJA",
                "orphan",
                detail,
                account=a,
                employee_id=emp,
                employee_name=a.display_name,
                directory_value="Habilitada" if a.enabled else "Deshabilitada",
            )
        )
    return out
