"""R5: problemas de calidad de datos que impiden una conciliación fiable."""

from __future__ import annotations

from collections import defaultdict

from ..engine import Context
from .base import finding

CODE = "R5"


def run(ctx: Context) -> list:
    out = []
    employees = ctx.data.employees

    # Códigos de empleado duplicados en nómina
    for _key, rows in sorted(ctx.rows_by_id.items()):
        if len(rows) > 1:
            names = " / ".join(dict.fromkeys(r.name for r in rows))
            filas = ", ".join(str(r.row) for r in rows)
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "duplicate_hr_id",
                    f"El código aparece en {len(rows)} filas de nómina ({filas}). "
                    "Se usó la fila vigente para conciliar.",
                    employee_id=rows[0].employee_id.strip(),
                    employee_name=names,
                    source=f"nómina filas {filas}",
                )
            )

    for e in employees:
        if not e.id_key:
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "missing_employee_id",
                    "Fila de nómina sin código de empleado: no se puede conciliar.",
                    e,
                )
            )
        elif e.status == "unknown" and ctx.primary.get(e.id_key) is e:
            raw = e.raw.get("status", "").strip()
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "unknown_status",
                    f"Estado no reconocido en nómina: '{raw or '(vacío)'}'. "
                    "El empleado no se evalúa en R1-R3.",
                    e,
                    hr_value=raw,
                )
            )

    for e in ctx.subjects():
        if e.status == "terminated" and e.termination_date is None:
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "terminated_without_date",
                    "Empleado de baja sin fecha de salida.",
                    e,
                    hr_value=e.raw.get("status", ""),
                )
            )
        if e.status == "active" and e.termination_date and e.termination_date <= ctx.as_of:
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "status_date_inconsistent",
                    f"Estado 'activo' con fecha de salida pasada "
                    f"({e.termination_date.isoformat()}).",
                    e,
                    hr_value=e.raw.get("status", ""),
                )
            )
        enabled = [a for a in ctx.accounts(e) if a.enabled]
        if len(enabled) > 1:
            out.append(
                finding(
                    CODE,
                    "ALTA",
                    "multiple_enabled_accounts",
                    f"{len(enabled)} cuentas habilitadas para el mismo empleado.",
                    e,
                    account=", ".join(sorted(a.account for a in enabled)),
                )
            )
        for a in ctx.accounts(e):
            if ctx.match_method.get(a.row) == "email":
                emp = a.raw.get("employee_id", "").strip()
                out.append(
                    finding(
                        CODE,
                        "BAJA",
                        "matched_by_email",
                        "Cuenta emparejada por correo: el employeeID del directorio "
                        f"está {'vacío' if not emp else f'mal ({emp})'}.",
                        e,
                        a,
                        directory_value=emp,
                    )
                )

    # Correos duplicados en nómina (entre empleados distintos)
    hr_emails: dict[str, dict[str, object]] = defaultdict(dict)
    for e in employees:
        if e.email_key:
            hr_emails[e.email_key][e.id_key or f"fila{e.row}"] = e
    for email, people in sorted(hr_emails.items()):
        if len(people) > 1:
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "duplicate_email_hr",
                    f"El correo está asignado a {len(people)} empleados en nómina.",
                    employee_id=", ".join(p.employee_id.strip() for p in people.values()),
                    employee_name=" / ".join(p.name for p in people.values()),
                    hr_value=email,
                    source="nómina filas " + ", ".join(str(p.row) for p in people.values()),
                )
            )

    # Correos duplicados en el directorio (entre cuentas de titulares distintos)
    dir_emails: dict[str, list] = defaultdict(list)
    for a in ctx.active_accounts():
        if a.email_key:
            dir_emails[a.email_key].append(a)
    for email, accounts in sorted(dir_emails.items()):
        owners = {ctx.owner_of[a.row].row if a.row in ctx.owner_of else -a.row for a in accounts}
        if len(owners) > 1:
            out.append(
                finding(
                    CODE,
                    "MEDIA",
                    "duplicate_email_directory",
                    f"El correo está en {len(accounts)} cuentas de titulares distintos.",
                    account=", ".join(sorted(a.account for a in accounts)),
                    directory_value=email,
                    source="directorio filas " + ", ".join(str(a.row) for a in accounts),
                )
            )
    return out
