import json
import shutil

import pytest
from conftest import AS_OF, ROOT

from hrrecon.cli import main


@pytest.fixture
def workspace(tmp_path):
    """Copia la configuración de ejemplo y genera datos en una carpeta temporal."""
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "config.example.yaml", tmp_path / "config")
    assert (
        main(["generate", "--out", str(tmp_path / "data" / "sample"), "--as-of", AS_OF.isoformat()])
        == 0
    )
    return tmp_path


def reconcile(ws, *extra):
    return main(
        [
            "reconcile",
            "-c",
            str(ws / "config" / "config.example.yaml"),
            "--as-of",
            AS_OF.isoformat(),
            *extra,
        ]
    )


def test_end_to_end_reconcile_and_verify(workspace, capsys):
    assert reconcile(workspace) == 0
    out_dir = workspace / "output"
    html = next(out_dir.glob("*.html"))
    xlsx = next(out_dir.glob("*.xlsx"))
    log = out_dir / "evidence_log.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["kind"] for e in entries] == ["input", "input", "report", "report"]
    capsys.readouterr()

    assert main(["verify", str(html), str(xlsx), "--log", str(log)]) == 0
    assert "OK" in capsys.readouterr().out

    head = entries[-1]["entry_hash"]
    assert main(["verify", "--log", str(log), "--head", head]) == 0


def test_verify_detects_modified_report(workspace, capsys):
    reconcile(workspace)
    html = next((workspace / "output").glob("*.html"))
    html.write_text(html.read_text(encoding="utf-8").replace("Crítica", "Baja"), encoding="utf-8")
    assert main(["verify", str(html), "--log", str(workspace / "output/evidence_log.jsonl")]) == 1
    assert "MODIFICADO" in capsys.readouterr().out


def test_verify_detects_tampered_log(workspace, capsys):
    reconcile(workspace)
    reconcile(workspace)
    log = workspace / "output" / "evidence_log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")  # borra una línea
    html = sorted((workspace / "output").glob("*.html"))[-1]
    assert main(["verify", str(html), "--log", str(log)]) == 1
    assert "MANIPULADO" in capsys.readouterr().out


def test_verify_detects_truncated_log_with_head(workspace, capsys):
    reconcile(workspace)
    log = workspace / "output" / "evidence_log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[-1])["entry_hash"]
    log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # quita la última línea
    assert main(["verify", "--log", str(log)]) == 0  # la cadena restante es coherente...
    assert main(["verify", "--log", str(log), "--head", head]) == 1  # ...pero la cabeza no


def test_runs_never_overwrite_reports(workspace):
    reconcile(workspace)
    reconcile(workspace)
    assert len(list((workspace / "output").glob("*.html"))) == 2


def test_fail_on_threshold(workspace):
    assert reconcile(workspace, "--fail-on", "critica") == 2
    assert reconcile(workspace, "--fail-on", "CRÍTICA") == 2  # con o sin tilde


def test_missing_last_logon_column_is_not_an_error(workspace, capsys):
    cfg = workspace / "config" / "config.example.yaml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace(
            'last_logon: "LastLogonDate"', 'last_logon: "ColumnaInexistente"'
        ),
        encoding="utf-8",
    )
    assert reconcile(workspace) == 0
    out = capsys.readouterr().out
    assert "omitida" in out and "columna opcional no encontrada" in out


def test_friendly_errors(tmp_path, capsys):
    assert main(["reconcile", "-c", str(tmp_path / "no.yaml")]) == 1
    assert "No existe" in capsys.readouterr().err
