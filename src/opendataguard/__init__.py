"""OpenDataGuard: Open-Source Data Quality, Validation, and Reconciliation Platform."""

__version__ = "1.0.0"

from opendataguard.cli import main
from opendataguard.database import (
    DatabaseConfig,
    create_safe_engine,
    fetch_table_sample,
    get_table_row_count,
    inspect_table_schema,
    list_database_tables,
)
from opendataguard.history import HistoryManager, get_history_db_path
from opendataguard.logging_config import logger, setup_logger
from opendataguard.reconciliation import (
    ReconciliationResult,
    ReconciliationSummary,
    reconcile_datasets,
)
from opendataguard.reports import (
    generate_reconciliation_excel,
    generate_validation_csv,
    generate_validation_excel,
    generate_validation_json,
)
from opendataguard.rules import (
    execute_rule,
    execute_rule_suite,
    load_rules,
    validate_rule_config,
)
from opendataguard.validators import (
    DEFAULT_EMAIL_REGEX,
    DatasetMetadata,
    ValidationResult,
    calculate_data_quality_score,
    check_allowed_values,
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
    load_dataset,
    read_csv_in_chunks,
    validate_file_safety,
)

__all__ = [
    # Core types
    "ValidationResult",
    "DatasetMetadata",
    "ReconciliationSummary",
    "ReconciliationResult",
    "DatabaseConfig",
    "HistoryManager",
    "DEFAULT_EMAIL_REGEX",
    # Ingestion
    "load_dataset",
    "validate_file_safety",
    "read_csv_in_chunks",
    # Validators
    "check_missing_values",
    "check_duplicate_rows",
    "check_key_uniqueness",
    "check_data_types",
    "check_date_validity",
    "check_numeric_validity",
    "check_value_range",
    "check_string_length",
    "check_allowed_values",
    "check_regex_pattern",
    "check_email_format",
    "check_schema_mismatch",
    "check_outliers_iqr",
    "check_row_count",
    "calculate_data_quality_score",
    # Reconciliation
    "reconcile_datasets",
    # Rules
    "load_rules",
    "validate_rule_config",
    "execute_rule",
    "execute_rule_suite",
    # Database
    "create_safe_engine",
    "list_database_tables",
    "inspect_table_schema",
    "get_table_row_count",
    "fetch_table_sample",
    # Reports
    "generate_validation_csv",
    "generate_validation_json",
    "generate_validation_excel",
    "generate_reconciliation_excel",
    # History & logging
    "get_history_db_path",
    "setup_logger",
    "logger",
    # CLI
    "main",
]
