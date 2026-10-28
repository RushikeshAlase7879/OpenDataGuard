# OpenDataGuard Application Screenshots 📸

High-resolution visual previews of the **OpenDataGuard** platform captured directly from live application execution with synthetic demonstration datasets.

---

## Showcase Gallery

### 1. Overview Dashboard
*Visual summary of total audited runs, continuous Data Quality Scores, platform capabilities, and historical score trend charts.*
![Overview Dashboard](01_overview_dashboard.png)

---

### 2. Dataset Explorer & Profiling
*Metadata cards (Rows, Columns, Duplicate Rows, Memory, Empty Columns), raw data preview table, statistical summary expander (`df.describe`), and missingness distribution bar chart.*
![Dataset Explorer](02_dataset_explorer.png)

---

### 3. Data Quality Validation
*Interactive rule configuration, declarative YAML/JSON execution, continuous Data Quality Score gauge, and failing record sample drilldown table.*
![Data Quality Validation](03_data_quality_validation.png)

---

### 4. Two-Way Dataset Reconciliation
*Source vs target 1-to-1 key diffing, tolerance configuration, match rate KPI, and breakdown of value mismatches, source-only, and target-only records.*
![Dataset Reconciliation](04_dataset_reconciliation.png)

---

### 5. Read-Only SQL Database Validation
*Safe connection string parsing, table schema inspection, and bounded table sampling with credential sanitization.*
![SQL Database Validation](05_sql_database_validation.png)

---

### 6. Local Validation History
*Persistent SQLite audit ledger, historical trend visualization, individual run details inspector, and audit purge controls.*
![Validation History](06_validation_history.png)

---

## Automated Screenshot Generation

To regenerate these screenshots automatically via Chrome DevTools Protocol:

```bash
# 1. Start Streamlit in headless mode
streamlit run app.py --server.port 8506 --server.headless true

# 2. In another terminal, run the capture script
python scripts/capture_screenshots.py
```
