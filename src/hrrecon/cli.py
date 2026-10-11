"""Interfaz de línea de comandos: hrrecon generate | reconcile | verify."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .evidence import EvidenceError, verify_chain, verify_file
from .loader import InputError
from .models import SEVERITY_ORDER
from .report.common import SEVERITIES, categories, severity_totals

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 2, 1


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"fecha inválida (use AAAA-MM-DD): {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hrrecon",
        description="Conciliador de SOLO LECTURA entre nómina de RR.HH. y directorio de usuarios.",
    )
    parser.add_argument("--version", action="version", version=f"hrrecon {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="genera datos ficticios con casos trampa")
    g.add_argument("--out", type=Path, default=Path("data/sample"), help="carpeta de salida")
    g.add_argument("--employees", type=int, default=500, help="número de empleados (mín. 250)")
    g.add_argument("--seed", type=int, default=42, help="semilla para resultados reproducibles")
    g.add_argument("--as-of", type=_date, help="fecha de referencia (AAAA-MM-DD); por defecto hoy")

    r = sub.add_parser("reconcile", help="concilia y genera reportes HTML/Excel con evidencia")
    r.add_argument("--config", "-c", type=Path, required=True, help="archivo YAML")
    r.add_argument("--hr", type=Path, help="sobrescribe hr.file")
    r.add_argument("--directory", type=Path, help="sobrescribe directory.file")
    r.add_argument("--out", type=Path, help="sobrescribe output.dir")
    r.add_argument("--log", type=Path, help="sobrescribe output.evidence_log")
    r.add_argument("--as-of", type=_date, help="fecha de corte (AAAA-MM-DD)")
    r.add_argument(
        "--fail-on",
        choices=[s.lower() for s in SEVERITIES],
        help="termina con código 2 si hay hallazgos de esta severidad o mayor (útil en CI)",
    )

    v = sub.add_parser("verify", help="verifica que reportes no fueron modificados")
    v.add_argument("files", nargs="*", type=Path, help="reportes a verificar")
    v.add_argument(
        "--log",
        type=Path,
        default=Path("output/evidence_log.jsonl"),
        help="registro de evidencia (por defecto output/evidence_log.jsonl)",
    )
    v.add_argument("--head", help="último entry_hash conocido (detecta truncamiento del registro)")
    return parser


def cmd_generate(args) -> int:
    from .generator import generate

    exp = generate(args.out, n_employees=args.employees, seed=args.seed, as_of=args.as_of)
    print(f"Datos ficticios generados en {args.out} (fecha de referencia {exp['as_of']}):")
    print(f"  nomina.xlsx       {exp['hr_rows']} filas")
    print(f"  directorio.csv    {exp['directory_rows']} cuentas")
    print("  expected_traps.json  casos trampa esperados por regla")
    return EXIT_OK


def cmd_reconcile(args) -> int:
    from .runner import run

    cfg = load_config(args.config)
    if args.hr:
        cfg.hr.file = args.hr.resolve()
    if args.directory:
        cfg.directory.file = args.directory.resolve()
    if args.out:
        cfg.output.dir = args.out.resolve()
        if not args.log:
            cfg.output.evidence_log = cfg.output.dir / "evidence_log.jsonl"
    if args.log:
        cfg.output.evidence_log = args.log.resolve()
    out = run(cfg, as_of=args.as_of)
    res = out.result

    print(f"Conciliación (solo lectura) · fecha de corte {res.as_of} · ejecución {out.run_id}")
    for warning in res.warnings:
        print(f"  aviso: {warning}")
    print()
    print(f"  {'Regla':<6}{'Categoría':<44}{'Total':>6}")
    for c in categories(res):
        total = "omitida" if c.skipped else str(c.total)
        print(f"  {c.rule.code:<6}{c.rule.title:<44}{total:>6}")
    totals = severity_totals(res)
    print()
    print("  " + " · ".join(f"{s.capitalize()}: {n}" for s, n in totals.items()))
    print()
    print(f"Reporte HTML:  {out.html}")
    print(f"Reporte Excel: {out.excel}")
    print(f"Evidencia:     {out.evidence_log}")
    print(f"Cabeza del registro (guárdela aparte para detectar truncamiento): {out.evidence_head}")

    if args.fail_on:
        limit = SEVERITY_ORDER[args.fail_on.upper()]
        if any(SEVERITY_ORDER[f.severity] <= limit for f in res.findings):
            return EXIT_FINDINGS
    return EXIT_OK


def cmd_verify(args) -> int:
    chain = verify_chain(args.log)
    ok = chain.ok
    if chain.ok:
        print(f"Registro de evidencia íntegro: {len(chain.entries)} entradas encadenadas.")
    else:
        print("REGISTRO DE EVIDENCIA MANIPULADO O DAÑADO:")
        for err in chain.errors:
            print(f"  - {err}")
    if args.head:
        if chain.head == args.head:
            print("La cabeza del registro coincide con el valor de referencia.")
        else:
            ok = False
            print(
                "LA CABEZA DEL REGISTRO NO COINCIDE: faltan entradas finales o el registro "
                f"fue reemplazado (actual {chain.head})."
            )
    for path in args.files:
        res = verify_file(path, chain, args.log)
        if res.status == "OK":
            e = res.entry
            print(
                f"OK          {path}  (sha256 {res.actual_sha256[:16]}…, registrado "
                f"{e['timestamp']}, ejecución {e['run_id']}, por {res.matched_by})"
            )
        elif res.status == "MODIFICADO":
            print(
                f"MODIFICADO  {path}  (actual {res.actual_sha256[:16]}…, registrado "
                f"{res.entry['sha256'][:16]}…)"
            )
        elif res.status == "NO_REGISTRADO":
            print(f"NO REGISTRADO  {path}  (sha256 {res.actual_sha256[:16]}…)")
        else:
            print(f"NO EXISTE   {path}")
        ok = ok and res.ok
    if not args.files and not args.head and chain.ok:
        print("(Indique uno o más reportes para verificar su hash.)")
    return EXIT_OK if ok else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"generate": cmd_generate, "reconcile": cmd_reconcile, "verify": cmd_verify}
    try:
        return handlers[args.command](args)
    except (ConfigError, InputError, EvidenceError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
