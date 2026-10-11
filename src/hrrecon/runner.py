"""Orquesta una ejecución: conciliar, escribir reportes y registrar la evidencia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .config import Config
from .engine import reconcile
from .evidence import append_entries
from .models import Result
from .report import write_excel, write_html


@dataclass
class RunOutput:
    result: Result
    run_id: str
    html: Path
    excel: Path
    evidence_log: Path
    evidence_head: str


def run(cfg: Config, as_of: date | None = None, run_id: str | None = None) -> RunOutput:
    result = reconcile(cfg, as_of=as_of)
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = cfg.output.dir
    stem, n = f"{cfg.output.basename}_{run_id}", 1
    while (out_dir / f"{stem}.html").exists() or (out_dir / f"{stem}.xlsx").exists():
        n += 1  # dos ejecuciones en el mismo segundo: nunca sobrescribir un reporte
        stem = f"{cfg.output.basename}_{run_id}_{n}"
    run_id = stem.removeprefix(f"{cfg.output.basename}_")
    html = write_html(result, out_dir / f"{stem}.html", run_id)
    excel = write_excel(result, out_dir / f"{stem}.xlsx", run_id)
    files = [("input", i.role, Path(i.path)) for i in result.inputs]
    files += [("report", "html", html), ("report", "excel", excel)]
    entries = append_entries(cfg.output.evidence_log, files, run_id)
    return RunOutput(
        result, run_id, html, excel, cfg.output.evidence_log, entries[-1]["entry_hash"]
    )
