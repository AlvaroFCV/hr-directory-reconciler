"""Generación de reportes HTML y Excel."""

from .excel import write_excel
from .html import render_html, write_html

__all__ = ["render_html", "write_html", "write_excel"]
