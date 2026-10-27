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
