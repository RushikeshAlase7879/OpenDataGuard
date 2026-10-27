# Changelog

All notable changes to **OpenDataGuard** are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-27

### Added
- **Core Ingestion Engine**: Safe parsing of CSV, TSV, and Excel files with encoding detection and 100MB size bounds.
- **10 Data Quality Validators**:
  - Missing and null value checks (`check_missing_values`)
  - Duplicate row detection (`check_duplicate_rows`)
  - Selected key uniqueness and non-null validation (`check_key_uniqueness`)
  - Data type conformity (`check_data_types`)
  - Date validity and chronological bounding (`check_date_validity`)
  - Numeric validity and inf/nan detection (`check_numeric_validity`)
  - Min/max range constraints (`check_value_range`)
  - String length bounds (`check_string_length`)
  - Categorical domain verification (`check_allowed_values`)
  - Schema mismatch and missing column auditing (`check_schema_mismatch`)
- **Dataset Reconciliation Engine**:
  - Key-based 1-to-1 diffing between source and target datasets
  - Cell-by-cell discrepancy tracking
  - Floating-point numeric comparison with absolute & relative tolerance (`float_atol`, `float_rtol`)
  - Duplicate key and null key guards to prevent erroneous cartesian joins
- **Declarative Rule Engine**:
  - JSON and YAML specification parsing (`load_rules`)
  - Strict rule schema validation with descriptive rejection errors
  - Batch rule execution (`execute_rule_suite`)
- **SQL Database Auditing**:
  - SQLAlchemy 2.0 integration for SQLite (default) and PostgreSQL
  - Safe credential masking across logs and output
  - Table schema reflection and bounded row sampling
- **Reporting Engine**:
  - Multi-sheet Excel export (`Summary`, `Validation Details`, `Failing Samples`)
  - CSV report output
  - Deterministic JSON summary reporting with UTC timestamps
  - Detailed reconciliation Excel workbook
- **Audit History**:
  - SQLite metadata persistence in `~/.opendataguard/history.db`
  - Zero raw data storage to preserve data privacy
  - History viewer and safe deletion controls
- **Interactive Streamlit Web Dashboard**:
  - Overview metrics & quality score trends
  - Interactive Dataset Explorer
  - Validation Runner with scorecard & failure drill-down
  - Dataset Reconciliation dashboard with side-by-side diff tabs
  - SQL Database Inspector
  - Historical Run Audit log
  - Settings & documentation reference
- **Automated Test Suite**:
  - 41 unit tests covering all core modules with 100% pass rate
- **CI/CD Pipeline**:
  - Multi-OS (Ubuntu, Windows) and multi-version (Python 3.10, 3.11, 3.12) GitHub Actions workflow
