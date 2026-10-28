"""Declarative validation rule configuration and execution engine for OpenDataGuard.

Supports JSON and YAML rule specifications with strict schema validation,
clear error reporting for unsupported rules or malformed parameters,
and unified execution across DataFrames.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import yaml

from opendataguard.logging_config import logger
from opendataguard.validators import (
    ValidationResult,
    _extract_sample,
    check_allowed_values,
    check_data_types,
    check_date_validity,
    check_duplicate_rows,
    check_email_format,
    check_key_uniqueness,
    check_missing_values,
    check_numeric_validity,
    check_regex_pattern,
    check_schema_mismatch,
    check_string_length,
    check_value_range,
)

# Supported rule types
SUPPORTED_RULES = {
    "required",
    "unique",
    "data_type",
    "min_value",
    "max_value",
    "range",
    "allowed_values",
    "min_length",
    "max_length",
    "length_range",
    "date_format",
    "date_range",
    "regex",
    "email",
    "schema",
    "duplicate_rows",
}


def validate_rule_config(config: Dict[str, Any]) -> None:
    """Validate that a rule configuration structure is valid and well-formed.

    Args:
        config: Parsed configuration dictionary.

    Raises:
        ValueError: If configuration fails validation with clear actionable description.
    """
    if not isinstance(config, dict):
        raise ValueError("Rule configuration must be a dictionary/mapping object at the root level.")

    if "rules" not in config:
        raise ValueError("Missing required key 'rules' at root level of configuration.")

    rules_list = config["rules"]
    if not isinstance(rules_list, list):
        raise ValueError("The 'rules' entry must be a list of rule definitions.")

    if len(rules_list) == 0:
        raise ValueError("Rule list is empty. Provide at least one rule definition.")

    for idx, rule in enumerate(rules_list):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule at index {idx} must be a dictionary, got: {type(rule).__name__}")

        rule_type = rule.get("rule")
        if not rule_type:
            raise ValueError(f"Rule at index {idx} is missing required field 'rule'. Definition: {rule}")

        if rule_type not in SUPPORTED_RULES:
            supported = ", ".join(sorted(SUPPORTED_RULES))
            raise ValueError(
                f"Unsupported rule type '{rule_type}' at index {idx}. Supported rule types: {supported}"
            )

        # Schema and duplicate_rows rules don't require 'column'
        if rule_type not in {"schema", "duplicate_rows"}:
            if "column" not in rule and "columns" not in rule:
                raise ValueError(
                    f"Rule '{rule_type}' at index {idx} requires a 'column' or 'columns' specification."
                )

        # Type-specific parameter validation
        if rule_type == "allowed_values":
            if "values" not in rule or not isinstance(rule["values"], (list, set, tuple)):
                raise ValueError(
                    f"Rule 'allowed_values' at index {idx} requires a list of 'values'. Got: {rule.get('values')}"
                )

        if rule_type == "regex":
            pattern = rule.get("pattern")
            if not pattern:
                raise ValueError(f"Rule 'regex' at index {idx} requires a non-empty 'pattern'.")
            try:
                re.compile(pattern)
            except re.error as err:
                raise ValueError(f"Invalid regex pattern '{pattern}' at index {idx}: {err}") from err

        if rule_type == "range":
            if "min" not in rule and "max" not in rule:
                raise ValueError(f"Rule 'range' at index {idx} requires at least 'min' or 'max' parameter.")

        if rule_type == "schema":
            if "expected_columns" not in rule or not isinstance(rule["expected_columns"], list):
                raise ValueError(f"Rule 'schema' at index {idx} requires an 'expected_columns' list.")


def load_rules(file_or_string: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Load and validate rules from a file path, JSON/YAML string, or dictionary.

    Args:
        file_or_string: File path (str/Path), raw JSON/YAML string, or already parsed dict.

    Returns:
        Validated rule configuration dictionary.

    Raises:
        ValueError: If file cannot be read, format is invalid, or schema check fails.
    """
    if isinstance(file_or_string, dict):
        validate_rule_config(file_or_string)
        return file_or_string

    content_str = ""
    # Check if input is a Path or a path-like string
    if isinstance(file_or_string, Path):
        if not file_or_string.is_file():
            raise FileNotFoundError(f"Rule file does not exist at '{file_or_string}'")
        try:
            content_str = file_or_string.read_text(encoding="utf-8")
        except Exception as err:
            raise ValueError(f"Failed to read rule file at '{file_or_string}': {err}") from err
    elif isinstance(file_or_string, str):
        # Check if the string refers to an existing file on disk
        is_file_on_disk = False
        try:
            potential_p = Path(file_or_string)
            if potential_p.is_file():
                is_file_on_disk = True
                content_str = potential_p.read_text(encoding="utf-8")
        except Exception:
            is_file_on_disk = False

        if not is_file_on_disk:
            content_str = file_or_string
    else:
        raise ValueError(f"Unsupported rules input type: {type(file_or_string).__name__}")

    # Attempt JSON parse first, fallback to YAML
    parsed = None
    try:
        parsed = json.loads(content_str)
    except Exception:
        try:
            parsed = yaml.safe_load(content_str)
        except Exception as yaml_err:
            raise ValueError(f"Could not parse rules as either JSON or YAML: {yaml_err}") from yaml_err

    if not isinstance(parsed, dict):
        raise ValueError("Rules configuration must deserialize into a dictionary.")

    validate_rule_config(parsed)
    return parsed


def execute_rule(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    """Execute a single rule definition against a DataFrame.

    Args:
        df: Input DataFrame.
        rule_def: Individual rule dictionary.

    Returns:
        List of ValidationResult items (one or more per rule).
    """
    rule_type = rule_def["rule"]
    col = rule_def.get("column")
    cols = rule_def.get("columns")
    results: List[ValidationResult] = []

    if rule_type == "required":
        target_cols = [col] if col else (cols or [])
        treat_empty = bool(rule_def.get("treat_empty_as_missing", False))
        for c in target_cols:
            threshold = float(rule_def.get("threshold_percent", 0.0))
            results.append(check_missing_values(df, column=c, threshold_percent=threshold, treat_empty_as_missing=treat_empty))

    elif rule_type == "unique":
        key_cols = cols or ([col] if col else [])
        results.append(check_key_uniqueness(df, key_columns=key_cols))

    elif rule_type == "duplicate_rows":
        subset = cols or ([col] if col else None)
        results.append(check_duplicate_rows(df, subset=subset))

    elif rule_type == "data_type":
        exp_type = rule_def.get("type", "string")
        results.append(check_data_types(df, expected_types={col: exp_type}))

    elif rule_type == "min_value":
        min_v = float(rule_def.get("value", 0))
        results.append(check_value_range(df, column=col, min_value=min_v))

    elif rule_type == "max_value":
        max_v = float(rule_def.get("value", 0))
        results.append(check_value_range(df, column=col, max_value=max_v))

    elif rule_type == "range":
        min_v = rule_def.get("min")
        max_v = rule_def.get("max")
        results.append(
            check_value_range(
                df,
                column=col,
                min_value=float(min_v) if min_v is not None else None,
                max_value=float(max_v) if max_v is not None else None,
            )
        )

    elif rule_type == "allowed_values":
        allowed = rule_def.get("values", [])
        case_sens = rule_def.get("case_sensitive", True)
        results.append(check_allowed_values(df, column=col, allowed_values=allowed, case_sensitive=case_sens))

    elif rule_type == "min_length":
        min_l = int(rule_def.get("value", 0))
        results.append(check_string_length(df, column=col, min_length=min_l))

    elif rule_type == "max_length":
        max_l = int(rule_def.get("value", 0))
        results.append(check_string_length(df, column=col, max_length=max_l))

    elif rule_type == "length_range":
        min_l = rule_def.get("min")
        max_l = rule_def.get("max")
        results.append(
            check_string_length(
                df,
                column=col,
                min_length=int(min_l) if min_l is not None else None,
                max_length=int(max_l) if max_l is not None else None,
            )
        )

    elif rule_type == "date_format":
        fmt = rule_def.get("format")
        chrono = bool(rule_def.get("chronological", False) or rule_def.get("check_chronological_order", False))
        results.append(check_date_validity(df, column=col, date_format=fmt, check_chronological_order=chrono))

    elif rule_type == "date_range":
        fmt = rule_def.get("format")
        min_d = rule_def.get("min_date")
        max_d = rule_def.get("max_date")
        chrono = bool(rule_def.get("chronological", False) or rule_def.get("check_chronological_order", False))
        results.append(check_date_validity(df, column=col, date_format=fmt, min_date=min_d, max_date=max_d, check_chronological_order=chrono))

    elif rule_type == "regex":
        pattern_str = rule_def["pattern"]
        results.append(check_regex_pattern(df, column=col, pattern=pattern_str))

    elif rule_type == "email":
        custom_pat = rule_def.get("pattern")
        if custom_pat:
            results.append(check_email_format(df, column=col, pattern=custom_pat))
        else:
            results.append(check_email_format(df, column=col))

    elif rule_type == "schema":
        expected = rule_def.get("expected_columns", [])
        strict = rule_def.get("strict", False)
        results.append(check_schema_mismatch(df, expected_columns=expected, strict=strict))

    return results


def execute_rule_suite(df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationResult]:
    """Execute all rules in a configuration against a DataFrame.

    Args:
        df: Input DataFrame.
        config: Validated rule configuration.

    Returns:
        List of all ValidationResult items.
    """
    validate_rule_config(config)
    results: List[ValidationResult] = []

    for rule_def in config["rules"]:
        try:
            rule_results = execute_rule(df, rule_def)
            results.extend(rule_results)
        except Exception as exc:
            logger.error("Error executing rule %s: %s", rule_def, exc)
            results.append(
                ValidationResult(
                    check_name=rule_def.get("rule", "unknown"),
                    column_name=rule_def.get("column"),
                    total_records=len(df),
                    failed_records=0,
                    passed=False,
                    message=f"Rule execution error: {exc}",
                )
            )

    return results
