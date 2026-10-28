"""Unit tests for declarative validation rules engine."""

import pytest
import pandas as pd

from opendataguard.rules import load_rules, validate_rule_config, execute_rule_suite


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "user_id": [1, 2, 3],
        "email": ["user1@test.com", "user2@test.com", "invalid-email"],
        "age": [25, 40, 150],
        "category": ["A", "B", "Z"],
    })


def test_load_rules_json_valid():
    config_json = """
    {
        "version": "1.0",
        "rules": [
            {"rule": "required", "column": "user_id"},
            {"rule": "range", "column": "age", "min": 0, "max": 120}
        ]
    }
    """
    config = load_rules(config_json)
    assert len(config["rules"]) == 2


def test_load_rules_yaml_valid():
    config_yaml = """
    version: "1.0"
    rules:
      - rule: required
        column: user_id
      - rule: allowed_values
        column: category
        values: [A, B, C]
    """
    config = load_rules(config_yaml)
    assert len(config["rules"]) == 2


def test_unsupported_rule_rejected():
    bad_config = {
        "rules": [
            {"rule": "unsupported_magic_check", "column": "age"}
        ]
    }
    with pytest.raises(ValueError, match="Unsupported rule type"):
        validate_rule_config(bad_config)


def test_malformed_rule_rejected():
    bad_config = {
        "rules": [
            {"rule": "allowed_values", "column": "category"}  # missing values
        ]
    }
    with pytest.raises(ValueError, match="requires a list of 'values'"):
        validate_rule_config(bad_config)


def test_execute_rule_suite(sample_df):
    config = {
        "rules": [
            {"rule": "required", "column": "user_id"},
            {"rule": "range", "column": "age", "min": 0, "max": 120},
            {"rule": "regex", "column": "email", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
            {"rule": "allowed_values", "column": "category", "values": ["A", "B"]},
        ]
    }
    results = execute_rule_suite(sample_df, config)
    assert len(results) == 4

    # Rule 0 (required user_id) should PASS
    assert results[0].passed

    # Rule 1 (age range) should FAIL on 150
    assert not results[1].passed
    assert results[1].failed_records == 1

    # Rule 2 (regex email) should FAIL on invalid-email
    assert not results[2].passed
    assert results[2].failed_records == 1

    # Rule 3 (allowed_values) should FAIL on 'Z'
    assert not results[3].passed
    assert results[3].failed_records == 1


def test_email_rule_suite():
    df = pd.DataFrame({"contact": ["good@test.com", "bad-email"]})
    config = {
        "rules": [
            {"rule": "email", "column": "contact"}
        ]
    }
    results = execute_rule_suite(df, config)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].failed_records == 1
    assert results[0].check_name == "email_format"


def test_invalid_regex_pattern_rejected():
    bad_config = {
        "rules": [
            {"rule": "regex", "column": "email", "pattern": "[invalid(regex"}
        ]
    }
    with pytest.raises(ValueError, match="Invalid regex pattern"):
        validate_rule_config(bad_config)


def test_load_rules_from_path(tmp_path):
    rule_file = tmp_path / "custom_rules.json"
    rule_file.write_text('{"version": "1.0", "rules": [{"rule": "duplicate_rows"}]}', encoding="utf-8")
    config = load_rules(rule_file)
    assert len(config["rules"]) == 1
    assert config["rules"][0]["rule"] == "duplicate_rows"


def test_load_rules_nonexistent_path(tmp_path):
    missing_file = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError, match="Rule file does not exist"):
        load_rules(missing_file)


def test_load_repo_sample_rules():
    from pathlib import Path
    repo_root = Path(__file__).parent.parent
    json_path = repo_root / "config" / "sample_rules.json"
    yaml_path = repo_root / "config" / "sample_rules.yaml"

    if json_path.is_file():
        cfg_json = load_rules(json_path)
        assert len(cfg_json["rules"]) >= 8

    if yaml_path.is_file():
        cfg_yaml = load_rules(yaml_path)
        assert len(cfg_yaml["rules"]) >= 8


def test_rule_suite_empty_strings_and_chronological():
    df = pd.DataFrame({
        "name": ["Alice", "   ", "Bob"],
        "joined": ["2023-01-01", "2023-02-01", "2023-01-15"],  # Jan 15 out of order
    })
    config = {
        "rules": [
            {"rule": "required", "column": "name", "treat_empty_as_missing": True},
            {"rule": "date_format", "column": "joined", "chronological": True},
        ]
    }
    results = execute_rule_suite(df, config)
    assert len(results) == 2
    # Rule 0 (name) should fail on whitespace
    assert not results[0].passed
    assert results[0].failed_records == 1

    # Rule 1 (joined) should fail on chronological sequence
    assert not results[1].passed
    assert results[1].failed_records == 1


def test_rule_suite_schema_strict():
    df = pd.DataFrame({"col_a": [1], "col_b": [2], "extra_col": [3]})
    strict_config = {
        "rules": [
            {"rule": "schema", "expected_columns": ["col_a", "col_b"], "strict": True}
        ]
    }
    results = execute_rule_suite(df, strict_config)
    assert len(results) == 1
    assert not results[0].passed
    assert "Unexpected extra columns" in results[0].message


def test_rule_suite_outliers_and_row_count():
    df = pd.DataFrame({"score": [10.0, 11.0, 10.5, 11.5, 95.0]})  # 95 is outlier, 5 rows
    config = {
        "rules": [
            {"rule": "row_count", "min_rows": 2, "max_rows": 10},
            {"rule": "outliers", "column": "score", "factor": 1.5},
        ]
    }
    results = execute_rule_suite(df, config)
    assert len(results) == 2
    # Row count passed
    assert results[0].passed
    # Outliers detected
    assert not results[1].passed
    assert results[1].failed_records == 1




