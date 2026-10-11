"""Evidencia para auditoría: hashes SHA-256 y registro encadenado (append-only).

Cada línea del registro (JSON Lines) guarda el hash de un archivo y el ``prev_hash`` de la
línea anterior; ``entry_hash`` es el SHA-256 de la propia línea sin ese campo. Así:

* si un reporte se modifica, su hash ya no coincide con el registrado;
* si alguien edita, borra o reordena una línea del registro, la cadena se rompe;
* para detectar que se truncaron las últimas líneas, guarde el último ``entry_hash``
  (la "cabeza", que el comando ``reconcile`` imprime) en otro lugar y páselo a
  ``verify --head``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import __version__

GENESIS = "0" * 64
_CHUNK = 1024 * 1024


class EvidenceError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ChainReport:
    ok: bool
    entries: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.entries[-1]["entry_hash"] if self.entries else GENESIS


def verify_chain(log_path: str | Path) -> ChainReport:
    """Comprueba que el registro no fue editado, reordenado ni le faltan líneas intermedias."""
    log_path = Path(log_path)
    if not log_path.is_file():
        return ChainReport(ok=False, errors=[f"No existe el registro de evidencia: {log_path}"])
    report = ChainReport(ok=True)
    prev = GENESIS
    expected_seq = 1
    with log_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                report.errors.append(f"línea {lineno}: línea vacía (el registro fue editado)")
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                report.errors.append(f"línea {lineno}: JSON inválido")
                continue
            if entry.get("seq") != expected_seq:
                report.errors.append(
                    f"línea {lineno}: secuencia {entry.get('seq')} (se esperaba {expected_seq})"
                )
            if entry.get("prev_hash") != prev:
                report.errors.append(
                    f"línea {lineno}: prev_hash no coincide con la línea anterior "
                    "(línea eliminada, insertada o reordenada)"
                )
            if _entry_hash(entry) != entry.get("entry_hash"):
                report.errors.append(
                    f"línea {lineno}: entry_hash no coincide (contenido de la línea alterado)"
                )
            report.entries.append(entry)
            prev = entry.get("entry_hash", "")
            expected_seq = (entry.get("seq") or expected_seq) + 1
    report.ok = not report.errors
    return report


def _relpath(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()
    except ValueError:  # otra unidad en Windows
        return str(path.resolve())


def append_entries(
    log_path: str | Path, files: list[tuple[str, str, Path]], run_id: str
) -> list[dict]:
    """Registra (tipo, rol, ruta) de cada archivo. Se niega a escribir sobre un registro roto."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        chain = verify_chain(log_path)
        if not chain.ok:
            raise EvidenceError(
                "El registro de evidencia está dañado o fue manipulado; no se agregan entradas. "
                + "; ".join(chain.errors[:3])
            )
        prev, seq = chain.head, len(chain.entries)
    else:
        prev, seq = GENESIS, 0
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    new_entries = []
    for kind, role, path in files:
        path = Path(path)
        seq += 1
        entry = {
            "seq": seq,
            "timestamp": timestamp,
            "run_id": run_id,
            "kind": kind,
            "role": role,
            "file": _relpath(path, log_path.parent),
            "file_name": path.name,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "tool_version": __version__,
            "prev_hash": prev,
        }
        entry["entry_hash"] = _entry_hash(entry)
        prev = entry["entry_hash"]
        new_entries.append(entry)
    with log_path.open("a", encoding="utf-8") as fh:
        for entry in new_entries:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return new_entries


@dataclass
class FileVerification:
    path: Path
    status: str  # 'OK' | 'MODIFICADO' | 'NO_REGISTRADO' | 'NO_EXISTE'
    actual_sha256: str = ""
    entry: dict | None = None
    matched_by: str = ""  # 'ruta' | 'nombre'

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def verify_file(path: str | Path, chain: ChainReport, log_path: str | Path) -> FileVerification:
    """Compara el hash actual del archivo con la última entrada registrada para él."""
    path = Path(path)
    if not path.is_file():
        return FileVerification(path, "NO_EXISTE")
    actual = sha256_file(path)
    base = Path(log_path).parent
    by_path = [e for e in chain.entries if (base / e.get("file", "")).resolve() == path.resolve()]
    candidates, matched_by = by_path, "ruta"
    if not candidates:
        candidates, matched_by = (
            [e for e in chain.entries if e.get("file_name") == path.name],
            ("nombre"),
        )
    if not candidates:
        return FileVerification(path, "NO_REGISTRADO", actual)
    entry = candidates[-1]
    status = "OK" if entry.get("sha256") == actual else "MODIFICADO"
    return FileVerification(path, status, actual, entry, matched_by)
