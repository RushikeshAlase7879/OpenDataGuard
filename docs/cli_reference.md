# OpenDataGuard CLI Reference Manual

This manual provides a detailed technical specification for the native `opendataguard` Command-Line Interface (CLI).

---

## 1. Overview & Global Options

The `opendataguard` CLI is registered as a console script entry point upon package installation (`pip install opendataguard` or `pip install -e .`).

### Syntax
```bash
opendataguard [-h] [-V] {validate,reconcile,ui,version} ...
```

### Global Options
| Option | Description |
| :--- | :--- |
| `-h`, `--help` | Show top-level command usage and exit. |
| `-V`, `--version` | Show program version (`OpenDataGuard 1.1.0`) and exit. |

---

## 2. Subcommands

### 2.1 `opendataguard validate`

Execute automated data quality checks against a tabular dataset using declarative JSON or YAML rules.

#### Syntax
```bash
opendataguard validate -d <DATA_PATH> -r <RULES_PATH> [options]
```

#### Options
| Flag | Long Option | Required | Type / Choices | Default | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `-d` | `--data` | **Yes** | Path | N/A | Path to input dataset file (`.csv`, `.tsv`, `.xlsx`, `.xls`, `.parquet`). |
| `-r` | `--rules` | **Yes** | Path | N/A | Path to declarative rule definition file (`.json` or `.yaml`). |
| `-o` | `--output` | No | Path | `None` | Path to save the generated audit report (e.g. `report.json`, `report.xlsx`, `report.csv`). |
| `-f` | `--format` | No | `json`, `csv`, `xlsx` | Inferred | Output format. Overrides output file extension. |
| `-n` | `--dataset-name` | No | String | Stem of data file | Logical dataset name recorded in reports and logs. |
| `-s` | `--min-score` | No | Float (`0.0`–`100.0`)| `None` | Minimum passing score. If actual score $<$ min_score, exits with code `1`. |
| | `--strict` | No | Flag | `False` | Fail if any warning or check failure occurs. |

#### Exit Codes
- **`0`**: All rules passed and Data Quality Score $\ge$ `--min-score` (if specified).
- **`1`**: One or more validation checks failed, or Data Quality Score $<$ `--min-score`.
- **`2`**: Missing data/rule file, unparseable CSV/Excel, malformed rule configuration, or operational error.

#### Examples
```bash
# Validate customer CSV against YAML rules
opendataguard validate --data data/customers.csv --rules config/customer_rules.yaml

# Enforce a 95% minimum quality score and export a multi-sheet Excel report
opendataguard validate -d data/transactions.csv -r config/rules.json -o audit_report.xlsx -s 95.0

# Export structured JSON report to standard directory
opendataguard validate -d data/inventory.xlsx -r config/rules.yaml -o reports/inventory_report.json
```

---

### 2.2 `opendataguard reconcile`

Perform row-by-row two-way dataset reconciliation between source and target datasets on primary or composite keys.

#### Syntax
```bash
opendataguard reconcile -s <SOURCE_PATH> -t <TARGET_PATH> -k <KEYS...> [options]
```

#### Options
| Flag | Long Option | Required | Type / Choices | Default | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `-s` | `--source` | **Yes** | Path | N/A | Path to source dataset file (`.csv`, `.xlsx`, `.parquet`). |
| `-t` | `--target` | **Yes** | Path | N/A | Path to target dataset file (`.csv`, `.xlsx`, `.parquet`). |
| `-k` | `--keys` | **Yes** | String(s) | N/A | Primary or composite key column names. Accepts space- or comma-separated lists. |
| | `--source-name` | No | String | Source file stem | Label for source dataset in reports. |
| | `--target-name` | No | String | Target file stem | Label for target dataset in reports. |
| | `--atol` | No | Float | `1e-5` | Absolute numeric tolerance for float comparisons. |
| | `--rtol` | No | Float | `1e-5` | Relative numeric tolerance for float comparisons. |
| | `--no-ignore-whitespace` | No | Flag | `False` | Do NOT strip leading/trailing whitespace when comparing strings. |
| | `--ignore-case` | No | Flag | `False` | Perform case-insensitive string comparisons. |
| `-c` | `--columns` | No | String(s) | All common | Specific subset of columns to compare. |
| `-o` | `--output` | No | Path | `None` | Path to save reconciliation report (`.xlsx` or `.json`). |
| `-f` | `--format` | No | `xlsx`, `json` | Inferred | Output format. Overrides output file extension. |

#### Exit Codes
- **`0`**: 100% matched records with zero value mismatches, zero source-only rows, zero target-only rows, and zero key errors.
- **`1`**: Discrepancies detected (value mismatches, row count differences, orphan rows, or duplicate key warnings).
- **`2`**: Missing key column in either dataset, file not found, unparseable input, or operational error.

#### Examples
```bash
# Single key reconciliation
opendataguard reconcile --source data/prod_users.csv --target data/dw_users.csv --keys user_id

# Composite key reconciliation with custom float tolerance
opendataguard reconcile -s source.csv -t target.csv -k country store_id --atol 0.01 --rtol 0.001

# Comma-separated keys with multi-sheet Excel export
opendataguard reconcile -s source.csv -t target.csv -k "region,store_id" -o reconciliation_results.xlsx
```

---

### 2.3 `opendataguard ui`

Launch the OpenDataGuard interactive Streamlit web application.

#### Syntax
```bash
opendataguard ui [options]
```

#### Options
| Flag | Long Option | Required | Type | Default | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `-p` | `--port` | No | Integer | `8501` | Port number for the Streamlit server. |
| | `--host` | No | String | `"localhost"` | Host address for the Streamlit server. |
| | `--no-browser` | No | Flag | `False` | Run Streamlit in headless mode without launching a browser window. |
| | `--app-path` | No | Path | Auto-detected | Explicit path to OpenDataGuard `app.py`. |

#### Exit Codes
- **`0`**: Web application stopped cleanly (e.g. via `Ctrl+C`).
- **`2`**: Streamlit is not installed, or `app.py` could not be located.

#### Examples
```bash
# Standard browser launch
opendataguard ui

# Headless server on custom port for Docker or remote environments
opendataguard ui --host 0.0.0.0 --port 8555 --no-browser
```

---

### 2.4 `opendataguard version`

Display version information, Python runtime, and host operating system.

#### Syntax
```bash
opendataguard version
```

#### Example Output
```text
OpenDataGuard 1.1.0 (Python 3.12.4 on Windows)
```

---

## 3. CI/CD Integration Recipes

### GitHub Actions
```yaml
- name: Validate Production Data Quality
  run: |
    opendataguard validate \
      --data data/latest_export.csv \
      --rules config/production_rules.yaml \
      --output validation_summary.json \
      --min-score 98.0
```

### Makefile Target
```makefile
.PHONY: quality-check
quality-check:
	opendataguard validate --data data/sample.csv --rules config/rules.yaml --strict
	opendataguard reconcile --source data/src.csv --target data/tgt.csv --keys id
```
