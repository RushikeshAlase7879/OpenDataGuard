# OpenDataGuard Application Screenshots Guide 📸

This directory is designated for high-resolution visual previews of the **OpenDataGuard** platform for repository visitors, documentation, and portfolio showcases.

---

## Recommended Showcase Screenshots

When showcasing OpenDataGuard to recruiters or hiring teams, capture the following 6 core screens:

| Screenshot File | Page in App | Demonstration Focus |
| :--- | :--- | :--- |
| `01_overview_dashboard.png` | **📊 Overview** | Metric cards (Audited Runs, Average DQ Score, Total Rules Run), capabilities overview, Plotly historical DQ trend chart. |
| `02_dataset_explorer.png` | **📁 Dataset Explorer** | Data preview table, metadata summary cards, `df.describe` basic statistics expander, missingness bar chart. |
| `03_data_quality_validation.png` | **🛡️ Data Quality Validation** | DQ Score gauge (e.g. ~74%), failed checks list, failing record sample drilldown table. |
| `04_dataset_reconciliation.png` | **🔄 Dataset Reconciliation** | Source vs target comparison, match rate KPI, source-only, target-only, and value mismatch breakdown. |
| `05_sql_database_validation.png` | **🗄️ SQL Database Validation** | SQLite connection preview, schema column inspector, bounded table sampler. |
| `06_validation_history.png` | **📜 Validation History** | Persistent SQLite audit ledger, historical trend visualization, individual run details inspector. |

---

## How to Capture Real Application Screenshots

Because headless browsers in headless CI/server sandboxes lack a hardware display context, capturing full-fidelity screenshots directly from your desktop browser provides the best visual quality:

1. **Activate the Virtual Environment**:
   ```powershell
   cd D:\OpenDataGuard
   .\.venv\Scripts\Activate.ps1
   ```

2. **Launch the Application**:
   ```bash
   streamlit run app.py
   ```

3. **Navigate & Capture**:
   - Open `http://localhost:8501` in your browser (Chrome, Edge, or Firefox).
   - In **📁 Dataset Explorer**, click **Load Synthetic Example Dataset** -> **Load Sample Source CSV**.
   - Use Windows Snipping Tool (`Win + Shift + S`) or browser full-page screenshot (`Ctrl + Shift + I` -> `Ctrl + Shift + P` -> "Capture full size screenshot").
   - Save the images into `docs/screenshots/` following the filenames in the table above.

4. **Git Inclusion**:
   - Commit the generated `.png` files to include them in your GitHub portfolio showcase.
