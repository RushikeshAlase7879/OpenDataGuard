"""Dataset reconciliation engine for OpenDataGuard.

Compares Source and Target datasets, identifies schema differences,
safely detects duplicate or null keys to avoid corrupt joins, evaluates
cell-by-cell mismatches with configurable float tolerance, and produces
detailed reconciliation breakdowns.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from opendataguard.logging_config import logger


@dataclass
class ReconciliationSummary:
    """Statistical summary of dataset reconciliation."""

    source_name: str
    target_name: str
    key_columns: List[str]
    source_rows: int
    target_rows: int
    row_count_diff: int
    common_columns: List[str]
    source_only_columns: List[str]
    target_only_columns: List[str]
    source_duplicate_keys: int
    target_duplicate_keys: int
    source_null_keys: int
    target_null_keys: int
    source_only_records: int
    target_only_records: int
    matched_records: int
    mismatched_records: int
    match_rate_percent: float
    column_mismatch_counts: Dict[str, int] = field(default_factory=dict)
    has_key_errors: bool = False
    key_error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary representation."""
        return asdict(self)


@dataclass
class ReconciliationResult:
    """Comprehensive reconciliation output including data subsets."""

    summary: ReconciliationSummary
    source_only_df: pd.DataFrame
    target_only_df: pd.DataFrame
    mismatched_df: pd.DataFrame
    matched_df: pd.DataFrame


def _values_are_equal(
    val_s: Any,
    val_t: Any,
    float_atol: float = 1e-5,
    float_rtol: float = 1e-5,
    ignore_whitespace: bool = True,
    case_sensitive: bool = True,
) -> bool:
    """Compare two individual values for equality considering tolerance and types."""
    # Both are null/NaN
    s_is_null = pd.isna(val_s)
    t_is_null = pd.isna(val_t)
    if s_is_null and t_is_null:
        return True
    if s_is_null != t_is_null:
        return False

    # Try numeric comparison
    try:
        f_s = float(val_s)
        f_t = float(val_t)
        return bool(np.isclose(f_s, f_t, rtol=float_rtol, atol=float_atol, equal_nan=True))
    except (ValueError, TypeError, OverflowError):
        pass

    # String comparison
    str_s = str(val_s)
    str_t = str(val_t)
    if ignore_whitespace:
        str_s = str_s.strip()
        str_t = str_t.strip()
    if not case_sensitive:
        str_s = str_s.lower()
        str_t = str_t.lower()

    return str_s == str_t


def reconcile_datasets(
    source_df: pd.DataFrame,
    target_df: pd.DataFrame,
    key_columns: Union[str, List[str]],
    source_name: str = "Source",
    target_name: str = "Target",
    float_atol: float = 1e-5,
    float_rtol: float = 1e-5,
    ignore_whitespace: bool = True,
    case_sensitive: bool = True,
    columns_to_compare: Optional[List[str]] = None,
) -> ReconciliationResult:
    """Perform full key-based reconciliation between source and target datasets.

    Args:
        source_df: Source DataFrame.
        target_df: Target DataFrame.
        key_columns: Column name or list of columns uniquely identifying records.
        source_name: Name/label for source dataset.
        target_name: Name/label for target dataset.
        float_atol: Absolute tolerance for numeric comparison.
        float_rtol: Relative tolerance for numeric comparison.
        ignore_whitespace: Strip leading/trailing string whitespace.
        case_sensitive: Whether string comparison is case-sensitive.
        columns_to_compare: Optional subset of common columns to reconcile.

    Returns:
        ReconciliationResult containing summary metrics and categorized DataFrames.

    Raises:
        ValueError: If key columns do not exist in both datasets.
    """
    keys = [key_columns] if isinstance(key_columns, str) else list(key_columns)

    # 1. Column and Schema Comparison
    source_cols = [str(c) for c in source_df.columns]
    target_cols = [str(c) for c in target_df.columns]

    missing_source_keys = [k for k in keys if k not in source_cols]
    missing_target_keys = [k for k in keys if k not in target_cols]
    if missing_source_keys or missing_target_keys:
        err_msg = (
            f"Key column(s) missing: Source missing {missing_source_keys}, "
            f"Target missing {missing_target_keys}"
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    common_cols = [c for c in source_cols if c in target_cols]
    source_only_cols = [c for c in source_cols if c not in target_cols]
    target_only_cols = [c for c in target_cols if c not in source_cols]

    # Non-key common columns to compare
    if columns_to_compare is not None:
        compare_cols = [c for c in columns_to_compare if c in common_cols and c not in keys]
    else:
        compare_cols = [c for c in common_cols if c not in keys]

    # 2. Key Integrity Checks
    # Check for Null Keys
    src_null_mask = source_df[keys].isna().any(axis=1)
    tgt_null_mask = target_df[keys].isna().any(axis=1)
    src_null_count = int(src_null_mask.sum())
    tgt_null_count = int(tgt_null_mask.sum())

    # Check for Duplicate Keys
    src_dup_mask = source_df.duplicated(subset=keys, keep=False)
    tgt_dup_mask = target_df.duplicated(subset=keys, keep=False)
    src_dup_count = int(src_dup_mask.sum())
    tgt_dup_count = int(tgt_dup_mask.sum())

    has_key_errors = (src_dup_count > 0 or tgt_dup_count > 0 or src_null_count > 0 or tgt_null_count > 0)
    key_error_msg = None

    if has_key_errors:
        reasons = []
        if src_dup_count > 0:
            reasons.append(f"Source has {src_dup_count} records with duplicate key '{keys}'")
        if tgt_dup_count > 0:
            reasons.append(f"Target has {tgt_dup_count} records with duplicate key '{keys}'")
        if src_null_count > 0:
            reasons.append(f"Source has {src_null_count} records with null keys")
        if tgt_null_count > 0:
            reasons.append(f"Target has {tgt_null_count} records with null keys")
        key_error_msg = "; ".join(reasons)
        logger.warning("Reconciliation key warning: %s. Safe one-to-one record join cannot proceed on duplicate rows.", key_error_msg)

    # Empty result containers if key errors prevent safe comparison
    if src_dup_count > 0 or tgt_dup_count > 0:
        summary = ReconciliationSummary(
            source_name=source_name,
            target_name=target_name,
            key_columns=keys,
            source_rows=len(source_df),
            target_rows=len(target_df),
            row_count_diff=len(source_df) - len(target_df),
            common_columns=common_cols,
            source_only_columns=source_only_cols,
            target_only_columns=target_only_cols,
            source_duplicate_keys=src_dup_count,
            target_duplicate_keys=tgt_dup_count,
            source_null_keys=src_null_count,
            target_null_keys=tgt_null_count,
            source_only_records=0,
            target_only_records=0,
            matched_records=0,
            mismatched_records=0,
            match_rate_percent=0.0,
            column_mismatch_counts={},
            has_key_errors=True,
            key_error_message=key_error_msg,
        )
        return ReconciliationResult(
            summary=summary,
            source_only_df=pd.DataFrame(),
            target_only_df=pd.DataFrame(),
            mismatched_df=pd.DataFrame(),
            matched_df=pd.DataFrame(),
        )

    # 3. Key-based Record Matching
    # Drop rows with null keys for the join matching, but preserve them in source/target only
    src_valid = source_df[~src_null_mask].copy()
    tgt_valid = target_df[~tgt_null_mask].copy()

    # Set keys as index for deterministic lookup
    src_indexed = src_valid.set_index(keys)
    tgt_indexed = tgt_valid.set_index(keys)

    src_idx_set = set(src_indexed.index)
    tgt_idx_set = set(tgt_indexed.index)

    common_keys = src_idx_set.intersection(tgt_idx_set)
    src_only_keys = src_idx_set.difference(tgt_idx_set)
    tgt_only_keys = tgt_idx_set.difference(src_idx_set)

    # Reconstruct Source Only (including null key rows)
    src_only_df = pd.concat([
        src_indexed.loc[list(src_only_keys)].reset_index() if src_only_keys else pd.DataFrame(columns=source_df.columns),
        source_df[src_null_mask],
    ], ignore_index=True)

    # Reconstruct Target Only (including null key rows)
    tgt_only_df = pd.concat([
        tgt_indexed.loc[list(tgt_only_keys)].reset_index() if tgt_only_keys else pd.DataFrame(columns=target_df.columns),
        target_df[tgt_null_mask],
    ], ignore_index=True)

    # 4. Compare common records
    mismatched_rows = []
    matched_keys_list = []
    col_mismatch_counts = {c: 0 for c in compare_cols}

    for key_val in common_keys:
        row_s = src_indexed.loc[key_val]
        row_t = tgt_indexed.loc[key_val]

        has_row_mismatch = False
        row_key_dict = {keys[0]: key_val} if len(keys) == 1 else dict(zip(keys, key_val))

        for col in compare_cols:
            val_s = row_s[col]
            val_t = row_t[col]

            if not _values_are_equal(
                val_s,
                val_t,
                float_atol=float_atol,
                float_rtol=float_rtol,
                ignore_whitespace=ignore_whitespace,
                case_sensitive=case_sensitive,
            ):
                has_row_mismatch = True
                col_mismatch_counts[col] += 1
                mismatch_record = {**row_key_dict, "mismatched_column": col, "source_value": val_s, "target_value": val_t}
                mismatched_rows.append(mismatch_record)

        if not has_row_mismatch:
            matched_keys_list.append(key_val)

    # Matched DataFrame
    if matched_keys_list:
        matched_df = src_indexed.loc[matched_keys_list].reset_index()
    else:
        matched_df = pd.DataFrame(columns=source_df.columns)

    # Mismatched DataFrame
    if mismatched_rows:
        mismatched_df = pd.DataFrame(mismatched_rows)
    else:
        mismatched_df = pd.DataFrame(columns=[*keys, "mismatched_column", "source_value", "target_value"])

    total_common_records = len(common_keys)
    matched_count = len(matched_keys_list)
    mismatched_record_count = total_common_records - matched_count

    total_unique_records = len(src_idx_set.union(tgt_idx_set)) + src_null_count + tgt_null_count
    match_rate = round((matched_count / total_unique_records * 100.0), 2) if total_unique_records > 0 else 100.0

    summary = ReconciliationSummary(
        source_name=source_name,
        target_name=target_name,
        key_columns=keys,
        source_rows=len(source_df),
        target_rows=len(target_df),
        row_count_diff=len(source_df) - len(target_df),
        common_columns=common_cols,
        source_only_columns=source_only_cols,
        target_only_columns=target_only_cols,
        source_duplicate_keys=src_dup_count,
        target_duplicate_keys=tgt_dup_count,
        source_null_keys=src_null_count,
        target_null_keys=tgt_null_count,
        source_only_records=len(src_only_df),
        target_only_records=len(tgt_only_df),
        matched_records=matched_count,
        mismatched_records=mismatched_record_count,
        match_rate_percent=match_rate,
        column_mismatch_counts={k: v for k, v in col_mismatch_counts.items() if v > 0},
        has_key_errors=has_key_errors,
        key_error_message=key_error_msg,
    )

    return ReconciliationResult(
        summary=summary,
        source_only_df=src_only_df,
        target_only_df=tgt_only_df,
        mismatched_df=mismatched_df,
        matched_df=matched_df,
    )
