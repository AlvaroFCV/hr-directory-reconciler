"""Normalización de valores antes de comparar.

Todas las comparaciones se hacen sobre valores normalizados; los reportes muestran
siempre el valor original tal como venía en la exportación.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

_WS_RE = re.compile(r"\s+")
_FLOAT_INT_RE = re.compile(r"^(\d+)\.0+$")

DEFAULT_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y",
)


@dataclass(frozen=True)
class TextOptions:
    strip_accents: bool = True
    casefold: bool = True
    collapse_spaces: bool = True


@dataclass(frozen=True)
class IdOptions:
    zfill: int = 0
    strip_non_digits: bool = False
    uppercase: bool = True
    remove_chars: str = " -."


DEFAULT_TEXT = TextOptions()
DEFAULT_ID = IdOptions()


def is_blank(value: object) -> bool:
    """True para None, NaN, NaT y cadenas vacías o solo con espacios."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if type(value).__name__ in ("NaTType", "NAType"):
        return True
    return isinstance(value, str) and value.strip() == ""


def to_str(value: object) -> str:
    """Convierte un valor de celda a texto sin perder información (vacío -> "")."""
    if is_blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos: 'Peñaherrera Gestión' -> 'Penaherrera Gestion'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(value: object, opts: TextOptions = DEFAULT_TEXT) -> str:
    """Normaliza texto libre (cargo, departamento, nombres) para comparar."""
    text = to_str(value)
    # Espacios no separables y similares que suelen venir de Excel.
    text = text.replace(" ", " ").strip()
    if opts.collapse_spaces:
        text = _WS_RE.sub(" ", text)
    if opts.strip_accents:
        text = strip_accents(text)
    if opts.casefold:
        text = text.casefold()
    return text


def normalize_id(value: object, opts: IdOptions = DEFAULT_ID) -> str:
    """Normaliza un identificador de empleado.

    Maneja los formatos típicos de exportación: ' 4512 ', '004512', '4512.0' (número
    convertido por Excel), 'emp-4512' (con ``strip_non_digits``).
    """
    text = to_str(value).replace(" ", " ").strip()
    if not text:
        return ""
    match = _FLOAT_INT_RE.match(text)
    if match:
        text = match.group(1)
    for ch in opts.remove_chars:
        text = text.replace(ch, "")
    if opts.strip_non_digits:
        text = re.sub(r"\D", "", text)
    if opts.uppercase:
        text = text.upper()
    if text.isdigit():
        # '0004512' y '4512' representan el mismo código.
        text = text.lstrip("0") or "0"
        if opts.zfill:
            text = text.zfill(opts.zfill)
    return text


def normalize_email(value: object) -> str:
    text = to_str(value).replace(" ", " ").strip()
    text = re.sub(r"^mailto:", "", text, flags=re.IGNORECASE)
    return text.replace(" ", "").casefold()


def normalize_account(value: object) -> str:
    """Normaliza un nombre de cuenta (sAMAccountName). Quita un prefijo DOMINIO\\ si existe."""
    text = to_str(value).strip()
    if "\\" in text:
        text = text.split("\\", 1)[1]
    return text.casefold()


def parse_bool(value: object, true_values: list[str] | tuple[str, ...]) -> bool:
    if isinstance(value, bool):
        return value
    text = normalize_text(value)
    return text in {normalize_text(v) for v in true_values}


def parse_datetime(
    value: object, formats: tuple[str, ...] | list[str] = DEFAULT_DATE_FORMATS
) -> datetime | None:
    """Convierte una celda (texto, fecha de Excel o Timestamp) a datetime. Vacío -> None."""
    if is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = to_str(value).strip()
    # ISO con zona horaria o fracciones de segundo.
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_date(
    value: object, formats: tuple[str, ...] | list[str] = DEFAULT_DATE_FORMATS
) -> date | None:
    parsed = parse_datetime(value, formats)
    return parsed.date() if parsed else None


def split_dn(dn: str) -> list[tuple[str, str]]:
    """Divide un Distinguished Name en pares (atributo, valor) respetando comas escapadas.

    'CN=Muñoz\\, Andrés,OU=TI,DC=x' -> [('CN', 'Muñoz, Andrés'), ('OU', 'TI'), ('DC', 'x')]
    """
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in dn:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    result = []
    for part in parts:
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        result.append((key.strip().upper(), val.strip()))
    return result


def is_dn(value: object) -> bool:
    text = to_str(value).strip()
    return bool(re.match(r"^\s*CN\s*=", text, flags=re.IGNORECASE)) and "=" in text


def manager_reference(value: object) -> str:
    """Extrae la referencia del jefe: el CN si viene como DN, o el valor tal cual."""
    text = to_str(value).strip()
    if is_dn(text):
        for key, val in split_dn(text):
            if key == "CN":
                return val
    return text
