"""Cada regla contra los casos trampa del generador (conjuntos esperados exactos)."""

from collections import Counter

from conftest import account_names, employee_ids


def test_r1_terminated_with_enabled_account(sample):
    result, exp, _ = sample
    assert employee_ids(result, "R1", severity="CRÍTICA") == exp["R1"]["critical"]
    assert employee_ids(result, "R1", severity="ALTA") == exp["R1"]["high"]


def test_r1_scheduled_terminations_not_reported(sample):
    result, exp, _ = sample
    reported = set(employee_ids(result, "R1"))
    assert not reported & set(exp["excluded"]["scheduled_termination"])


def test_r2_active_without_account(sample):
    result, exp, _ = sample
    assert employee_ids(result, "R2") == exp["R2"]


def test_r2_excludes_interns_and_future_hires(sample):
    result, exp, _ = sample
    reported = set(employee_ids(result, "R2")) | set(employee_ids(result, "R2b"))
    assert not reported & set(exp["excluded"]["no_account_required"])
    assert not reported & set(exp["excluded"]["scheduled_hire"])


def test_r2b_active_with_only_disabled_accounts(sample):
    result, exp, _ = sample
    assert employee_ids(result, "R2b") == exp["R2b"]


def test_r3_attribute_drift_per_attribute(sample):
    result, exp, _ = sample
    for attr, ids in exp["R3"].items():
        assert employee_ids(result, "R3", issue=attr) == ids, attr


def test_r3_ignores_cosmetic_noise(sample):
    """Tildes, mayúsculas, espacios y formatos de ID no deben generar hallazgos."""
    result, exp, _ = sample
    noisy = set(exp["no_findings"])
    flagged = {f.employee_id for f in result.findings}
    from conftest import nid

    assert not noisy & {nid(x) for x in flagged if x}


def test_r3_manager_dn_is_resolved(sample):
    """El jefe viene como DN, cuenta o código; sin cambios reales no hay hallazgos 'no resuelto'."""
    result, _, _ = sample
    unresolved = [f for f in result.findings if f.rule == "R3" and "No se pudo" in f.detail]
    assert unresolved == []


def test_r4_orphan_accounts_exclude_service_accounts(sample):
    result, exp, _ = sample
    assert account_names(result, "R4") == exp["R4"]
    enabled = sorted(f.account for f in result.by_rule("R4") if f.severity == "ALTA")
    assert enabled == exp["R4_enabled"]
    service = set(exp["excluded"]["service_accounts"]) | set(exp["excluded"]["special_accounts"])
    for rule in ("R4", "R7"):
        assert not set(account_names(result, rule)) & service


def test_r5_data_quality(sample):
    result, exp, _ = sample
    r5 = exp["R5"]
    for issue in (
        "duplicate_hr_id",
        "multiple_enabled_accounts",
        "unknown_status",
        "matched_by_email",
        "terminated_without_date",
        "status_date_inconsistent",
    ):
        assert employee_ids(result, "R5", issue=issue) == r5[issue], issue
    issues = Counter(f.issue for f in result.by_rule("R5"))
    assert issues["missing_employee_id"] == r5["missing_employee_id"]
    assert (
        sorted(f.hr_value for f in result.by_rule("R5") if f.issue == "duplicate_email_hr")
        == r5["duplicate_email_hr"]
    )
    assert (
        sorted(
            f.directory_value
            for f in result.by_rule("R5")
            if f.issue == "duplicate_email_directory"
        )
        == r5["duplicate_email_directory"]
    )


def test_r6_logon_after_termination(sample):
    result, exp, _ = sample
    assert account_names(result, "R6") == exp["R6"]
    assert {f.severity for f in result.by_rule("R6")} == {"CRÍTICA"}


def test_r7_stale_accounts(sample):
    result, exp, _ = sample
    assert account_names(result, "R7") == exp["R7"]


def test_exclusions_are_listed(sample):
    result, exp, _ = sample
    accounts = {x.identifier for x in result.exclusions if x.kind == "cuenta"}
    assert accounts == set(exp["excluded"]["service_accounts"]) | set(
        exp["excluded"]["special_accounts"]
    )
    reasons = Counter(x.scope for x in result.exclusions if x.kind == "empleado")
    assert reasons["R1"] == len(exp["excluded"]["scheduled_termination"])
    assert reasons["R2/R2b"] == len(exp["excluded"]["no_account_required"]) + len(
        exp["excluded"]["scheduled_hire"]
    )
