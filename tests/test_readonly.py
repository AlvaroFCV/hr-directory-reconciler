"""Garantía de solo lectura: el paquete no importa módulos de red ni de directorio."""

import ast
from pathlib import Path

import hrrecon

FORBIDDEN = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "ldap",
    "ldap3",
    "pyad",
    "win32com",
    "subprocess",
    "paramiko",
}


def test_no_network_or_directory_modules():
    src = Path(hrrecon.__file__).parent
    offenders = []
    for file in src.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in FORBIDDEN:
                    offenders.append(f"{file.name}: {name}")
    assert offenders == []


def test_inputs_are_not_modified(sample):
    """Conciliar no altera los archivos de entrada (mismo hash antes y después)."""
    from hrrecon.engine import reconcile
    from hrrecon.evidence import sha256_file

    _, _, cfg = sample
    before = {p: sha256_file(p) for p in (cfg.hr.file, cfg.directory.file)}
    reconcile(cfg)
    assert {p: sha256_file(p) for p in before} == before
