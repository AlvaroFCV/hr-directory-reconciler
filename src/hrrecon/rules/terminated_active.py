"""R1: empleados de baja en nómina cuya cuenta sigue habilitada en el directorio."""

from __future__ import annotations

from ..engine import TERMINATED, Context
from .base import finding

CODE = "R1"


def run(ctx: Context) -> list:
    threshold = ctx.cfg.rules.termination_escalation_days
    out = []
    for e in ctx.subjects():
        if ctx.state(e) != TERMINATED:
            continue
        term = e.termination_date
        for a in ctx.accounts(e):
            if not a.enabled:
                continue  # baja con cuenta deshabilitada: correcto
            if term is None:
                days, severity = None, "ALTA"
                detail = "Baja en nómina sin fecha de salida; la cuenta sigue habilitada."
            else:
                days = (ctx.as_of - term).days
                severity = "CRÍTICA" if days > threshold else "ALTA"
                detail = f"Baja hace {days} días ({term.isoformat()}); la cuenta sigue habilitada."
                if e.status == "active":
                    detail += " Nómina indica 'activo' pero la fecha de salida ya pasó."
                if a.last_logon and a.last_logon.date() > term:
                    severity = "CRÍTICA"
                    detail += " Registra inicio de sesión posterior a la baja."
            out.append(
                finding(
                    CODE,
                    severity,
                    "terminated_enabled",
                    detail,
                    e,
                    a,
                    days=days,
                    termination_date=term.isoformat() if term else "",
                    hr_value=e.raw.get("status", ""),
                    directory_value="Habilitada",
                )
            )
    return out
