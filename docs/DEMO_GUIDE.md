# OpenDataGuard — Step-by-Step Demonstration Guide 🛡️

This guide walks you through setting up and demonstrating **OpenDataGuard** for recruiters, engineering peers, or hiring managers. It covers the full lifecycle from launching the web platform to data profiling, quality rule evaluation, two-way dataset reconciliation, and audit reporting.

---

## 1. Prerequisites

- **Python**: Version 3.10, 3.11, or 3.12 installed.
- **Git**: Installed and available in PATH.
- **Hardware / OS**: Windows, macOS, or Linux with at least 2 GB free RAM.
- **Target Repository**: Clone of `https://github.com/RushikeshAlase7879/OpenDataGuard`.

---

## 2. Environment Activation & Verification

Navigate to your project root (e.g., `D:\OpenDataGuard`):

### Windows (PowerShell)
```powershell
cd D:\OpenDataGuard
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux (Bash)
```bash
cd /path/to/OpenDataGuard
source .venv/bin/activate
```

Verify your active Python interpreter and dependencies:
```bash
python --version
pip list
```

---

## 3. Launching the Interactive Platform

Start the local Streamlit application:

```bash
streamlit run app.py
```

Streamlit will launch and display local connection details:
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

Open `http://localhost:8501` in your web browser.

---

## 4. End-to-End Walkthrough

### Scenario A: Profiling a Dataset (`📁 Dataset Explorer`)
1. Click **📁 Dataset Explorer** in the sidebar.
2. Under **Choose Data Source**, select **Load Synthetic Example Dataset**.
3. Click the **Load Sample Source CSV** button.
4. **Observe the Results**:
   - **Summary Cards**: Inspect the total row count (10), column count (7), memory footprint, empty columns, and duplicate rows.
   - **Preview Table**: Browse the first 50 rows of raw customer records.
   - **Basic Statistics**: Expand the **📊 Basic Statistical Summary (df.describe)** section to view numeric percentiles, means, and categorical counts.
   - **Missingness Chart**: Inspect the Plotly bar chart highlighting columns with null records (`email`).

---

### Scenario B: Executing Data Quality Rules (`🛡️ Data Quality Validation`)
1. Navigate to **🛡️ Data Quality Validation** in the sidebar.
2. Confirm that `sample_source.csv` is the target dataset.
3. Under the **Interactive Rule Builder** tab:
   - Check **Check for Missing / Null Values** (select `email`).
   - Check **Check for Duplicate Rows**.
   - Check **Check Unique Identifier / Primary Key** (select `customer_id`).
   - Check **Check Numeric Value Range** (select `age`, min: `18`, max: `120`).
   - Check **Check Categorical Allowed Values** (select `status`, enter: `ACTIVE, INACTIVE, PENDING`).
   - Check **Check Email Syntax Format** (select `email`).
4. Click **Run Interactive Quality Validation**.
5. **Analyze the Audit**:
   - **Continuous DQ Score**: Observe the computed score (e.g. ~74.3%).
   - **Failing Rules**: Notice flagged defects—duplicate record for customer `1001`, null email, invalid age `250`, and non-allowed status `BANNED`.
   - **Drill-down Table**: Review the failing record sample table showing exact defect details.
6. Under **Upload JSON/YAML Rule File** tab:
   - Upload `config/sample_rules.yaml` or `config/sample_rules.json` to demonstrate version-controlled Rules-as-Code.

---

### Scenario C: Two-Way Dataset Reconciliation (`🔄 Dataset Reconciliation`)
Demonstrates diffing an upstream extract against a downstream transformed table:
1. Navigate to **🔄 Dataset Reconciliation** in the sidebar.
2. For **Source Dataset (Golden / Upstream)**, choose **Load Synthetic Example Source** (`examples/sample_source_deduped.csv`).
3. For **Target Dataset (Warehouse / Downstream)**, choose **Load Synthetic Example Target** (`examples/sample_target.csv`).
4. Select Key Column: `customer_id`.
5. Keep default float tolerance (`0.0001`) and leave **Ignore Whitespace Differences** checked.
6. Click **Execute Dataset Reconciliation**.
7. **Inspect Reconciliation Metrics**:
   - **Match Rate**: View the overall match percentage.
   - **Source-Only Records**: Note missing customer records downstream.
   - **Target-Only Records**: Identify unmapped customer `1099`.
   - **Value Mismatches**: Drill down into customer `1005` (status mismatch: `ACTIVE` vs `SUSPENDED`, balance precision variance).

---

### Scenario D: Exporting Multi-Tab Audit Reports
1. In the **🛡️ Data Quality Validation** or **🔄 Dataset Reconciliation** page, locate the **Export Validation Reports** section.
2. Click **Download Multi-Sheet Excel Report (.xlsx)**:
   - Opens in Microsoft Excel or LibreOffice Calc with formatted sheets: `Summary`, `Failed Checks`, and `Failing Rows`.
3. Click **Download Deterministic JSON Report (.json)**:
   - Schema-validated structured output with UTC ISO-8601 timestamps, ideal for CI/CD pipeline artifact storage.

---

### Scenario E: Reviewing Audit History (`📜 Validation History`)
1. Click **📜 Validation History** in the sidebar.
2. View the local SQLite audit ledger (`~/.opendataguard/history.db`).
3. Inspect historical metrics: timestamp, dataset name, rules evaluated, passing/failing rule counts, and DQ scores.
4. Review the Plotly score trend line illustrating data health improvements over time.
5. *(Optional)* Click **Clear Audit History** to reset the local ledger.

---

## 5. Stopping the Application

In your terminal or PowerShell console, press:
```
Ctrl + C
```
The Streamlit web server will gracefully shut down.

---

## 6. Running Automated Tests

To demonstrate test suite rigor to hiring teams:

```powershell
# Using the standalone test runner
python scripts/run_tests.py

# Or directly with pytest
pytest tests/ -v
```

Expected result: **86 passed, 0 failed, 0 skipped** across all 8 test modules.

---

## 7. Troubleshooting & FAQ

| Problem | Likely Cause | Solution |
| :--- | :--- | :--- |
| `Address already in use: 8501` | Another Streamlit or local process is using port 8501. | Launch on an alternative port: `streamlit run app.py --server.port=8502`. |
| `ModuleNotFoundError: No module named 'opendataguard'` | Package not installed in editable mode. | Run `pip install -e .` in your active virtual environment. |
| `psycopg2 driver not installed` | Optional PostgreSQL driver not installed. | SQLite is supported by default. To test PostgreSQL, install `pip install psycopg2-binary`. |
| Large file upload rejected | File exceeds 100 MB default upload limit. | Set environment variable: `$env:OPENDATAGUARD_MAX_UPLOAD_BYTES="209715200"` (200MB). |
