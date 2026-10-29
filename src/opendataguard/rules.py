"""Declarative validation rule configuration and execution engine for OpenDataGuard.

Supports JSON and YAML rule specifications with strict schema validation,
clear error reporting for unsupported rules or malformed parameters,
table-driven rule dispatch, and unified execution across DataFrames.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd
import yaml

from opendataguard.logging_config import logger
from opendataguard.validators import (
    ValidationResult,
    _extract_sample,
    check_allowed_values,
    check_column_comparison,
    check_data_types,
    check_date_validity,
    check_duplicate_rows,
    check_email_format,
    check_key_uniqueness,
    check_missing_values,
    check_numeric_validity,
    check_outliers_iqr,
    check_regex_pattern,
    check_row_count,
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
    "outliers",
    "iqr",
    "row_count",
    "column_comparison",
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

        # Rules that don't require standard 'column' or 'columns'
        if rule_type not in {"schema", "duplicate_rows", "row_count", "column_comparison"}:
            if "column" not in rule and "columns" not in rule:
                raise ValueError(
                    f"Rule '{rule_type}' at index {idx} requires a 'column' or 'columns' specification."
                )

        # Column comparison rule validation
        if rule_type == "column_comparison":
            col_a = rule.get("column") or rule.get("column_a")
            col_b = rule.get("compare_to") or rule.get("column_b")
            if not col_a or not col_b:
                raise ValueError(
                    f"Rule 'column_comparison' at index {idx} requires ('column' and 'compare_to') or ('column_a' and 'column_b')."
                )
            if "operator" in rule:
                op = str(rule["operator"]).strip()
                if op not in {">=", ">", "<=", "<", "==", "!=", "="}:
                    raise ValueError(
                        f"Rule 'column_comparison' at index {idx} has invalid operator '{op}'."
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

        # Optional conditional 'when' block validation
        if "when" in rule:
            when = rule["when"]
            if not isinstance(when, dict):
                raise ValueError(f"Conditional 'when' clause at index {idx} must be a dictionary.")
            if "column" not in when:
                raise ValueError(f"Conditional 'when' clause at index {idx} requires a 'column' field.")


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
    if isinstance(file_or_string, Path):
        if not file_or_string.is_file():
            raise FileNotFoundError(f"Rule file does not exist at '{file_or_string}'")
        try:
            content_str = file_or_string.read_text(encoding="utf-8")
        except Exception as err:
            raise ValueError(f"Failed to read rule file at '{file_or_string}': {err}") from err
    elif isinstance(file_or_string, str):
        if "\x00" in file_or_string:
            raise ValueError("Invalid rule specification: input contains null byte.")
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


# ============================================================================
# Modular Rule Dispatch Handlers (TD-08 Refactor)
# ============================================================================


def _apply_conditional_filter(df: pd.DataFrame, when_def: Dict[str, Any]) -> pd.DataFrame:
    """Slice DataFrame based on declarative condition.

    Supported syntax:
        when: {column: "status", equals: "ACTIVE"}
        when: {column: "status", value: "ACTIVE"}
        when: {column: "status", operator: "==", value: "ACTIVE"}
        when: {column: "status", in: ["ACTIVE", "PENDING"]}
    """
    col = when_def.get("column")
    if not col or col not in df.columns:
        return df

    series = df[col]
    if "in" in when_def:
        allowed_list = when_def["in"]
        mask = series.isin(allowed_list)
    elif "equals" in when_def:
        mask = series == when_def["equals"]
    elif "operator" in when_def and "value" in when_def:
        op = str(when_def["operator"]).strip()
        val = when_def["value"]
        if op in ("==", "="):
            mask = series == val
        elif op == "!=":
            mask = series != val
        elif op == ">":
            mask = series > val
        elif op == ">=":
            mask = series >= val
        elif op == "<":
            mask = series < val
        elif op == "<=":
            mask = series <= val
        else:
            mask = pd.Series(True, index=df.index)
    elif "value" in when_def:
        mask = series == when_def["value"]
    else:
        mask = pd.Series(True, index=df.index)

    return df.loc[mask]


def _handle_required(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def.get("column")
    cols = rule_def.get("columns")
    target_cols = [col] if col else (cols or [])
    treat_empty = bool(rule_def.get("treat_empty_as_missing", False))
    threshold = float(rule_def.get("threshold_percent", 0.0))
    return [
        check_missing_values(
            df,
            column=c,
            threshold_percent=threshold,
            treat_empty_as_missing=treat_empty,
        )
        for c in target_cols
    ]


def _handle_unique(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def.get("column")
    cols = rule_def.get("columns")
    key_cols = cols or ([col] if col else [])
    return [check_key_uniqueness(df, key_columns=key_cols)]


def _handle_duplicate_rows(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def.get("column")
    cols = rule_def.get("columns")
    subset = cols or ([col] if col else None)
    return [check_duplicate_rows(df, subset=subset)]


def _handle_data_type(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    exp_type = rule_def.get("type", "string")
    return [check_data_types(df, expected_types={col: exp_type})]


def _handle_min_value(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    min_v = float(rule_def.get("value", 0))
    return [check_value_range(df, column=col, min_value=min_v)]


def _handle_max_value(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    max_v = float(rule_def.get("value", 0))
    return [check_value_range(df, column=col, max_value=max_v)]


def _handle_range(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    min_v = rule_def.get("min")
    max_v = rule_def.get("max")
    return [
        check_value_range(
            df,
            column=col,
            min_value=float(min_v) if min_v is not None else None,
            max_value=float(max_v) if max_v is not None else None,
        )
    ]


def _handle_allowed_values(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    allowed = rule_def.get("values", [])
    case_sens = rule_def.get("case_sensitive", True)
    return [check_allowed_values(df, column=col, allowed_values=allowed, case_sensitive=case_sens)]


def _handle_min_length(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    min_l = int(rule_def.get("value", 0))
    return [check_string_length(df, column=col, min_length=min_l)]


def _handle_max_length(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    max_l = int(rule_def.get("value", 0))
    return [check_string_length(df, column=col, max_length=max_l)]


def _handle_length_range(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    min_l = rule_def.get("min")
    max_l = rule_def.get("max")
    return [
        check_string_length(
            df,
            column=col,
            min_length=int(min_l) if min_l is not None else None,
            max_length=int(max_l) if max_l is not None else None,
        )
    ]


def _handle_date_format(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    fmt = rule_def.get("format")
    chrono = bool(rule_def.get("chronological", False) or rule_def.get("check_chronological_order", False))
    return [check_date_validity(df, column=col, date_format=fmt, check_chronological_order=chrono)]


def _handle_date_range(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    fmt = rule_def.get("format")
    min_d = rule_def.get("min_date")
    max_d = rule_def.get("max_date")
    chrono = bool(rule_def.get("chronological", False) or rule_def.get("check_chronological_order", False))
    return [
        check_date_validity(
            df,
            column=col,
            date_format=fmt,
            min_date=min_d,
            max_date=max_d,
            check_chronological_order=chrono,
        )
    ]


def _handle_regex(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    pattern_str = rule_def["pattern"]
    return [check_regex_pattern(df, column=col, pattern=pattern_str)]


def _handle_email(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    custom_pat = rule_def.get("pattern")
    if custom_pat:
        return [check_email_format(df, column=col, pattern=custom_pat)]
    return [check_email_format(df, column=col)]


def _handle_schema(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    expected = rule_def.get("expected_columns", [])
    strict = rule_def.get("strict", False)
    return [check_schema_mismatch(df, expected_columns=expected, strict=strict)]


def _handle_outliers(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col = rule_def["column"]
    factor_val = float(rule_def.get("factor", 1.5))
    return [check_outliers_iqr(df, column=col, factor=factor_val)]


def _handle_row_count(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    min_r = rule_def.get("min_rows") or rule_def.get("min")
    max_r = rule_def.get("max_rows") or rule_def.get("max")
    exp_r = rule_def.get("expected_rows") or rule_def.get("expected")
    return [
        check_row_count(
            df,
            min_rows=int(min_r) if min_r is not None else None,
            max_rows=int(max_r) if max_r is not None else None,
            expected_rows=int(exp_r) if exp_r is not None else None,
        )
    ]


def _handle_column_comparison(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    col_a = rule_def.get("column") or rule_def.get("column_a", "")
    col_b = rule_def.get("compare_to") or rule_def.get("column_b", "")
    op = rule_def.get("operator", ">=")
    allow_nulls = bool(rule_def.get("allow_nulls", True))
    return [check_column_comparison(df, col_a=col_a, col_b=col_b, operator=op, allow_nulls=allow_nulls)]


# Rule Dispatch Registry (O(1) dictionary lookup replacing monolithic if/elif cascade)
RULE_DISPATCH: Dict[str, Callable[[pd.DataFrame, Dict[str, Any]], List[ValidationResult]]] = {
    "required": _handle_required,
    "unique": _handle_unique,
    "duplicate_rows": _handle_duplicate_rows,
    "data_type": _handle_data_type,
    "min_value": _handle_min_value,
    "max_value": _handle_max_value,
    "range": _handle_range,
    "allowed_values": _handle_allowed_values,
    "min_length": _handle_min_length,
    "max_length": _handle_max_length,
    "length_range": _handle_length_range,
    "date_format": _handle_date_format,
    "date_range": _handle_date_range,
    "regex": _handle_regex,
    "email": _handle_email,
    "schema": _handle_schema,
    "outliers": _handle_outliers,
    "iqr": _handle_outliers,
    "row_count": _handle_row_count,
    "column_comparison": _handle_column_comparison,
}


def execute_rule(df: pd.DataFrame, rule_def: Dict[str, Any]) -> List[ValidationResult]:
    """Execute a single rule definition against a DataFrame via registry dispatch.

    Args:
        df: Input DataFrame.
        rule_def: Individual rule dictionary.

    Returns:
        List of ValidationResult items (one or more per rule).

    Raises:
        ValueError: If rule type is not registered in RULE_DISPATCH.
    """
    rule_type = rule_def["rule"]
    handler = RULE_DISPATCH.get(rule_type)
    if not handler:
        supported = ", ".join(sorted(SUPPORTED_RULES))
        raise ValueError(f"Unsupported rule type '{rule_type}'. Supported: {supported}")

    # Evaluate conditional filter if specified
    eval_df = df
    if "when" in rule_def:
        eval_df = _apply_conditional_filter(df, rule_def["when"])

    return handler(eval_df, rule_def)


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
