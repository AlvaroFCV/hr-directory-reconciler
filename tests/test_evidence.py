import json

import pytest

from hrrecon.evidence import (
    GENESIS,
    EvidenceError,
    append_entries,
    sha256_file,
    verify_chain,
    verify_file,
)


@pytest.fixture
def logged(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    files = []
    for name in ("r1.html", "r1.xlsx", "r2.html"):
        f = out / name
        f.write_text(f"contenido {name}", encoding="utf-8")
        files.append(f)
    log = out / "evidence_log.jsonl"
    append_entries(log, [("report", "html", files[0]), ("report", "excel", files[1])], "run1")
    append_entries(log, [("report", "html", files[2])], "run2")
    return log, files


def lines(log):
    return log.read_text(encoding="utf-8").splitlines()


def test_sha256_known_value(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_chain_is_linked(logged):
    log, files = logged
    chain = verify_chain(log)
    assert chain.ok, chain.errors
    assert chain.entries[0]["prev_hash"] == GENESIS
    for prev, cur in zip(chain.entries, chain.entries[1:], strict=False):
        assert cur["prev_hash"] == prev["entry_hash"]
    assert [e["seq"] for e in chain.entries] == [1, 2, 3]
    assert chain.entries[0]["file"] == "r1.html"  # ruta relativa al registro


def test_verify_untouched_report(logged):
    log, files = logged
    chain = verify_chain(log)
    result = verify_file(files[0], chain, log)
    assert result.ok and result.matched_by == "ruta"


def test_verify_detects_modified_report(logged):
    log, files = logged
    files[0].write_text("contenido alterado", encoding="utf-8")
    result = verify_file(files[0], verify_chain(log), log)
    assert result.status == "MODIFICADO"


def test_verify_unregistered_and_missing(logged, tmp_path):
    log, _ = logged
    other = tmp_path / "otro.html"
    other.write_text("x")
    chain = verify_chain(log)
    assert verify_file(other, chain, log).status == "NO_REGISTRADO"
    assert verify_file(tmp_path / "nada.html", chain, log).status == "NO_EXISTE"


def test_verify_copy_matches_by_name(logged, tmp_path):
    log, files = logged
    copy_dir = tmp_path / "auditoria"
    copy_dir.mkdir()
    copy = copy_dir / files[2].name
    copy.write_bytes(files[2].read_bytes())
    result = verify_file(copy, verify_chain(log), log)
    assert result.ok and result.matched_by == "nombre"


def test_tampered_line_content_detected(logged):
    log, files = logged
    rows = lines(log)
    entry = json.loads(rows[0])
    entry["sha256"] = "0" * 64  # alguien "ajusta" el hash para encubrir un cambio
    rows[0] = json.dumps(entry)
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    chain = verify_chain(log)
    assert not chain.ok
    assert any("entry_hash no coincide" in e for e in chain.errors)


def test_recomputed_entry_hash_still_breaks_chain(logged):
    """Aunque el atacante recalcule entry_hash de la línea, la siguiente deja de encadenar."""
    from hrrecon.evidence import _entry_hash

    log, _ = logged
    rows = lines(log)
    entry = json.loads(rows[0])
    entry["sha256"] = "f" * 64
    entry["entry_hash"] = _entry_hash(entry)
    rows[0] = json.dumps(entry)
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    chain = verify_chain(log)
    assert not chain.ok
    assert any("línea 2: prev_hash" in e for e in chain.errors)


def test_deleted_and_reordered_lines_detected(logged):
    log, _ = logged
    rows = lines(log)
    log.write_text("\n".join([rows[0], rows[2]]) + "\n", encoding="utf-8")
    assert not verify_chain(log).ok
    log.write_text("\n".join([rows[1], rows[0], rows[2]]) + "\n", encoding="utf-8")
    assert not verify_chain(log).ok


def test_refuses_to_append_to_tampered_log(logged):
    log, files = logged
    rows = lines(log)
    log.write_text("\n".join(rows[1:]) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceError):
        append_entries(log, [("report", "html", files[0])], "run3")


def test_missing_log(tmp_path):
    chain = verify_chain(tmp_path / "no.jsonl")
    assert not chain.ok and "No existe" in chain.errors[0]
