from datetime import date, datetime

import pytest

from hrrecon.normalize import (
    IdOptions,
    TextOptions,
    is_blank,
    manager_reference,
    normalize_account,
    normalize_email,
    normalize_id,
    normalize_text,
    parse_bool,
    parse_date,
    parse_datetime,
    split_dn,
)


@pytest.mark.parametrize(
    "a, b",
    [
        ("Gestión Humana", "GESTION HUMANA"),
        ("  Tecnología  ", "tecnologia"),
        ("Analista   de\tNómina", "analista de nomina"),
        ("Peñaherrera", "PENAHERRERA"),
        ("Jefe Comercial", "jefe comercial"),
    ],
)
def test_text_equivalences(a, b):
    assert normalize_text(a) == normalize_text(b)


def test_text_options_can_keep_accents():
    opts = TextOptions(strip_accents=False)
    assert normalize_text("Gestión", opts) != normalize_text("Gestion", opts)


@pytest.mark.parametrize("raw", ["4512", "004512", " 4512 ", "4512.0", 4512, 4512.0, "0004512"])
def test_id_formats_converge(raw):
    assert normalize_id(raw, IdOptions(zfill=6)) == "004512"


def test_id_alphanumeric_and_blank():
    assert normalize_id("emp-4512", IdOptions()) == "EMP4512"
    assert normalize_id("emp-4512", IdOptions(strip_non_digits=True, zfill=6)) == "004512"
    assert normalize_id("", IdOptions(zfill=6)) == ""
    assert normalize_id(None) == ""


def test_email_and_account():
    assert normalize_email(" Andres.Munoz@Comercialandina.EXAMPLE ") == (
        "andres.munoz@comercialandina.example"
    )
    assert normalize_email("mailto:a@b.example") == "a@b.example"
    assert normalize_account("ANDINA\\AMunoz") == "amunoz"


def test_blank_detection():
    assert is_blank(None) and is_blank("  ") and is_blank(float("nan"))
    assert not is_blank("0")


def test_parse_bool():
    values = ["true", "1", "habilitado"]
    assert parse_bool("TRUE", values) and parse_bool(" Habilitado ", values)
    assert not parse_bool("False", values) and not parse_bool("", values)


def test_parse_dates():
    assert parse_date("05/03/2026") == date(2026, 3, 5)  # día primero (formato Ecuador)
    assert parse_date("2026-03-05") == date(2026, 3, 5)
    assert parse_date("2026-03-05 00:00:00") == date(2026, 3, 5)
    assert parse_date(datetime(2026, 3, 5, 10, 0)) == date(2026, 3, 5)
    assert parse_datetime("2026-03-05 08:15:22") == datetime(2026, 3, 5, 8, 15, 22)
    assert parse_date("") is None and parse_date("no es fecha") is None


def test_dn_parsing():
    dn = "CN=Andrés Muñoz Peñaherrera,OU=Tecnología,OU=Usuarios,DC=comercialandina,DC=example"
    assert manager_reference(dn) == "Andrés Muñoz Peñaherrera"
    assert split_dn("CN=Muñoz\\, Andrés,OU=TI")[0] == ("CN", "Muñoz, Andrés")
    assert manager_reference("cn = Ana Paz ,OU=X") == "Ana Paz"
    # Valores que no son DN se devuelven tal cual (cuenta o código de empleado).
    assert manager_reference("amunoz") == "amunoz"
    assert manager_reference("004512") == "004512"
