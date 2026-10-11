"""Casos pequeños escritos a mano para cada regla, incluidos los bordes."""

from conftest import acc, emp, run_case


def rules_of(result):
    return sorted({f.rule for f in result.findings})


# ---------- R1 ----------
def test_r1_severity_escalates_after_threshold(tmp_path):
    hr = [
        emp("001001", status="Baja", term="24/09/2026"),  # 7 días: ALTA (umbral exacto)
        emp("001002", status="Baja", term="2026-09-23"),  # 8 días: CRÍTICA
    ]
    ad = [acc("a1", "1001", logon="2026-09-20 10:00"), acc("a2", "1002", logon="2026-09-20")]
    r1 = {f.account: f for f in run_case(tmp_path, hr, ad).by_rule("R1")}
    assert (r1["a1"].severity, r1["a1"].days) == ("ALTA", 7)
    assert (r1["a2"].severity, r1["a2"].days) == ("CRÍTICA", 8)


def test_r1_threshold_is_configurable(tmp_path):
    hr = [emp("001001", status="Baja", term="2026-09-21")]  # 10 días
    ad = [acc("a1", "1001", logon="2026-09-01")]
    result = run_case(
        tmp_path, hr, ad, rules={"as_of": "2026-10-01", "termination_escalation_days": 30}
    )
    assert result.by_rule("R1")[0].severity == "ALTA"


def test_r1_future_termination_is_not_reported(tmp_path):
    hr = [emp("001001", status="Baja", term="2026-10-15")]
    result = run_case(tmp_path, hr, [acc("a1", "1001")])
    assert result.by_rule("R1") == []
    assert [x.reason for x in result.exclusions] == ["Baja programada para 2026-10-15"]


def test_r1_disabled_account_is_fine(tmp_path):
    hr = [emp("001001", status="Baja", term="2026-01-10")]
    result = run_case(tmp_path, hr, [acc("a1", "1001", enabled="False", logon="2026-01-05")])
    assert result.findings == []


def test_r1_without_termination_date(tmp_path):
    hr = [emp("001001", status="BAJA", term="")]
    result = run_case(tmp_path, hr, [acc("a1", "1001")])
    assert [(f.severity, f.days) for f in result.by_rule("R1")] == [("ALTA", None)]
    assert [f.issue for f in result.by_rule("R5")] == ["terminated_without_date"]


# ---------- R6 ----------
def test_r6_logon_after_termination_is_critical(tmp_path):
    hr = [
        emp("001001", status="Baja", term="2026-09-28"),  # 3 días: R1 sería ALTA
        emp("001002", status="Baja", term="2026-08-01"),
    ]
    ad = [
        acc("a1", "1001", logon="2026-09-30 22:10:00"),
        acc("a2", "1002", enabled="False", logon="2026-08-05 08:00:00"),
    ]
    result = run_case(tmp_path, hr, ad)
    assert result.by_rule("R1")[0].severity == "CRÍTICA"  # se eleva por el inicio de sesión
    assert sorted(f.account for f in result.by_rule("R6")) == ["a1", "a2"]
    assert {f.severity for f in result.by_rule("R6")} == {"CRÍTICA"}


def test_r6_r7_skipped_without_last_logon_column(tmp_path):
    hr = [emp("001001", status="Baja", term="2026-01-01"), emp("001002")]
    ad = [acc("a1", "1001"), acc("a2", "1002")]
    result = run_case(tmp_path, hr, ad, with_logon=False)
    assert set(result.skipped_rules) == {"R6", "R7"}
    assert rules_of(result) == ["R1"]


# ---------- R2 / R2b ----------
def test_r2_and_r2b(tmp_path):
    hr = [
        emp("001001"),
        emp("001002"),
        emp("001003", title="Pasante"),
        emp("001004", hire="2026-11-01"),
    ]
    ad = [acc("a2", "1002", enabled="False")]
    result = run_case(tmp_path, hr, ad)
    assert [f.employee_id for f in result.by_rule("R2")] == ["001001"]
    assert [f.account for f in result.by_rule("R2b")] == ["a2"]
    reasons = sorted(x.reason for x in result.exclusions)
    assert reasons == ["Alta programada para 2026-11-01", "Cargo sin cuenta obligatoria: Pasante"]


def test_r2_matches_by_email_when_id_missing(tmp_path):
    hr = [emp("001001", email="ana.munoz@x.example")]
    ad = [acc("amunoz", "", email="ANA.MUNOZ@X.EXAMPLE")]
    result = run_case(tmp_path, hr, ad)
    assert result.by_rule("R2") == [] and result.by_rule("R4") == []
    assert [f.issue for f in result.by_rule("R5")] == ["matched_by_email"]


# ---------- R3 ----------
def test_r3_normalization_avoids_false_positives(tmp_path):
    hr = [
        emp(" 1001 ", title="Analista de Nómina", dept="  Gestión   Humana ", email="Ana@X.example")
    ]
    ad = [
        acc(
            "a1", "001001", title="ANALISTA DE NOMINA", dept="gestion humana", email="ana@x.example"
        )
    ]
    assert run_case(tmp_path, hr, ad).findings == []


def test_r3_reports_each_attribute(tmp_path):
    hr = [
        emp("000100", name="Jefa Uno"),
        emp("000200", name="Jefe Dos"),
        emp("001001", title="Contador", dept="Finanzas", boss="100", email="n@x.example"),
    ]
    ad = [
        acc("jefa1", "100", name="Jefa Uno"),
        acc("jefe2", "200", name="Jefe Dos"),
        acc(
            "a1",
            "1001",
            title="Asistente",
            dept="Bodega",
            boss="CN=Jefe Dos,OU=Finanzas,DC=x,DC=example",
            email="viejo@x.example",
        ),
    ]
    result = run_case(tmp_path, hr, ad)
    drift = {f.issue: f for f in result.by_rule("R3")}
    assert set(drift) == {"title", "department", "manager", "email"}
    assert drift["manager"].hr_value == "000100 (Jefa Uno)"
    assert "000200 (Jefe Dos)" in drift["manager"].detail


def test_r3_manager_formats_dn_account_and_id(tmp_path):
    hr = [
        emp("000100", name="Jefa Muñoz"),
        emp("001001", boss="100"),
        emp("001002", boss="000100"),
        emp("001003", boss="100"),
        emp("001004", boss="100"),
    ]
    ad = [
        acc("jmunoz", "100", name="Jefa Muñoz"),
        acc("a1", "1001", boss="CN=Jefa Muñoz,OU=TI,DC=x,DC=example"),
        acc("a2", "1002", boss="jmunoz"),
        acc("a3", "1003", boss="000100"),
        acc("a4", "1004", boss="CN=jmunoz,OU=TI,DC=x"),
    ]  # CN igual a la cuenta
    assert run_case(tmp_path, hr, ad).by_rule("R3") == []


def test_r3_empty_value_is_low_severity(tmp_path):
    hr = [emp("001001", dept="Finanzas")]
    ad = [acc("a1", "1001", dept="")]
    (finding,) = run_case(tmp_path, hr, ad).by_rule("R3")
    assert (finding.issue, finding.severity) == ("department", "BAJA")


def test_r3_only_configured_attributes(tmp_path):
    hr = [emp("001001", title="Contador")]
    ad = [acc("a1", "1001", title="Asistente", email="otro@x.example")]
    result = run_case(tmp_path, hr, ad, compare_attributes=["title"])
    assert [f.issue for f in result.by_rule("R3")] == ["title"]


# ---------- R4 ----------
def test_r4_orphans_and_exclusions(tmp_path):
    hr = [emp("001001")]
    ad = [
        acc("a1", "1001"),
        acc("fantasma", "999999"),
        acc("viejo", "", enabled="False"),
        acc("svc_backup", ""),
        acc("scanner.piso3", ""),
        acc("recepcion.general", ""),
    ]
    result = run_case(tmp_path, hr, ad)
    sev = {f.account: f.severity for f in result.by_rule("R4")}
    assert sev == {"fantasma": "ALTA", "viejo": "BAJA"}
    assert sorted(x.identifier for x in result.exclusions) == [
        "recepcion.general",
        "scanner.piso3",
        "svc_backup",
    ]


def test_excluded_employee_ids_skip_all_rules(tmp_path):
    hr = [emp("001001", status="Baja", term="2025-01-01")]
    ad = [acc("a1", "1001")]
    result = run_case(tmp_path, hr, ad, exclusions={"employee_ids": ["1001"]})
    assert result.findings == []
    assert [x.reason for x in result.exclusions] == ["Empleado en lista de exclusiones"]


# ---------- R5 ----------
def test_r5_duplicates(tmp_path):
    hr = [
        emp("001001", status="Baja", term="2020-01-01", email="a@x.example"),
        emp("1001", email="a@x.example"),  # reingreso: misma persona, mismo correo
        emp("001002", email="dup@x.example"),
        emp("001003", email="dup@x.example"),
        emp("", name="Sin Código"),
        emp("001004", status="Vacaciones"),
    ]
    ad = [
        acc("a1", "1001", email="a@x.example"),
        acc("a1b", "1001", email="a@x.example"),
        acc("b", "1002", email="dup@x.example"),
        acc("c", "1003", email="dup@x.example"),
        acc("d", "1004"),
    ]
    result = run_case(tmp_path, hr, ad)
    issues = sorted(f.issue for f in result.by_rule("R5"))
    assert issues == [
        "duplicate_email_directory",
        "duplicate_email_hr",
        "duplicate_hr_id",
        "missing_employee_id",
        "multiple_enabled_accounts",
        "unknown_status",
    ]
    # El reingreso se concilia con la fila vigente: no hay R1.
    assert result.by_rule("R1") == []
    # Correo compartido por el mismo empleado (a1, a1b) no cuenta como duplicado.
    dup_dir = [f for f in result.by_rule("R5") if f.issue == "duplicate_email_directory"]
    assert dup_dir[0].account == "b, c"


# ---------- R7 ----------
def test_r7_stale_and_recent_hires(tmp_path):
    hr = [
        emp("001001"),
        emp("001002"),
        emp("001003", hire="2026-09-15"),
        emp("001004"),
        emp("001005", status="Baja", term="2026-01-01"),
    ]
    ad = [
        acc("viejo", "1001", logon="2026-05-01 08:00"),  # 153 días
        acc("limite", "1002", logon="2026-07-03 08:00"),  # 90 días: no supera el límite
        acc("nuevo", "1003", logon=""),  # alta reciente
        acc("nunca", "1004", logon=""),
        acc("baja", "1005", enabled="False", logon="2025-12-01"),
    ]
    result = run_case(tmp_path, hr, ad)
    assert sorted(f.account for f in result.by_rule("R7")) == ["nunca", "viejo"]
    days = {f.account: f.days for f in result.by_rule("R7")}
    assert days["viejo"] == 153


def test_r7_days_configurable(tmp_path):
    hr = [emp("001001")]
    ad = [acc("a1", "1001", logon="2026-08-01")]
    result = run_case(tmp_path, hr, ad, rules={"as_of": "2026-10-01", "stale_account_days": 30})
    assert [f.account for f in result.by_rule("R7")] == ["a1"]
