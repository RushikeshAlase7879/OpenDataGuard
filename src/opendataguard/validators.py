"""Data validation engine and safe dataset ingestion for OpenDataGuard.

Provides safe loading for CSV and Excel files, robust error handling,
and 10 comprehensive data quality checks returning structured results.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from opendataguard.logging_config import logger

# Maximum allowed upload size in bytes (default 100 MB to avoid memory exhaustion)
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


@dataclass
class ValidationResult:
    """Standardized result for an individual data quality check."""

    check_name: str
    column_name: Optional[str]
    total_records: int
    failed_records: int
    passed: bool
    message: str
    failing_sample: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        return asdict(self)


@dataclass
class DatasetMetadata:
    """High-level summary of an ingested dataset."""

    name: str
    row_count: int
    column_count: int
    columns: List[str]
    dtypes: Dict[str, str]
    empty_columns: List[str]
    memory_usage_bytes: int
    file_size_bytes: Optional[int] = None
    duplicate_columns: List[str] = field(default_factory=list)

    def memory_usage_mb(self) -> float:
        """Return memory footprint in megabytes."""
        return round(self.memory_usage_bytes / (1024 * 1024), 2)


# ============================================================================
# Safe File Ingestion & Metadata Extraction
# ============================================================================


def validate_file_safety(
    file_input: Union[str, Path, io.BytesIO, bytes],
    filename: Optional[str] = None,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Tuple[str, int]:
    """Validate file existence, extension, and size safety.

    Args:
        file_input: Path, BytesIO buffer, or raw bytes.
        filename: Optional filename hint when passing buffer/bytes.
        max_size_bytes: Maximum allowed size in bytes.

    Returns:
        Tuple of (clean_file_extension, file_size_in_bytes).

    Raises:
        ValueError: If file is empty, exceeds size limit, or has unsupported extension.
        FileNotFoundError: If a file path is provided that does not exist.
    """
    clean_name = filename or ""
    size_bytes = 0

    if isinstance(file_input, (str, Path)):
        path = Path(file_input).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Dataset file not found at: {path}")
        clean_name = path.name
        size_bytes = path.stat().st_size
    elif isinstance(file_input, io.BytesIO):
        size_bytes = file_input.getbuffer().nbytes
    elif isinstance(file_input, bytes):
        size_bytes = len(file_input)
    else:
        raise ValueError("Unsupported file input type. Must be str, Path, BytesIO, or bytes.")

    if size_bytes == 0:
        raise ValueError(f"Uploaded file '{clean_name or 'input'}' is completely empty (0 bytes).")

    if size_bytes > max_size_bytes:
        limit_mb = max_size_bytes / (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        raise ValueError(
            f"File '{clean_name}' size ({actual_mb:.2f} MB) exceeds maximum allowed limit ({limit_mb:.2f} MB)."
        )

    # Validate file extension
    ext = Path(clean_name).suffix.lower() if clean_name else ""
    supported_extensions = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}
    if ext and ext not in supported_extensions:
        raise ValueError(
            f"Unsupported file format '{ext}'. OpenDataGuard supports: {', '.join(sorted(supported_extensions))}"
        )

    return ext, size_bytes


def load_dataset(
    file_input: Union[str, Path, io.BytesIO, bytes],
    filename: Optional[str] = None,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    encoding: Optional[str] = None,
    sheet_name: Union[str, int] = 0,
) -> Tuple[pd.DataFrame, DatasetMetadata]:
    """Safely load a dataset into a pandas DataFrame and extract metadata.

    Handles CSV, TSV, and Excel files with automatic encoding fallbacks.
    Does not modify source data or execute any macros/scripts.

    Args:
        file_input: File path, BytesIO, or raw bytes.
        filename: Optional name for reference.
        max_size_bytes: Maximum allowed size.
        encoding: Specific CSV encoding to try first.
        sheet_name: Excel sheet index or name (defaults to first sheet).

    Returns:
        Tuple of (pd.DataFrame, DatasetMetadata).

    Raises:
        ValueError: If file is empty, malformed, or cannot be parsed.
    """
    ext, size_bytes = validate_file_safety(file_input, filename, max_size_bytes)
    resolved_name = filename or (Path(file_input).name if isinstance(file_input, (str, Path)) else "dataset")

    df: Optional[pd.DataFrame] = None

    if ext in {".xlsx", ".xls"}:
        try:
            # Load Excel with openpyxl engine
            df = pd.read_excel(file_input, sheet_name=sheet_name, engine="openpyxl")
        except Exception as exc:
            logger.error("Failed to read Excel file %s: %s", resolved_name, exc)
            raise ValueError(f"Unable to parse Excel file '{resolved_name}': {exc}") from exc
    else:
        # Default to CSV/TSV/delimiter parsing
        encodings_to_try = [encoding] if encoding else ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]
        last_error = None
        sep = "\t" if ext in {".tsv", ".tab"} else None

        for enc in encodings_to_try:
            if not enc:
                continue
            try:
                if isinstance(file_input, io.BytesIO):
                    file_input.seek(0)
                if sep is not None:
                    df = pd.read_csv(file_input, sep=sep, encoding=enc, low_memory=False)
                else:
                    df = pd.read_csv(file_input, encoding=enc, low_memory=False)
                format_lbl = "TSV" if sep == "\t" else "CSV"
                logger.info("Successfully loaded %s '%s' using encoding '%s'", format_lbl, resolved_name, enc)
                break
            except (UnicodeDecodeError, pd.errors.ParserError) as err:
                last_error = err
                continue

        if df is None:
            raise ValueError(
                f"Failed to read CSV/TSV '{resolved_name}'. Attempted encodings ({encodings_to_try}) failed: {last_error}"
            )

    if df.empty:
        raise ValueError(f"Dataset '{resolved_name}' contains no rows or records.")

    # Identify empty columns (columns with all NaN or whitespace-only)
    empty_cols = []
    for col in df.columns:
        if df[col].isna().all():
            empty_cols.append(str(col))

    # Detect duplicate column names if disambiguated by pandas (e.g. 'col.1')
    duplicate_cols = []
    col_str_list = [str(c) for c in df.columns]
    for c in col_str_list:
        if re.search(r"\.\d+$", c):
            base_col = re.sub(r"\.\d+$", "", c)
            if base_col in col_str_list:
                duplicate_cols.append(c)

    metadata = DatasetMetadata(
        name=resolved_name,
        row_count=len(df),
        column_count=len(df.columns),
        columns=[str(c) for c in df.columns],
        dtypes={str(c): str(t) for c, t in df.dtypes.items()},
        empty_columns=empty_cols,
        memory_usage_bytes=int(df.memory_usage(deep=True).sum()),
        file_size_bytes=size_bytes,
        duplicate_columns=duplicate_cols,
    )

    return df, metadata


def read_csv_in_chunks(
    filepath: Union[str, Path],
    chunksize: int = 50_000,
    encoding: str = "utf-8",
) -> Generator[pd.DataFrame, None, None]:
    """Yield DataFrame chunks for memory-efficient processing of large CSV files.

    Args:
        filepath: Path to CSV file.
        chunksize: Number of rows per chunk.
        encoding: File encoding.

    Yields:
        pd.DataFrame chunks.
    """
    for chunk in pd.read_csv(filepath, chunksize=chunksize, encoding=encoding, low_memory=False):
        yield chunk


# ============================================================================
# Core Data Quality Validation Checks
# ============================================================================


def _extract_sample(df: pd.DataFrame, mask: pd.Series, max_samples: int = 10) -> List[Dict[str, Any]]:
    """Helper to extract a sample of failing records as serializable dictionaries."""
    if not mask.any():
        return []
    failing_rows = df[mask].head(max_samples).copy()
    # Replace NaN/inf with None for JSON serializability
    return failing_rows.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")


def check_missing_values(
    df: pd.DataFrame,
    column: Optional[str] = None,
    threshold_percent: float = 0.0,
    treat_empty_as_missing: bool = False,
    max_samples: int = 10,
) -> ValidationResult:
    """Check for missing or null values in a column or across the entire dataset.

    Args:
        df: Input DataFrame.
        column: Optional specific column name. If None, checks across all columns.
        threshold_percent: Allowed percentage of missing values (0.0 to 100.0).
        treat_empty_as_missing: If True, also flags empty strings and whitespace-only strings.
        max_samples: Maximum failing samples to capture.

    Returns:
        ValidationResult with check details.
    """
    total = len(df)
    if total == 0:
        return ValidationResult("missing_values", column, 0, 0, True, "Dataset is empty.")

    if column is not None:
        if column not in df.columns:
            return ValidationResult(
                "missing_values",
                column,
                total,
                0,
                False,
                f"Column '{column}' does not exist in dataset.",
            )
        mask = df[column].isna()
        if treat_empty_as_missing:
            is_str = df[column].apply(lambda x: isinstance(x, str))
            str_empty = is_str & df[column].apply(lambda x: str(x).strip() == "" if isinstance(x, str) else False)
            mask = mask | str_empty
    else:
        mask = df.isna().any(axis=1)
        if treat_empty_as_missing:
            for c in df.columns:
                is_str = df[c].apply(lambda x: isinstance(x, str))
                str_empty = is_str & df[c].apply(lambda x: str(x).strip() == "" if isinstance(x, str) else False)
                mask = mask | str_empty

    failed_count = int(mask.sum())
    fail_rate = (failed_count / total) * 100.0
    passed = fail_rate <= threshold_percent

    msg = (
        f"{failed_count} of {total} records ({fail_rate:.2f}%) contain null/missing values "
        f"(allowed threshold: {threshold_percent:.2f}%)."
    )

    return ValidationResult(
        check_name="missing_values",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, mask, max_samples),
        details={"missing_percentage": round(fail_rate, 2), "threshold_percent": threshold_percent},
    )


def check_duplicate_rows(
    df: pd.DataFrame,
    subset: Optional[List[str]] = None,
    max_samples: int = 10,
) -> ValidationResult:
    """Check for completely duplicate rows or duplicates within a subset of columns.

    Args:
        df: Input DataFrame.
        subset: Optional list of columns to consider for duplicates.
        max_samples: Maximum failing samples to capture.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if total == 0:
        return ValidationResult("duplicate_rows", None, 0, 0, True, "Dataset is empty.")

    if subset:
        missing = [c for c in subset if c not in df.columns]
        if missing:
            return ValidationResult(
                "duplicate_rows",
                ", ".join(subset),
                total,
                0,
                False,
                f"Specified subset columns not found: {missing}",
            )
        mask = df.duplicated(subset=subset, keep=False)
    else:
        mask = df.duplicated(keep=False)

    failed_count = int(mask.sum())
    passed = failed_count == 0
    col_desc = f"columns [{', '.join(subset)}]" if subset else "all columns"
    msg = f"Found {failed_count} duplicate records based on {col_desc}." if not passed else "No duplicate rows found."

    return ValidationResult(
        check_name="duplicate_rows",
        column_name=", ".join(subset) if subset else None,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, mask, max_samples),
        details={"subset": subset},
    )


def check_key_uniqueness(
    df: pd.DataFrame,
    key_columns: Union[str, List[str]],
    max_samples: int = 10,
) -> ValidationResult:
    """Check that selected key column(s) contain unique, non-null values.

    Args:
        df: Input DataFrame.
        key_columns: Column name or list of column names forming the primary/unique key.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    cols = [key_columns] if isinstance(key_columns, str) else list(key_columns)
    col_str = ", ".join(cols)

    missing = [c for c in cols if c not in df.columns]
    if missing:
        return ValidationResult(
            "key_uniqueness",
            col_str,
            total,
            0,
            False,
            f"Key column(s) not found in dataset: {missing}",
        )

    # Duplicates in key
    dup_mask = df.duplicated(subset=cols, keep=False)
    # Nulls in key
    null_mask = df[cols].isna().any(axis=1)

    fail_mask = dup_mask | null_mask
    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    null_count = int(null_mask.sum())
    dup_count = int(dup_mask.sum())

    if passed:
        msg = f"Key '{col_str}' is unique and non-null across all records."
    else:
        msg = f"Key '{col_str}' violation: {dup_count} duplicate values and {null_count} null keys detected."

    return ValidationResult(
        check_name="key_uniqueness",
        column_name=col_str,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"duplicate_key_count": dup_count, "null_key_count": null_count},
    )


def check_data_types(
    df: pd.DataFrame,
    expected_types: Dict[str, str],
    max_samples: int = 10,
) -> ValidationResult:
    """Check that columns conform to expected data types.

    Supported expected types: 'int', 'float', 'numeric', 'string', 'datetime', 'bool'.

    Args:
        df: Input DataFrame.
        expected_types: Mapping of column name to expected type category.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    type_mismatches: Dict[str, Dict[str, str]] = {}
    failing_indices = set()

    for col, expected in expected_types.items():
        if col not in df.columns:
            type_mismatches[col] = {"expected": expected, "actual": "MISSING_COLUMN"}
            continue

        exp = expected.lower().strip()
        series = df[col].dropna()

        if exp in {"int", "integer"}:
            def is_valid_int(val: Any) -> bool:
                try:
                    return float(val).is_integer()
                except (ValueError, TypeError, OverflowError):
                    return False
            invalid_mask = ~df[col].isna() & ~df[col].apply(is_valid_int)

        elif exp in {"float", "numeric", "number"}:
            def is_valid_float(val: Any) -> bool:
                try:
                    float(val)
                    return True
                except (ValueError, TypeError):
                    return False
            invalid_mask = ~df[col].isna() & ~df[col].apply(is_valid_float)

        elif exp in {"datetime", "date"}:
            converted = pd.to_datetime(series, errors="coerce")
            invalid_mask = ~df[col].isna() & converted.isna()

        elif exp in {"bool", "boolean"}:
            valid_bools = {True, False, 1, 0, "true", "false", "1", "0", "yes", "no"}
            invalid_mask = ~df[col].isna() & ~df[col].astype(str).str.lower().isin(valid_bools)

        elif exp in {"str", "string", "text"}:
            # Almost everything can be string, but flag complex objects if any
            invalid_mask = pd.Series(False, index=df.index)

        else:
            type_mismatches[col] = {"expected": expected, "actual": f"UNSUPPORTED_TYPE_SPEC: {expected}"}
            continue

        if invalid_mask.any():
            type_mismatches[col] = {
                "expected": expected,
                "actual_dtype": str(df[col].dtype),
                "invalid_count": int(invalid_mask.sum()),
            }
            failing_indices.update(df[invalid_mask].index.tolist())

    mask = pd.Series(False, index=df.index)
    if failing_indices:
        mask.loc[list(failing_indices)] = True

    failed_count = len(failing_indices) or len([m for m in type_mismatches.values() if "actual" in m])
    passed = len(type_mismatches) == 0

    msg = "All checked columns conform to expected types." if passed else f"Data type mismatches detected: {type_mismatches}"

    return ValidationResult(
        check_name="data_types",
        column_name=", ".join(expected_types.keys()),
        total_records=total,
        failed_records=int(mask.sum()),
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, mask, max_samples),
        details={"mismatches": type_mismatches},
    )


def check_date_validity(
    df: pd.DataFrame,
    column: str,
    date_format: Optional[str] = None,
    min_date: Optional[Union[str, pd.Timestamp]] = None,
    max_date: Optional[Union[str, pd.Timestamp]] = None,
    check_chronological_order: bool = False,
    max_samples: int = 10,
) -> ValidationResult:
    """Validate that dates in a column are parseable, within bounds, and optionally chronological.

    Args:
        df: Input DataFrame.
        column: Column name containing dates.
        date_format: Optional strftime format (e.g. '%Y-%m-%d').
        min_date: Optional earliest valid date.
        max_date: Optional latest valid date.
        check_chronological_order: If True, asserts valid dates appear in ascending chronological order.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("date_validity", column, total, 0, False, f"Column '{column}' not found.")

    non_null_mask = ~df[column].isna()
    non_null_series = df.loc[non_null_mask, column]

    if date_format:
        parsed = pd.to_datetime(non_null_series, format=date_format, errors="coerce")
    else:
        parsed = pd.to_datetime(non_null_series, errors="coerce")

    # Unparseable dates
    unparseable_mask = non_null_mask.copy()
    unparseable_mask.loc[non_null_mask] = parsed.isna()

    # Out of bounds dates
    out_of_bounds_mask = pd.Series(False, index=df.index)
    if min_date is not None:
        min_ts = pd.to_datetime(min_date)
        valid_parsed = parsed.dropna()
        too_early = valid_parsed[valid_parsed < min_ts].index
        out_of_bounds_mask.loc[too_early] = True

    if max_date is not None:
        max_ts = pd.to_datetime(max_date)
        valid_parsed = parsed.dropna()
        too_late = valid_parsed[valid_parsed > max_ts].index
        out_of_bounds_mask.loc[too_late] = True

    # Chronological ordering check
    order_mask = pd.Series(False, index=df.index)
    if check_chronological_order and len(parsed.dropna()) > 1:
        valid_parsed = parsed.dropna()
        prev_dates = valid_parsed.shift(1)
        out_of_order = valid_parsed[valid_parsed < prev_dates].index
        order_mask.loc[out_of_order] = True

    fail_mask = unparseable_mask | out_of_bounds_mask | order_mask
    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    unparseable_count = int(unparseable_mask.sum())
    oob_count = int(out_of_bounds_mask.sum())
    order_count = int(order_mask.sum())

    if passed:
        msg = f"All non-null dates in '{column}' are valid."
    else:
        parts = []
        if unparseable_count > 0:
            parts.append(f"{unparseable_count} unparseable dates")
        if oob_count > 0:
            parts.append(f"{oob_count} out-of-range dates (min: {min_date}, max: {max_date})")
        if order_count > 0:
            parts.append(f"{order_count} dates violating chronological order")
        msg = f"Date validity check failed for '{column}': {', '.join(parts)}."

    return ValidationResult(
        check_name="date_validity",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"unparseable": unparseable_count, "out_of_bounds": oob_count, "out_of_order": order_count},
    )


def check_numeric_validity(
    df: pd.DataFrame,
    column: str,
    allow_inf: bool = False,
    allow_nan: bool = True,
    max_samples: int = 10,
) -> ValidationResult:
    """Validate that values in a column are valid numbers, checking for non-numbers and inf.

    Args:
        df: Input DataFrame.
        column: Column name to validate.
        allow_inf: Whether infinity / -infinity is permitted.
        allow_nan: Whether NaN is permitted.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("numeric_validity", column, total, 0, False, f"Column '{column}' not found.")

    converted = pd.to_numeric(df[column], errors="coerce")
    is_originally_nan = df[column].isna()

    # Non-numeric string or object values: converted is NaN but original was not NaN
    non_numeric_mask = converted.isna() & (~is_originally_nan)

    # Inf check
    inf_mask = pd.Series(False, index=df.index)
    if not allow_inf:
        inf_mask = np.isinf(converted)

    # NaN check
    nan_mask = pd.Series(False, index=df.index)
    if not allow_nan:
        nan_mask = is_originally_nan

    fail_mask = non_numeric_mask | inf_mask | nan_mask
    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    msg = (
        f"Column '{column}' contains valid numeric values."
        if passed
        else f"Column '{column}' has {failed_count} invalid numeric values "
        f"({int(non_numeric_mask.sum())} non-numeric, {int(inf_mask.sum())} infinite, {int(nan_mask.sum())} nulls)."
    )

    return ValidationResult(
        check_name="numeric_validity",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={
            "non_numeric": int(non_numeric_mask.sum()),
            "infinite": int(inf_mask.sum()),
            "nulls": int(nan_mask.sum()),
        },
    )


def check_value_range(
    df: pd.DataFrame,
    column: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    max_samples: int = 10,
) -> ValidationResult:
    """Check that numeric values fall within [min_value, max_value].

    Args:
        df: Input DataFrame.
        column: Column name.
        min_value: Minimum permissible value.
        max_value: Maximum permissible value.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("value_range", column, total, 0, False, f"Column '{column}' not found.")

    num_series = pd.to_numeric(df[column], errors="coerce")
    valid_nums = num_series.dropna()

    fail_mask = pd.Series(False, index=df.index)

    if min_value is not None:
        too_low_idx = valid_nums[valid_nums < min_value].index
        fail_mask.loc[too_low_idx] = True

    if max_value is not None:
        too_high_idx = valid_nums[valid_nums > max_value].index
        fail_mask.loc[too_high_idx] = True

    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    msg = (
        f"All numeric values in '{column}' fall within [{min_value}, {max_value}]."
        if passed
        else f"Column '{column}' has {failed_count} values outside range [{min_value}, {max_value}]."
    )

    return ValidationResult(
        check_name="value_range",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"min_value": min_value, "max_value": max_value},
    )


def check_string_length(
    df: pd.DataFrame,
    column: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    max_samples: int = 10,
) -> ValidationResult:
    """Validate string length bounds for a text column.

    Null values are ignored unless covered by a separate missing_values check.

    Args:
        df: Input DataFrame.
        column: Column name.
        min_length: Minimum allowed character count.
        max_length: Maximum allowed character count.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("string_length", column, total, 0, False, f"Column '{column}' not found.")

    non_null_mask = ~df[column].isna()
    lengths = df.loc[non_null_mask, column].astype(str).str.len()

    fail_mask = pd.Series(False, index=df.index)
    if min_length is not None:
        too_short_idx = lengths[lengths < min_length].index
        fail_mask.loc[too_short_idx] = True

    if max_length is not None:
        too_long_idx = lengths[lengths > max_length].index
        fail_mask.loc[too_long_idx] = True

    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    msg = (
        f"All strings in '{column}' satisfy length bounds [{min_length}, {max_length}]."
        if passed
        else f"Column '{column}' has {failed_count} string length violations."
    )

    return ValidationResult(
        check_name="string_length",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"min_length": min_length, "max_length": max_length},
    )


def check_allowed_values(
    df: pd.DataFrame,
    column: str,
    allowed_values: Iterable[Any],
    case_sensitive: bool = True,
    max_samples: int = 10,
) -> ValidationResult:
    """Check that column values belong to an allowed categorical set.

    Null values are ignored (checked separately by missing_values).

    Args:
        df: Input DataFrame.
        column: Column name.
        allowed_values: Permissible categories.
        case_sensitive: Whether string comparison is case-sensitive.
        max_samples: Maximum failing samples.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("allowed_values", column, total, 0, False, f"Column '{column}' not found.")

    non_null_mask = ~df[column].isna()
    series = df.loc[non_null_mask, column]

    if not case_sensitive:
        allowed_set = {str(v).lower() for v in allowed_values}
        invalid_sub_mask = ~series.astype(str).str.lower().isin(allowed_set)
    else:
        allowed_set = set(allowed_values)
        invalid_sub_mask = ~series.isin(allowed_set)

    fail_mask = pd.Series(False, index=df.index)
    fail_mask.loc[series[invalid_sub_mask].index] = True

    failed_count = int(fail_mask.sum())
    passed = failed_count == 0

    msg = (
        f"All categorical values in '{column}' are valid."
        if passed
        else f"Column '{column}' has {failed_count} values outside allowed set: {list(allowed_values)[:10]}."
    )

    return ValidationResult(
        check_name="allowed_values",
        column_name=column,
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"allowed_values": list(allowed_values), "case_sensitive": case_sensitive},
    )


def check_schema_mismatch(
    df: pd.DataFrame,
    expected_columns: List[str],
    strict: bool = False,
) -> ValidationResult:
    """Validate that expected columns are present, and optionally that no unexpected columns exist.

    Args:
        df: Input DataFrame.
        expected_columns: List of column names that must exist.
        strict: If True, flags any column in df that is not in expected_columns.

    Returns:
        ValidationResult.
    """
    total = len(df)
    actual_columns = [str(c) for c in df.columns]
    missing_cols = [c for c in expected_columns if c not in actual_columns]
    unexpected_cols = [c for c in actual_columns if c not in expected_columns] if strict else []

    passed = len(missing_cols) == 0 and len(unexpected_cols) == 0
    failed_count = len(missing_cols) + len(unexpected_cols)

    if passed:
        msg = f"Schema conforms to expected {len(expected_columns)} columns."
    else:
        parts = []
        if missing_cols:
            parts.append(f"Missing required columns: {missing_cols}")
        if unexpected_cols:
            parts.append(f"Unexpected extra columns: {unexpected_cols}")
        msg = "; ".join(parts)

    return ValidationResult(
        check_name="schema_mismatch",
        column_name=", ".join(expected_columns),
        total_records=total,
        failed_records=failed_count,
        passed=passed,
        message=msg,
        details={
            "expected_columns": expected_columns,
            "actual_columns": actual_columns,
            "missing_columns": missing_cols,
            "unexpected_columns": unexpected_cols,
        },
    )


DEFAULT_EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"


def check_regex_pattern(
    df: pd.DataFrame,
    column: str,
    pattern: str,
    max_samples: int = 10,
) -> ValidationResult:
    """Validate that text values in a column match a regular expression pattern.

    Null values are ignored (checked separately by missing_values).

    Args:
        df: Input DataFrame.
        column: Column name to validate.
        pattern: Regular expression pattern string.
        max_samples: Maximum failing samples to capture.

    Returns:
        ValidationResult.
    """
    total = len(df)
    if column not in df.columns:
        return ValidationResult("regex_pattern", column, total, 0, False, f"Column '{column}' not found.")

    try:
        pat = re.compile(pattern)
    except re.error as err:
        return ValidationResult("regex_pattern", column, total, 0, False, f"Invalid regex pattern '{pattern}': {err}")

    non_null_mask = ~df[column].isna()
    if not non_null_mask.any():
        return ValidationResult(
            check_name="regex_pattern",
            column_name=column,
            total_records=total,
            failed_records=0,
            passed=True,
            message=f"No non-null records to evaluate for pattern in '{column}'.",
            details={"pattern": pattern},
        )

    series_str = df.loc[non_null_mask, column].astype(str)
    matches = series_str.apply(lambda v: bool(pat.search(v)))
    fail_mask = pd.Series(False, index=df.index)
    fail_mask.loc[series_str[~matches].index] = True

    failed_cnt = int(fail_mask.sum())
    passed = failed_cnt == 0

    msg = (
        f"All records in '{column}' match pattern '{pattern}'."
        if passed
        else f"Found {failed_cnt} records in '{column}' not matching pattern '{pattern}'."
    )

    return ValidationResult(
        check_name="regex_pattern",
        column_name=column,
        total_records=total,
        failed_records=failed_cnt,
        passed=passed,
        message=msg,
        failing_sample=_extract_sample(df, fail_mask, max_samples),
        details={"pattern": pattern},
    )


def check_email_format(
    df: pd.DataFrame,
    column: str,
    pattern: str = DEFAULT_EMAIL_REGEX,
    max_samples: int = 10,
) -> ValidationResult:
    """Validate that text values in a column conform to valid email syntax.

    Null values are ignored (checked separately by missing_values).

    Args:
        df: Input DataFrame.
        column: Column name containing email addresses.
        pattern: Regular expression pattern for email validation.
        max_samples: Maximum failing samples to capture.

    Returns:
        ValidationResult.
    """
    res = check_regex_pattern(df, column=column, pattern=pattern, max_samples=max_samples)
    res.check_name = "email_format"
    if not res.passed:
        if f"Column '{column}' not found" not in res.message and "Invalid regex" not in res.message:
            res.message = f"Column '{column}' contains {res.failed_records} invalid email address(es)."
    else:
        res.message = f"All non-null email addresses in '{column}' conform to valid format."
    return res


# ============================================================================
# Data Quality Score Calculation
# ============================================================================


def calculate_data_quality_score(results: List[ValidationResult]) -> float:
    """Calculate overall Data Quality Score (0.0 to 100.0).

    Formula Documentation:
    Each validation check is scored on its individual pass-rate ratio:
        check_score = max(0.0, 1.0 - (failed_records / total_records))
    For schema / structural checks where failed_records represents column count
    rather than row count, binary scoring (1.0 for pass, 0.0 for fail) is applied.

    The final overall score is the arithmetic mean across all executed checks:
        DQ_Score = (sum(check_scores) / total_checks) * 100

    This provides a deterministic, transparent, and continuous quality metric.

    Args:
        results: List of ValidationResult objects.

    Returns:
        Quality score as float rounded to 2 decimal places (0.0 - 100.0).
    """
    if not results:
        return 100.0

    scores = []
    for r in results:
        if r.total_records == 0 or r.check_name == "schema_mismatch":
            scores.append(1.0 if r.passed else 0.0)
        else:
            ratio = min(1.0, max(0.0, r.failed_records / r.total_records))
            scores.append(1.0 - ratio)

    avg_score = (sum(scores) / len(scores)) * 100.0
    return round(float(avg_score), 2)
