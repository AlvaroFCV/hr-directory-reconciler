"""R6: cuentas con inicio de sesión posterior a la fecha de baja (requiere last_logon)."""

from __future__ import annotations

from ..engine import TERMINATED, Context
from .base import finding


def run(ctx: Context) -> list:
    out = []
    for e in ctx.subjects():
        term = e.termination_date
        if ctx.state(e) != TERMINATED or term is None:
            continue
        for a in ctx.accounts(e):
            if a.last_logon and a.last_logon.date() > term:
                days = (a.last_logon.date() - term).days
                estado = "habilitada" if a.enabled else "hoy deshabilitada"
                out.append(
                    finding(
                        "R6",
                        "CRÍTICA",
                        "logon_after_termination",
                        f"Inicio de sesión {days} días después de la baja ({term.isoformat()}); "
                        f"cuenta {estado}. Posible uso indebido: revisar actividad.",
                        e,
                        a,
                        days=days,
                        termination_date=term.isoformat(),
                        directory_value="Habilitada" if a.enabled else "Deshabilitada",
                    )
                )
    return out
