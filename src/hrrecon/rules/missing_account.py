"""R2 / R2b: empleados activos sin cuenta, o solo con cuentas deshabilitadas."""

from __future__ import annotations

from ..engine import ACTIVE, Context
from .base import finding


def _candidates(ctx: Context):
    for e in ctx.subjects():
        if ctx.state(e) == ACTIVE and not ctx.is_title_without_account(e):
            yield e


def run_missing(ctx: Context) -> list:
    out = []
    for e in _candidates(ctx):
        if not ctx.accounts(e):
            out.append(
                finding(
                    "R2",
                    "ALTA",
                    "no_account",
                    "Empleado activo sin cuenta en el directorio (ni por código ni por correo).",
                    e,
                    hr_value=e.raw.get("title", ""),
                )
            )
    return out


def run_disabled(ctx: Context) -> list:
    out = []
    for e in _candidates(ctx):
        accounts = ctx.accounts(e)
        if accounts and not any(a.enabled for a in accounts):
            for a in accounts:
                out.append(
                    finding(
                        "R2b",
                        "MEDIA",
                        "only_disabled",
                        "Empleado activo cuya única cuenta está deshabilitada.",
                        e,
                        a,
                        hr_value=e.raw.get("status", ""),
                        directory_value="Deshabilitada",
                    )
                )
    return out
