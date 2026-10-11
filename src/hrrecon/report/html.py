"""Reporte HTML autocontenido para gerencia (sin JavaScript ni recursos externos)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .. import __version__
from ..models import Result
from .common import COLUMNS, SEVERITIES, categories, cell_value, key_messages, severity_totals

_env = Environment(
    loader=PackageLoader("hrrecon", "report/templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.globals["cell_value"] = cell_value
_env.filters["basename"] = lambda p: Path(p).name

SEVERITY_CLASS = {"CRÍTICA": "critical", "ALTA": "serious", "MEDIA": "warning", "BAJA": "low"}


def render_html(result: Result, run_id: str, generated_at: datetime | None = None) -> str:
    cats = categories(result)
    max_total = max((c.total for c in cats), default=0) or 1
    template = _env.get_template("report.html.j2")
    return template.render(
        result=result,
        run_id=run_id,
        generated_at=(generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M"),
        version=__version__,
        categories=cats,
        max_total=max_total,
        totals=severity_totals(result),
        total=len(result.findings),
        severities=SEVERITIES,
        severity_class=SEVERITY_CLASS,
        columns=COLUMNS,
        nowrap={"employee_id", "employee_name", "account", "termination_date", "last_logon"},
        messages=key_messages(result),
    )


def write_html(result: Result, path: Path, run_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(result, run_id), encoding="utf-8")
    return path
