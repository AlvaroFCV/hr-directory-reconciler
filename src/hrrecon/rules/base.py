"""Definición común de las reglas de detección."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Account, Employee, Finding

if TYPE_CHECKING:
    from ..engine import Context


@dataclass(frozen=True)
class Rule:
    code: str
    title: str
    description: str
    recommendation: str
    run: Callable[[Context], list[Finding]]
    requires_last_logon: bool = False


def finding(
    rule: str,
    severity: str,
    issue: str,
    detail: str,
    employee: Employee | None = None,
    account: Account | str | None = None,
    **extra,
) -> Finding:
    """Crea un hallazgo rellenando los datos comunes de empleado y cuenta."""
    sources = []
    if employee is not None:
        sources.append(f"nómina fila {employee.row}")
    if isinstance(account, Account):
        sources.append(f"directorio fila {account.row}")
    return Finding(
        rule=rule,
        severity=severity,
        issue=issue,
        detail=detail,
        employee_id=employee.employee_id.strip() if employee else extra.pop("employee_id", ""),
        employee_name=employee.name if employee else extra.pop("employee_name", ""),
        account=account.account if isinstance(account, Account) else (account or ""),
        last_logon=_fmt_dt(account.last_logon) if isinstance(account, Account) else "",
        source=extra.pop("source", "; ".join(sources)),
        **extra,
    )


def _fmt_dt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""
