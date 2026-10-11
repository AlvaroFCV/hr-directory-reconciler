"""R7: cuentas habilitadas sin inicio de sesión en N días (requiere last_logon)."""

from __future__ import annotations

from ..engine import TERMINATED, Context
from .base import finding


def run(ctx: Context) -> list:
    limit = ctx.cfg.rules.stale_account_days
    out = []
    for a in ctx.active_accounts():
        if not a.enabled:
            continue
        owner = ctx.owner_of.get(a.row)
        if owner is not None and (
            owner.row in ctx.excluded_employees or ctx.state(owner) == TERMINATED
        ):
            continue  # las bajas ya se reportan en R1
        if a.last_logon is None:
            hire = owner.hire_date if owner else None
            if hire and (ctx.as_of - hire).days <= limit:
                continue  # alta reciente: todavía no ha tenido que iniciar sesión
            days, detail = None, "Sin registro de inicio de sesión."
        else:
            days = (ctx.as_of - a.last_logon.date()).days
            if days <= limit:
                continue
            detail = f"Sin inicio de sesión hace {days} días (límite {limit})."
        out.append(
            finding(
                "R7",
                "MEDIA",
                "stale_account",
                detail,
                owner,
                a,
                days=days,
                directory_value="Habilitada",
            )
        )
    return out
