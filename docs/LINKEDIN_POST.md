# LinkedIn Announcement Post Draft 📢

*Status: Prepared for author review. Not published automatically.*

---

## Post Copy

I am excited to share **OpenDataGuard**, an open-source Python platform I built for automated data quality validation, dataset reconciliation, and audit reporting! 🛡️

### Why I Built OpenDataGuard
In modern analytics and data engineering workflows, silent data corruption is an expensive problem:
- Upstream schema regressions or null spikes break executive dashboards without triggering pipeline warnings.
- Cloud migrations and ETL transformations require tedious, manual spot-checking between source and target warehouses.
- Traditional SQL joins for reconciliation often suffer from Cartesian explosion when duplicate keys are present.
- Most enterprise data observability tools require expensive SaaS subscriptions or risk data confidentiality by sending company data over the wire.

OpenDataGuard solves this with a 100% local, lightweight, and deterministic open-source engine.

---

### Core Technical Capabilities
- **12 Comprehensive Quality Checks**: Missing values (with empty string detection), row/key duplicates, regex syntax, RFC-compliant email validation, data type conformity, chronological date ranges, allowed domain values, string length boundaries, and IQR outlier detection.
- **Continuous Data Quality Scoring**: A deterministic scoring algorithm ($0.0\% - 100.0\%$) aggregating row-level defect ratios and structural schema compliance.
- **Two-Way Dataset Reconciliation**: 1-to-1 key-based diffing with floating-point tolerance (`atol`/`rtol`), whitespace stripping, and duplicate/null key guards to prevent Cartesian explosion.
- **Rules-as-Code Engine**: Version-control your data quality assertions via declarative JSON or YAML specifications.
- **Read-Only SQL Audits**: Safe schema inspection and bounded preview sampling via SQLAlchemy 2.0 (SQLite default, optional PostgreSQL) with systematic credential masking (`admin:***@host`).
- **Audit Ledger & Reporting**: Local SQLite execution ledger tracking metrics across restarts, plus one-click exports to multi-tab Excel workbooks, CSV, and schema-validated JSON reports.
- **Interactive Streamlit Dashboard**: 7 interactive pages with Plotly visualizations, failing record drill-downs, and instant synthetic dataset loaders.

---

### Engineering & Testing Rigor
A data quality tool must itself be thoroughly tested. OpenDataGuard is backed by:
- **86 automated tests** across unit, integration, and UI modules with a 100% pass rate in ~16 seconds.
- Streamlit's official `AppTest` framework to verify UI rendering and session state stability across all 7 dashboard pages.
- Multi-OS GitHub Actions CI matrix testing Python 3.10, 3.11, and 3.12 on both Ubuntu and Windows runners.

---

### Key Takeaways from Building This
Building OpenDataGuard reinforced several important software and data engineering practices:
1. **Defensive Non-Mutation**: Ensuring validation functions never mutate caller DataFrames during evaluation.
2. **Tolerance-Aware Diffs**: Handling floating-point precision differences when comparing source and target numbers.
3. **Application Security First**: Masking sensitive database connection URIs in logging handlers and validating table names against catalog reflection to eliminate SQL injection vectors.

Check out the project, explore the code, or try it locally:
👉 **GitHub Repository**: https://github.com/RushikeshAlase7879/OpenDataGuard

Feedback, suggestions, and GitHub stars are always welcome! ⭐

#DataEngineering #Python #DataQuality #OpenSource #Streamlit #Pandas #SQLAlchemy #SoftwareEngineering #DataOps #AnalyticsEngineering
