"""Genera las capturas del README a partir de una ejecución con los datos de ejemplo.

Uso:  python scripts/make_screenshots.py
Requiere: pip install -e '.[screenshots]' y un Chromium para Playwright. Para las capturas
del Excel usa LibreOffice (soffice) si está instalado.
Variable opcional CHROMIUM_PATH para usar un Chromium ya instalado.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

from hrrecon.config import load_config
from hrrecon.runner import run

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
AS_OF = "2026-10-01"


def html_shots(html: Path) -> None:
    exe = os.environ.get("CHROMIUM_PATH")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page.goto(html.as_uri())
        top = page.locator("#R1").bounding_box()["y"] - 40
        page.screenshot(
            path=IMG / "reporte_resumen.png", clip={"x": 0, "y": 0, "width": 1280, "height": top}
        )
        for code, name in (("R1", "reporte_detalle_r1.png"), ("R3", "reporte_detalle_r3.png")):
            section = page.locator(f"#{code}")
            box = section.bounding_box()
            height = min(box["height"], 640)
            page.screenshot(
                path=IMG / name,
                full_page=True,
                clip={
                    "x": box["x"] - 16,
                    "y": box["y"] - 12,
                    "width": box["width"] + 32,
                    "height": height + 12,
                },
            )
        dark = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
        dark.goto(html.as_uri())
        dark.screenshot(path=IMG / "reporte_oscuro.png")
        browser.close()


def excel_shots(xlsx: Path) -> None:
    soffice = shutil.which("soffice")
    if not soffice:
        print("soffice no disponible: se omiten las capturas del Excel")
        return
    for sheet, name in (("Resumen", "excel_resumen.png"), ("R1 Bajas con cuenta", "excel_r1.png")):
        with tempfile.TemporaryDirectory() as tmp:
            wb = load_workbook(xlsx)
            for ws in list(wb.worksheets):
                if ws.title != sheet:
                    wb.remove(ws)
            single = Path(tmp) / "hoja.xlsx"
            wb.save(single)
            subprocess.run(
                [soffice, "--headless", "--convert-to", "png", "--outdir", tmp, str(single)],
                check=True,
                capture_output=True,
            )
            _crop(Path(tmp) / "hoja.png", IMG / name)


def _crop(src: Path, dst: Path, margin: int = 24) -> None:
    """Recorta el margen blanco de la página exportada por LibreOffice."""
    from PIL import Image, ImageChops

    img = Image.open(src).convert("RGB")
    bbox = ImageChops.difference(img, Image.new("RGB", img.size, "white")).getbbox()
    if bbox:
        left, top, right, bottom = bbox
        img = img.crop(
            (
                max(left - margin, 0),
                max(top - margin, 0),
                min(right + margin, img.width),
                min(bottom + margin, img.height),
            )
        )
    img.save(dst)


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        cfg.output.dir = Path(tmp)
        cfg.output.evidence_log = Path(tmp) / "evidence_log.jsonl"
        from datetime import date

        out = run(cfg, as_of=date.fromisoformat(AS_OF), run_id="demo")
        html_shots(out.html)
        excel_shots(out.excel)
    print(f"Capturas en {IMG}")


if __name__ == "__main__":
    main()
