"""Deterministic report generation engine for OpenDataGuard.

Generates CSV, Excel, and JSON reports for both Data Quality Validations
and Dataset Reconciliations with standardized UTC timestamps and schemas.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from opendataguard.logging_config import logger
from opendataguard.reconciliation import ReconciliationResult
from opendataguard.validators import ValidationResult, calculate_data_quality_score


def generate_validation_csv(
    results: List[ValidationResult],
    dataset_name: str,
    timestamp_utc: Optional[str] = None,
) -> str:
    """Generate a deterministic CSV string of validation results.

    Args:
        results: List of ValidationResult objects.
        dataset_name: Name of evaluated dataset.
        timestamp_utc: Optional ISO timestamp string (defaults to now UTC).

    Returns:
        CSV string content.
    """
    ts = timestamp_utc or datetime.now(timezone.utc).isoformat()
    rows = []
    for r in results:
        rows.append({
            "timestamp_utc": ts,
            "dataset_name": dataset_name,
            "check_name": r.check_name,
            "column_name": r.column_name or "",
            "passed": r.passed,
            "total_records": r.total_records,
            "failed_records": r.failed_records,
            "failure_rate_pct": round((r.failed_records / r.total_records * 100), 2) if r.total_records > 0 else 0.0,
            "message": r.message,
            "details": json.dumps(r.details) if r.details else "{}",
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


def generate_validation_json(
    results: List[ValidationResult],
    dataset_name: Any,
    row_count: Optional[int] = None,
    column_count: Optional[int] = None,
    timestamp_utc: Optional[str] = None,
) -> str:
    """Generate a structured JSON validation summary report.

    Args:
        results: List of ValidationResult items.
        dataset_name: Evaluated dataset name (or DatasetMetadata object).
        row_count: Dataset row count (optional if DatasetMetadata passed).
        column_count: Dataset column count (optional if DatasetMetadata passed).
        timestamp_utc: Optional ISO timestamp.

    Returns:
        Formatted JSON string.
    """
    resolved_name = dataset_name
    if hasattr(dataset_name, "name") and hasattr(dataset_name, "row_count"):
        resolved_name = dataset_name.name
        if row_count is None:
            row_count = dataset_name.row_count
        if column_count is None:
            column_count = dataset_name.column_count

    if row_count is None:
        row_count = results[0].total_records if results else 0
    if column_count is None:
        column_count = 0

    ts = timestamp_utc or datetime.now(timezone.utc).isoformat()
    passed_count = sum(1 for r in results if r.passed)
    failed_count = sum(1 for r in results if not r.passed)
    score = calculate_data_quality_score(results)

    try:
        import opendataguard
        current_version = opendataguard.__version__
    except (ImportError, AttributeError):
        current_version = "1.1.0"

    report = {
        "metadata": {
            "platform": "OpenDataGuard",
            "version": current_version,
            "timestamp_utc": ts,
            "dataset_name": str(resolved_name),
            "total_rows": row_count,
            "total_columns": column_count,
        },
        "summary": {
            "total_checks": len(results),
            "passed_checks": passed_count,
            "failed_checks": failed_count,
            "data_quality_score": score,
            "overall_status": "PASSED" if failed_count == 0 else "FAILED",
        },
        "results": [r.to_dict() for r in results],
    }

    return json.dumps(report, indent=2)


def generate_validation_excel(
    results: List[ValidationResult],
    dataset_name: Any,
    row_count: Optional[int] = None,
    column_count: Optional[int] = None,
    timestamp_utc: Optional[str] = None,
    max_sample_rows: int = 5_000,
    output_file: Optional[Union[str, Path]] = None,
) -> bytes:
    """Generate a multi-tab Excel validation workbook with memory-bounded sample rows.

    Sheets:
    1. Summary - Metadata, overall score, pass/fail counters.
    2. Detailed Checks - Full check table.
    3. Failed Samples - Individual sample records from failing checks (capped at max_sample_rows).

    Args:
        results: List of ValidationResult items.
        dataset_name: Dataset name (or DatasetMetadata object).
        row_count: Total row count (optional if DatasetMetadata passed).
        column_count: Total column count (optional if DatasetMetadata passed).
        timestamp_utc: Timestamp.
        max_sample_rows: Maximum failing sample rows written to Excel sheet.
        output_file: Optional direct file path for disk streaming.

    Returns:
        Excel workbook as bytes (or empty bytes if output_file was provided).
    """
    resolved_name = dataset_name
    if hasattr(dataset_name, "name") and hasattr(dataset_name, "row_count"):
        resolved_name = dataset_name.name
        if row_count is None:
            row_count = dataset_name.row_count
        if column_count is None:
            column_count = dataset_name.column_count

    if row_count is None:
        row_count = results[0].total_records if results else 0
    if column_count is None:
        column_count = 0

    ts = timestamp_utc or datetime.now(timezone.utc).isoformat()
    passed_count = sum(1 for r in results if r.passed)
    failed_count = sum(1 for r in results if not r.passed)
    score = calculate_data_quality_score(results)

    summary_data = [
        {"Metric": "Dataset Name", "Value": str(resolved_name)},
        {"Metric": "Execution Timestamp (UTC)", "Value": ts},
        {"Metric": "Total Rows Checked", "Value": row_count},
        {"Metric": "Total Columns Checked", "Value": column_count},
        {"Metric": "Total Validation Rules", "Value": len(results)},
        {"Metric": "Passed Checks", "Value": passed_count},
        {"Metric": "Failed Checks", "Value": failed_count},
        {"Metric": "Data Quality Score (%)", "Value": f"{score}%"},
        {"Metric": "Overall Status", "Value": "PASSED" if failed_count == 0 else "FAILED"},
    ]
    summary_df = pd.DataFrame(summary_data)

    checks_data = []
    sample_rows = []
    for r in results:
        checks_data.append({
            "Check Name": r.check_name,
            "Column Name": r.column_name or "N/A",
            "Status": "PASS" if r.passed else "FAIL",
            "Total Records": r.total_records,
            "Failed Records": r.failed_records,
            "Message": r.message,
        })
        if r.failing_sample and len(sample_rows) < max_sample_rows:
            remaining_slots = max_sample_rows - len(sample_rows)
            for s in r.failing_sample[:remaining_slots]:
                sample_item = {"Check Name": r.check_name, "Column": r.column_name or "N/A", **s}
                sample_rows.append(sample_item)

    checks_df = pd.DataFrame(checks_data)
    samples_df = pd.DataFrame(sample_rows) if sample_rows else pd.DataFrame([{"Notice": "No failing records"}])

    dest: Any = output_file if output_file is not None else io.BytesIO()
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        checks_df.to_excel(writer, sheet_name="Validation Details", index=False)
        samples_df.to_excel(writer, sheet_name="Failing Samples", index=False)

    if output_file is not None:
        return b""
    return dest.getvalue()


def generate_reconciliation_excel(
    result: ReconciliationResult,
    max_rows_per_sheet: int = 10_000,
    output_file: Optional[Union[str, Path]] = None,
) -> bytes:
    """Generate a multi-tab Excel workbook for reconciliation outputs with memory bounds.

    Sheets:
    1. Summary
    2. Value Mismatches (capped at max_rows_per_sheet)
    3. Source Only (capped at max_rows_per_sheet)
    4. Target Only (capped at max_rows_per_sheet)
    5. Matched Sample (capped at max_rows_per_sheet)

    Args:
        result: ReconciliationResult instance.
        max_rows_per_sheet: Maximum rows written per discrepancy sheet to bound memory.
        output_file: Optional direct file path for disk streaming.

    Returns:
        Excel workbook as bytes (or empty bytes if output_file was provided).
    """
    s = result.summary
    summary_rows = [
        {"Metric": "Source Dataset", "Value": s.source_name},
        {"Metric": "Target Dataset", "Value": s.target_name},
        {"Metric": "Key Column(s)", "Value": ", ".join(s.key_columns)},
        {"Metric": "Source Total Rows", "Value": s.source_rows},
        {"Metric": "Target Total Rows", "Value": s.target_rows},
        {"Metric": "Row Count Difference", "Value": s.row_count_diff},
        {"Metric": "Matched Records", "Value": s.matched_records},
        {"Metric": "Mismatched Records", "Value": s.mismatched_records},
        {"Metric": "Source Only Records", "Value": s.source_only_records},
        {"Metric": "Target Only Records", "Value": s.target_only_records},
        {"Metric": "Match Rate (%)", "Value": f"{s.match_rate_percent}%"},
        {"Metric": "Source Duplicate Keys", "Value": s.source_duplicate_keys},
        {"Metric": "Target Duplicate Keys", "Value": s.target_duplicate_keys},
        {"Metric": "Source Null Keys", "Value": s.source_null_keys},
        {"Metric": "Target Null Keys", "Value": s.target_null_keys},
        {"Metric": "Key Warnings", "Value": s.key_error_message or "None"},
        {"Metric": "Excel Row Cap per Sheet", "Value": f"{max_rows_per_sheet:,} rows (Export to CSV for full dumps)"},
    ]
    summary_df = pd.DataFrame(summary_rows)

    def _bound_df(df: pd.DataFrame, empty_msg: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame([{"Notice": empty_msg}])
        if len(df) > max_rows_per_sheet:
            return df.head(max_rows_per_sheet)
        return df

    dest: Any = output_file if output_file is not None else io.BytesIO()
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        mismatched_out = _bound_df(result.mismatched_df, "No value mismatches detected")
        mismatched_out.to_excel(writer, sheet_name="Value Mismatches", index=False)

        source_only_out = _bound_df(result.source_only_df, "No source-only records")
        source_only_out.to_excel(writer, sheet_name="Source Only", index=False)

        target_only_out = _bound_df(result.target_only_df, "No target-only records")
        target_only_out.to_excel(writer, sheet_name="Target Only", index=False)

        matched_out = _bound_df(result.matched_df, "No matched records")
        matched_out.to_excel(writer, sheet_name="Matched Records (Sample)", index=False)

    if output_file is not None:
        return b""
    return dest.getvalue()
