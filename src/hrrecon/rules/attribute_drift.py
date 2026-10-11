"""R3: diferencias de cargo, departamento, jefe o correo entre nómina y directorio."""

from __future__ import annotations

from ..engine import ACTIVE, Context
from ..normalize import normalize_email
from .base import finding

CODE = "R3"
LABELS = {"title": "cargo", "department": "departamento", "manager": "jefe", "email": "correo"}
# atributo -> (campo en nómina, campo en directorio)
FIELDS = {
    "title": ("title", "title"),
    "department": ("department", "department"),
    "manager": ("manager_id", "manager"),
    "email": ("email", "email"),
}


def available_attributes(ctx: Context) -> list[str]:
    attrs = []
    for attr in ctx.cfg.compare_attributes:
        hr_field, dir_field = FIELDS[attr]
        if hr_field in ctx.data.hr_fields and dir_field in ctx.data.directory_fields:
            attrs.append(attr)
        else:
            ctx.skipped[f"R3 ({LABELS[attr]})"] = "Falta la columna en una de las exportaciones."
    return attrs


def _manager_label(ctx: Context, key: str) -> str:
    boss = ctx.primary.get(key)
    return f"{key} ({boss.name})" if boss else key


def run(ctx: Context) -> list:
    attrs = available_attributes(ctx)
    out = []
    for e in ctx.subjects():
        if ctx.state(e) != ACTIVE:
            continue
        for a in ctx.accounts(e):
            if not a.enabled:
                continue
            for attr in attrs:
                hr_field, dir_field = FIELDS[attr]
                hr_raw, dir_raw = e.raw.get(hr_field, ""), a.raw.get(dir_field, "")
                if attr == "manager":
                    resolved = ctx.resolve_manager(dir_raw, a.manager_ref)
                    if resolved == e.manager_key:
                        continue
                    hr_shown = _manager_label(ctx, e.manager_key) if e.manager_key else ""
                    if resolved is None:
                        detail = "No se pudo identificar en el directorio al jefe indicado."
                    else:
                        detail = (
                            f"Jefe distinto: nómina {hr_shown or '(vacío)'}, "
                            f"directorio {_manager_label(ctx, resolved) or '(vacío)'}."
                        )
                    empty = not e.manager_key or not dir_raw.strip()
                    out.append(
                        finding(
                            CODE,
                            "BAJA" if empty else "MEDIA",
                            attr,
                            detail,
                            e,
                            a,
                            hr_value=hr_shown,
                            directory_value=dir_raw,
                        )
                    )
                    continue
                if attr == "email":
                    equal = normalize_email(hr_raw) == normalize_email(dir_raw)
                else:
                    equal = ctx.text_equal(hr_raw, dir_raw)
                if equal:
                    continue
                empty = not hr_raw.strip() or not dir_raw.strip()
                if empty:
                    side = "nómina" if not hr_raw.strip() else "directorio"
                    detail = f"{LABELS[attr].capitalize()} vacío en {side}."
                else:
                    detail = f"{LABELS[attr].capitalize()} distinto entre nómina y directorio."
                out.append(
                    finding(
                        CODE,
                        "BAJA" if empty else "MEDIA",
                        attr,
                        detail,
                        e,
                        a,
                        hr_value=hr_raw,
                        directory_value=dir_raw,
                    )
                )
    return out
