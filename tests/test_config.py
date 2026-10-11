from pathlib import Path

import pytest

from hrrecon.config import ConfigError, config_from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]


def minimal(**overrides):
    data = {
        "hr": {"file": "hr.csv", "columns": {"employee_id": "ID", "status": "Estado"}},
        "directory": {"file": "ad.csv", "columns": {"account": "sam", "enabled": "En"}},
    }
    data.update(overrides)
    return data


def test_example_config_loads():
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    assert cfg.hr.file == ROOT / "data" / "sample" / "nomina.xlsx"
    assert cfg.directory.columns["last_logon"] == "LastLogonDate"
    assert cfg.rules.termination_escalation_days == 7
    assert cfg.rules.stale_account_days == 90
    assert cfg.id_options.zfill == 6


def test_paths_relative_to_config(tmp_path):
    cfg = config_from_dict(minimal(), tmp_path)
    assert cfg.hr.file == tmp_path / "hr.csv"
    assert cfg.output.evidence_log == tmp_path / "output" / "evidence_log.jsonl"


def test_missing_required_column_mapping(tmp_path):
    data = minimal()
    del data["hr"]["columns"]["status"]
    with pytest.raises(ConfigError, match="status"):
        config_from_dict(data, tmp_path)


def test_unknown_field_rejected(tmp_path):
    data = minimal()
    data["hr"]["columns"]["salario"] = "Sueldo"
    with pytest.raises(ConfigError, match="salario"):
        config_from_dict(data, tmp_path)


def test_bad_values_rejected(tmp_path):
    with pytest.raises(ConfigError):
        config_from_dict(minimal(compare_attributes=["telefono"]), tmp_path)
    with pytest.raises(ConfigError):
        config_from_dict(minimal(matching={"keys": ["nombre"]}), tmp_path)
    with pytest.raises(ConfigError):
        config_from_dict(minimal(rules={"as_of": "ayer"}), tmp_path)
