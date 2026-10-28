"""OpenDataGuard - Interactive Streamlit Web Platform.

Open-Source Data Quality, Validation, and Reconciliation Platform.
Features:
- Dataset Upload & Profiling
- 12 Configurable Data Quality Checks
- Declarative JSON/YAML Rule Runner
- Dataset Reconciliation & Diff Engine
- Safe Read-Only SQL Database Validator
- Historical Auditing & Run Trends
- One-Click Report Generation (Excel, CSV, JSON)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

from opendataguard.database import (
    DatabaseConfig,
    create_safe_engine,
    fetch_table_sample,
    get_table_row_count,
    inspect_table_schema,
    list_database_tables,
)
from opendataguard.history import HistoryManager
from opendataguard.logging_config import logger
from opendataguard.reconciliation import reconcile_datasets
from opendataguard.reports import (
    generate_reconciliation_excel,
    generate_validation_csv,
    generate_validation_excel,
    generate_validation_json,
)
from opendataguard.rules import execute_rule_suite, load_rules
from opendataguard.validators import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
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
    check_regex_pattern,
    check_schema_mismatch,
    check_string_length,
    check_value_range,
    load_dataset,
)

# Set page configuration
st.set_page_config(
    page_title="OpenDataGuard | Data Quality & Reconciliation",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for crisp, modern appearance
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .stAlert {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_history_mgr() -> HistoryManager:
    """Initialize singleton history manager."""
    return HistoryManager()


history_mgr = get_history_mgr()

# Initialize session state objects
if "current_df" not in st.session_state:
    st.session_state["current_df"] = None
if "current_metadata" not in st.session_state:
    st.session_state["current_metadata"] = None
if "validation_results" not in st.session_state:
    st.session_state["validation_results"] = None
if "source_df" not in st.session_state:
    st.session_state["source_df"] = None
if "target_df" not in st.session_state:
    st.session_state["target_df"] = None
if "reconcile_result" not in st.session_state:
    st.session_state["reconcile_result"] = None

# Sidebar Navigation
st.sidebar.image("https://raw.githubusercontent.com/feathericons/feather/master/icons/shield.svg", width=48)
st.sidebar.title("OpenDataGuard")
st.sidebar.caption("v1.0.0 • Open-Source Data Quality Platform")

PAGES = [
    "📊 Overview",
    "📁 Dataset Explorer",
    "🛡️ Data Quality Validation",
    "🔄 Dataset Reconciliation",
    "🗄️ SQL Database Validation",
    "📜 Validation History",
    "⚙️ Settings & Documentation",
]
page_idx = 0
if "page" in st.query_params:
    p = st.query_params["page"].lower()
    for idx, name in enumerate(PAGES):
        if p in name.lower():
            page_idx = idx
            break

if st.query_params.get("sample") == "1":
    if st.session_state.get("current_df") is None:
        sample_path = Path(__file__).parent / "examples" / "sample_source.csv"
        if sample_path.exists():
            st.session_state["current_df"], st.session_state["current_metadata"] = load_dataset(sample_path, filename="sample_source.csv")
    if st.session_state.get("source_df") is None:
        src_path = Path(__file__).parent / "examples" / "sample_source_deduped.csv"
        tgt_path = Path(__file__).parent / "examples" / "sample_target.csv"
        if src_path.exists() and tgt_path.exists():
            st.session_state["source_df"], _ = load_dataset(src_path, filename="sample_source_deduped.csv")
            st.session_state["target_df"], _ = load_dataset(tgt_path, filename="sample_target.csv")

navigation = st.sidebar.radio("Navigation", PAGES, index=page_idx)


# ============================================================================
# Page 1: Overview
# ============================================================================
if navigation == "📊 Overview":
    st.markdown('<div class="main-header">🛡️ OpenDataGuard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Open-Source Data Quality, Validation, and Reconciliation Platform for Modern Data Teams</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    history_df = history_mgr.get_history(limit=100)

    total_runs = len(history_df)
    avg_score = round(history_df["dq_score"].mean(), 1) if not history_df.empty else None
    avg_score_str = f"{avg_score}%" if avg_score is not None else "N/A"
    total_checks_run = int(history_df["total_checks"].sum()) if not history_df.empty else 0
    total_rows_inspected = int(history_df["total_rows"].sum()) if not history_df.empty else 0

    col1.metric("Audited Runs", f"{total_runs:,}")
    col2.metric("Average DQ Score", avg_score_str)
    col3.metric("Total Rules Run", f"{total_checks_run:,}")
    col4.metric("Total Rows Evaluated", f"{total_rows_inspected:,}")

    st.markdown("---")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("Platform Capabilities")
        st.markdown(
            """
            - **Dataset Profiling**: Instantly load and inspect CSV, TSV, and Excel files with automated encoding detection and null profiling.
            - **12 Core Quality Checks**: Validate missingness, unique keys, regex, email syntax, data types, date formats/ordering, value ranges, string lengths, and categorical domains.
            - **Rule-as-Code Engine**: Version-control data quality assertions via declarative JSON or YAML specifications.
            - **Two-Way Reconciliation**: Perform key-based diffs between source & target tables with floating-point tolerance and zero chance of many-to-many join duplication.
            - **Read-Only SQL Audits**: Connect securely to SQLite and PostgreSQL tables without credential logging or write side-effects.
            - **Audit Trail & Reports**: Save execution history locally in SQLite and export multi-sheet Excel, CSV, or JSON summaries.
            """
        )

        st.info("💡 **Quick Start**: Head to **📁 Dataset Explorer** to upload your data or try the pre-loaded synthetic examples.")

    with col_right:
        st.subheader("Recent Quality Trends")
        if not history_df.empty:
            fig = px.line(
                history_df.sort_values("timestamp_utc"),
                x="timestamp_utc",
                y="dq_score",
                title="Historical DQ Score Trend",
                markers=True,
                labels={"timestamp_utc": "Audit Timestamp (UTC)", "dq_score": "Score (%)"},
            )
            fig.update_layout(yaxis=dict(range=[0, 105]), margin=dict(l=20, r=20, t=40, b=20), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No audit history found yet. Run your first validation to see real-time trends.")


# ============================================================================
# Page 2: Dataset Explorer
# ============================================================================
elif navigation == "📁 Dataset Explorer":
    st.subheader("📁 Dataset Explorer & Ingestion")
    st.caption("Upload and profile local CSV or Excel files safely.")

    upload_source = st.radio(
        "Choose Data Source:",
        ["Upload File", "Load Synthetic Example Dataset"],
        horizontal=True,
    )

    df_loaded = None
    meta_loaded = None

    if upload_source == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload CSV or Excel file (Max 100MB):",
            type=["csv", "tsv", "xlsx", "xls"],
            help="Securely parsed locally. Source data is never modified.",
        )
        if uploaded_file is not None:
            try:
                with st.spinner("Analyzing dataset..."):
                    bytes_data = uploaded_file.read()
                    df_loaded, meta_loaded = load_dataset(
                        file_input=io.BytesIO(bytes_data),
                        filename=uploaded_file.name,
                    )
            except Exception as err:
                st.error(f"Error loading file: {err}")
    else:
        # Load sample synthetic file
        sample_path = Path(__file__).parent / "examples" / "sample_source.csv"
        if sample_path.exists():
            if st.button("Load Sample Source CSV"):
                try:
                    df_loaded, meta_loaded = load_dataset(sample_path, filename="sample_source.csv")
                except Exception as err:
                    st.error(f"Error loading sample: {err}")
        else:
            st.warning("Sample dataset not found at examples/sample_source.csv")

    if df_loaded is not None and meta_loaded is not None:
        st.session_state["current_df"] = df_loaded
        st.session_state["current_metadata"] = meta_loaded
        st.success(f"Successfully loaded '{meta_loaded.name}'")

    current_df = st.session_state.get("current_df")
    current_meta = st.session_state.get("current_metadata")

    if current_df is not None and current_meta is not None:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Rows", f"{current_meta.row_count:,}")
        m2.metric("Columns", f"{current_meta.column_count}")
        m3.metric("Duplicate Rows", f"{int(current_df.duplicated().sum()):,}")
        m4.metric("Memory Footprint", f"{current_meta.memory_usage_mb()} MB")
        m5.metric("Empty Columns", f"{len(current_meta.empty_columns)}")

        st.markdown("### Data Preview (First 50 Rows)")
        st.dataframe(current_df.head(50), use_container_width=True)

        with st.expander("📊 Basic Statistical Summary (df.describe)", expanded=False):
            st.dataframe(current_df.describe(include="all"), use_container_width=True)

        st.markdown("### Schema & Column Profiling")
        profile_data = []
        for col in current_df.columns:
            null_count = int(current_df[col].isna().sum())
            null_pct = round((null_count / len(current_df)) * 100, 2)
            unique_count = int(current_df[col].nunique())
            profile_data.append({
                "Column Name": col,
                "Inferred Type": str(current_df[col].dtype),
                "Null Records": null_count,
                "Missing %": null_pct,
                "Unique Values": unique_count,
            })
        profile_df = pd.DataFrame(profile_data)
        st.dataframe(profile_df, use_container_width=True)

        # Missingness visualization
        if profile_df["Missing %"].sum() > 0:
            st.markdown("### Missing Value Distribution")
            fig = px.bar(
                profile_df,
                x="Column Name",
                y="Missing %",
                color="Missing %",
                color_continuous_scale="Reds",
                title="Missing Value Percentage by Column",
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# Page 3: Data Quality Validation
# ============================================================================
elif navigation == "🛡️ Data Quality Validation":
    st.subheader("🛡️ Data Quality Validation")
    st.caption("Execute interactive quality checks or upload declarative JSON/YAML rule files.")

    current_df = st.session_state.get("current_df")
    current_meta = st.session_state.get("current_metadata")

    if current_df is None:
        st.warning("Please upload or select a dataset first in the 📁 Dataset Explorer page.")
    else:
        st.info(f"Target Dataset: **{current_meta.name}** ({len(current_df):,} rows, {len(current_df.columns)} columns)")

        tab_interactive, tab_rules = st.tabs(["Interactive Rule Builder", "Upload JSON/YAML Rule File"])

        results: List[ValidationResult] = []

        with tab_interactive:
            st.markdown("Select and configure validation checks to run:")
            col_a, col_b = st.columns(2)

            with col_a:
                run_null_check = st.checkbox("Check for Missing / Null Values", value=True)
                null_cols = st.multiselect("Columns for null check (leave blank for all):", options=list(current_df.columns))

                run_dup_check = st.checkbox("Check for Entire Duplicate Rows", value=True)

                run_key_check = st.checkbox("Check Key Column Uniqueness", value=False)
                key_cols = st.multiselect("Key Column(s):", options=list(current_df.columns))

                run_allowed_check = st.checkbox("Categorical Domain Check (Allowed Values)", value=False)
                cat_col = st.selectbox("Category Column:", options=list(current_df.columns), key="cat_col")
                cat_vals = st.text_input("Allowed Values (comma separated):", "ACTIVE, INACTIVE, PENDING")

            with col_b:
                run_num_range = st.checkbox("Numeric Range Check", value=False)
                num_col = st.selectbox("Numeric Column:", options=list(current_df.columns), key="num_col")
                c_min, c_max = st.columns(2)
                min_v = c_min.number_input("Min Value:", value=0.0)
                max_v = c_max.number_input("Max Value:", value=100.0)

                run_len_check = st.checkbox("String Length Check", value=False)
                str_col = st.selectbox("Text Column:", options=list(current_df.columns), key="str_col")
                l_min, l_max = st.columns(2)
                min_l = l_min.number_input("Min Length:", value=1, min_value=0)
                max_l = l_max.number_input("Max Length:", value=50, min_value=1)

                run_date_check = st.checkbox("Date Validity Check", value=False)
                date_col = st.selectbox("Date Column:", options=list(current_df.columns), key="date_col")

                run_email_check = st.checkbox("Email Format Validity Check", value=False)
                email_col = st.selectbox("Email Column:", options=list(current_df.columns), key="email_col")

            if st.button("🚀 Run Selected Interactive Checks", type="primary"):
                with st.spinner("Executing quality checks..."):
                    if run_null_check:
                        if null_cols:
                            for c in null_cols:
                                results.append(check_missing_values(current_df, column=c))
                        else:
                            results.append(check_missing_values(current_df))

                    if run_dup_check:
                        results.append(check_duplicate_rows(current_df))

                    if run_key_check and key_cols:
                        results.append(check_key_uniqueness(current_df, key_columns=key_cols))

                    if run_allowed_check and cat_col:
                        vals = [v.strip() for v in cat_vals.split(",") if v.strip()]
                        results.append(check_allowed_values(current_df, column=cat_col, allowed_values=vals))

                    if run_num_range and num_col:
                        results.append(check_value_range(current_df, column=num_col, min_value=min_v, max_value=max_v))

                    if run_len_check and str_col:
                        results.append(check_string_length(current_df, column=str_col, min_length=int(min_l), max_length=int(max_l)))

                    if run_date_check and date_col:
                        results.append(check_date_validity(current_df, column=date_col))

                    if run_email_check and email_col:
                        results.append(check_email_format(current_df, column=email_col))

        with tab_rules:
            st.markdown("Upload a version-controlled JSON or YAML validation rules file:")
            rule_file = st.file_uploader("Upload Rule File (.json, .yaml, .yml):", type=["json", "yaml", "yml"])

            # Provide default sample loader
            sample_rule_path = Path(__file__).parent / "config" / "sample_rules.json"
            load_sample_rule = st.button("Load Built-in Sample Rule File")

            rule_content = None
            if rule_file is not None:
                rule_content = rule_file.read().decode("utf-8")
            elif load_sample_rule and sample_rule_path.exists():
                rule_content = sample_rule_path.read_text(encoding="utf-8")
                st.success("Loaded config/sample_rules.json")

            if rule_content:
                st.code(rule_content[:600] + ("..." if len(rule_content) > 600 else ""), language="json")
                if st.button("🚀 Execute Declarative Rules Suite", type="primary"):
                    with st.spinner("Executing rule suite..."):
                        try:
                            config_dict = load_rules(rule_content)
                            results = execute_rule_suite(current_df, config_dict)
                        except Exception as err:
                            st.error(f"Rule execution error: {err}")

        # Display results if generated
        if results:
            st.session_state["validation_results"] = results
            # Automatically record in local audit history
            dq_score = calculate_data_quality_score(results)
            run_id = history_mgr.record_run(
                dataset_name=current_meta.name,
                total_rows=current_meta.row_count,
                total_columns=current_meta.column_count,
                results=results,
                dq_score=dq_score,
            )

        active_results: Optional[List[ValidationResult]] = st.session_state.get("validation_results")

        if active_results:
            st.markdown("---")
            st.subheader("Validation Scorecard")

            score = calculate_data_quality_score(active_results)
            passed_checks = sum(1 for r in active_results if r.passed)
            failed_checks = sum(1 for r in active_results if not r.passed)

            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Data Quality Score", f"{score}%")
            sc2.metric("Total Rules Tested", f"{len(active_results)}")
            sc3.metric("Passed Checks", f"{passed_checks}", delta="Pass")
            sc4.metric("Failed Checks", f"{failed_checks}", delta="-Fail" if failed_checks > 0 else "0", delta_color="inverse")

            # Score explanation alert
            st.info(
                f"ℹ️ **Score Calculation**: Overall Data Quality Score ({score}%) is computed as the mean record pass rate "
                f"across all {len(active_results)} executed checks."
            )

            # Column error distribution chart
            failed_items = [r for r in active_results if not r.passed]
            if failed_items:
                chart_data = pd.DataFrame([
                    {"Check": r.check_name, "Column": r.column_name or "N/A", "Failed Records": r.failed_records}
                    for r in failed_items
                ])
                fig = px.bar(
                    chart_data,
                    x="Column",
                    y="Failed Records",
                    color="Check",
                    title="Failed Records Distribution by Column & Rule",
                    barmode="group",
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Detailed Check Results")
            for idx, r in enumerate(active_results):
                status_icon = "✅ PASS" if r.passed else "❌ FAIL"
                col_label = f"[{r.column_name}]" if r.column_name else "[Dataset]"
                expander_label = f"{status_icon} - {r.check_name} {col_label} | {r.failed_records:,} failed / {r.total_records:,} total"

                with st.expander(expander_label, expanded=not r.passed):
                    st.write(f"**Explanation:** {r.message}")
                    if r.details:
                        st.json(r.details)
                    if r.failing_sample:
                        st.write("**Failing Records Sample (Up to 10 rows):**")
                        st.dataframe(pd.DataFrame(r.failing_sample), use_container_width=True)

            # Downloadable Reports
            st.markdown("### Download Validation Reports")
            col_d1, col_d2, col_d3 = st.columns(3)

            # CSV Report
            csv_data = generate_validation_csv(active_results, current_meta.name)
            col_d1.download_button(
                label="📥 Download CSV Report",
                data=csv_data,
                file_name=f"validation_report_{current_meta.name}.csv",
                mime="text/csv",
            )

            # Excel Report
            excel_bytes = generate_validation_excel(
                active_results,
                current_meta.name,
                current_meta.row_count,
                current_meta.column_count,
            )
            col_d2.download_button(
                label="📥 Download Multi-Sheet Excel Report",
                data=excel_bytes,
                file_name=f"validation_report_{current_meta.name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # JSON Report
            json_str = generate_validation_json(
                active_results,
                current_meta.name,
                current_meta.row_count,
                current_meta.column_count,
            )
            col_d3.download_button(
                label="📥 Download JSON Summary",
                data=json_str,
                file_name=f"validation_summary_{current_meta.name}.json",
                mime="application/json",
            )


# ============================================================================
# Page 4: Dataset Reconciliation
# ============================================================================
elif navigation == "🔄 Dataset Reconciliation":
    st.subheader("🔄 Dataset Reconciliation")
    st.caption("Compare Source and Target datasets, evaluate key-based record equality, and isolate mismatches.")

    col_src, col_tgt = st.columns(2)

    with col_src:
        st.markdown("#### Source Dataset (e.g. Staging / Upstream)")
        src_mode = st.radio("Source Input:", ["Upload Source", "Load Synthetic Source"], horizontal=True, key="src_mode")
        if src_mode == "Upload Source":
            f_src = st.file_uploader("Upload Source CSV/Excel:", type=["csv", "xlsx"], key="f_src")
            if f_src is not None:
                df_s, _ = load_dataset(io.BytesIO(f_src.read()), filename=f_src.name)
                st.session_state["source_df"] = df_s
        else:
            s_path = Path(__file__).parent / "examples" / "sample_source.csv"
            if s_path.exists() and st.button("Load Example Source"):
                df_s, _ = load_dataset(s_path, filename="sample_source.csv")
                st.session_state["source_df"] = df_s

    with col_tgt:
        st.markdown("#### Target Dataset (e.g. Warehouse / Downstream)")
        tgt_mode = st.radio("Target Input:", ["Upload Target", "Load Synthetic Target"], horizontal=True, key="tgt_mode")
        if tgt_mode == "Upload Target":
            f_tgt = st.file_uploader("Upload Target CSV/Excel:", type=["csv", "xlsx"], key="f_tgt")
            if f_tgt is not None:
                df_t, _ = load_dataset(io.BytesIO(f_tgt.read()), filename=f_tgt.name)
                st.session_state["target_df"] = df_t
        else:
            t_path = Path(__file__).parent / "examples" / "sample_target.csv"
            if t_path.exists() and st.button("Load Example Target"):
                df_t, _ = load_dataset(t_path, filename="sample_target.csv")
                st.session_state["target_df"] = df_t

    df_source = st.session_state.get("source_df")
    df_target = st.session_state.get("target_df")

    if df_source is not None and df_target is not None:
        st.success(f"Loaded Source ({len(df_source):,} rows) and Target ({len(df_target):,} rows).")

        common_candidates = [c for c in df_source.columns if c in df_target.columns]
        if not common_candidates:
            st.error("No common columns found between Source and Target datasets.")
        else:
            st.markdown("#### Comparison Configuration")
            c_cfg1, c_cfg2, c_cfg3 = st.columns(3)

            with c_cfg1:
                selected_keys = st.multiselect(
                    "Select Key Column(s) (Required for 1-to-1 match):",
                    options=common_candidates,
                    default=[common_candidates[0]],
                )

            with c_cfg2:
                tol_float = st.number_input(
                    "Numeric Tolerance (Absolute):",
                    value=1e-4,
                    format="%.5f",
                    help="Allowed absolute difference when comparing float values.",
                )

            with c_cfg3:
                ignore_case = st.checkbox("Case-insensitive string comparison", value=False)
                ignore_ws = st.checkbox("Ignore leading/trailing whitespace", value=True)

            if st.button("⚡ Run Full Reconciliation", type="primary"):
                if not selected_keys:
                    st.error("Please select at least one key column for reconciliation.")
                else:
                    with st.spinner("Reconciling datasets..."):
                        try:
                            rec_result = reconcile_datasets(
                                source_df=df_source,
                                target_df=df_target,
                                key_columns=selected_keys,
                                float_atol=tol_float,
                                ignore_whitespace=ignore_ws,
                                case_sensitive=not ignore_case,
                            )
                            st.session_state["reconcile_result"] = rec_result
                        except Exception as exc:
                            st.error(f"Reconciliation error: {exc}")

            rec_res = st.session_state.get("reconcile_result")
            if rec_res is not None:
                summary = rec_res.summary

                st.markdown("---")
                st.subheader("Reconciliation Summary")

                if summary.has_key_errors:
                    st.error(f"⚠️ **Key Integrity Warning**: {summary.key_error_message}")
                    st.warning("Reconciliation cannot safely compare records because duplicate keys would create false cartesian matches.")
                else:
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("Match Rate", f"{summary.match_rate_percent}%")
                    r2.metric("Matched Records", f"{summary.matched_records:,}")
                    r3.metric("Mismatched Records", f"{summary.mismatched_records:,}")
                    r4.metric("Row Count Delta", f"{summary.row_count_diff:,}")

                    # Tabs for drill-downs
                    t_diffs, t_src_only, t_tgt_only, t_matched = st.tabs([
                        f"Value Mismatches ({summary.mismatched_records})",
                        f"Source Only ({summary.source_only_records})",
                        f"Target Only ({summary.target_only_records})",
                        f"Matched Records ({summary.matched_records})",
                    ])

                    with t_diffs:
                        if not rec_res.mismatched_df.empty:
                            st.dataframe(rec_res.mismatched_df, use_container_width=True)
                        else:
                            st.success("No cell-by-cell value mismatches found across common keys!")

                    with t_src_only:
                        if not rec_res.source_only_df.empty:
                            st.dataframe(rec_res.source_only_df, use_container_width=True)
                        else:
                            st.info("No records exclusive to Source.")

                    with t_tgt_only:
                        if not rec_res.target_only_df.empty:
                            st.dataframe(rec_res.target_only_df, use_container_width=True)
                        else:
                            st.info("No records exclusive to Target.")

                    with t_matched:
                        if not rec_res.matched_df.empty:
                            st.dataframe(rec_res.matched_df.head(100), use_container_width=True)
                        else:
                            st.info("No matching records found.")

                    # Download button for reconciliation Excel workbook
                    st.markdown("### Download Reconciliation Report")
                    rec_excel = generate_reconciliation_excel(rec_res)
                    st.download_button(
                        label="📥 Download Full Reconciliation Workbook (.xlsx)",
                        data=rec_excel,
                        file_name="dataset_reconciliation_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )


# ============================================================================
# Page 5: SQL Database Validation
# ============================================================================
elif navigation == "🗄️ SQL Database Validation":
    st.subheader("🗄️ SQL Database Validation")
    st.caption("Securely inspect tables and perform quality checks on SQLite or PostgreSQL databases.")

    db_type = st.radio("Database Engine:", ["SQLite", "PostgreSQL"], horizontal=True)

    db_config: Optional[DatabaseConfig] = None
    engine = None

    if db_type == "SQLite":
        sqlite_source = st.radio("SQLite Source:", ["Demo In-Memory Sample Table", "Local SQLite File (.db, .sqlite)"], horizontal=True)
        if sqlite_source == "Demo In-Memory Sample Table":
            db_config = DatabaseConfig(dialect="sqlite", sqlite_path=":memory:")
        else:
            db_path_input = st.text_input("Local SQLite File Path:", "opendataguard_test.db")
            if db_path_input:
                db_config = DatabaseConfig(dialect="sqlite", sqlite_path=db_path_input)
    else:
        st.markdown("#### PostgreSQL Connection Parameters")
        c1, c2 = st.columns(2)
        pg_host = c1.text_input("Host:", "localhost")
        pg_port = c2.number_input("Port:", value=5432)
        pg_db = c1.text_input("Database Name:", "postgres")
        pg_user = c2.text_input("Username:", "postgres")
        pg_pwd = st.text_input("Password:", type="password", help="Never saved or logged.")

        db_config = DatabaseConfig(
            dialect="postgresql",
            host=pg_host,
            port=int(pg_port),
            database=pg_db,
            username=pg_user,
            password=pg_pwd,
        )

    if db_config is not None:
        if st.button("🔗 Connect & Inspect Database"):
            try:
                with st.spinner("Connecting to database..."):
                    engine = create_safe_engine(db_config)
                    # If demo in-memory, populate a mock table for user exploration
                    if db_config.dialect == "sqlite" and db_config.sqlite_path == ":memory:":
                        demo_df = pd.DataFrame({
                            "user_id": [1, 2, 3, 4, 5],
                            "username": ["alice", "bob", "carol", "dave", "eve"],
                            "email": ["alice@test.com", "bob@test.com", None, "dave@test.com", "eve@test.com"],
                            "score": [95.5, 88.0, 72.3, 105.0, 60.0],
                        })
                        demo_df.to_sql("users_audit", engine, index=False)

                    tables = list_database_tables(engine)
                    st.session_state["db_engine"] = engine
                    st.session_state["db_tables"] = tables
                    st.success(f"Connected successfully! Found {len(tables)} tables: {tables}")
            except Exception as err:
                st.error(f"Connection failed: {err}")

    # Inspect tables if engine in session state
    saved_engine = st.session_state.get("db_engine")
    saved_tables = st.session_state.get("db_tables", [])

    if saved_engine is not None and saved_tables:
        st.markdown("---")
        st.markdown("### Table Inspection & Validation")
        selected_table = st.selectbox("Select Table to Audit:", options=saved_tables)

        if selected_table:
            row_count = get_table_row_count(saved_engine, selected_table)
            schema = inspect_table_schema(saved_engine, selected_table)

            t1, t2 = st.columns(2)
            t1.metric("Table Name", selected_table)
            t2.metric("Row Count", f"{row_count:,}")

            st.write("**Table Schema:**")
            st.dataframe(pd.DataFrame(schema), use_container_width=True)

            if st.button(f"📥 Load '{selected_table}' into Validator (Sample up to 10k rows)"):
                with st.spinner("Fetching table rows..."):
                    table_df = fetch_table_sample(saved_engine, selected_table, limit=10_000)
                    st.session_state["current_df"] = table_df
                    st.session_state["current_metadata"] = None
                    st.success(f"Loaded {len(table_df):,} rows from '{selected_table}'. Go to **🛡️ Data Quality Validation** to execute checks!")


# ============================================================================
# Page 6: Validation History
# ============================================================================
elif navigation == "📜 Validation History":
    st.subheader("📜 Validation Execution History")
    st.caption("Persistent local SQLite audit ledger of historical validation runs.")

    history_df = history_mgr.get_history(limit=100)

    if history_df.empty:
        st.info("No validation history recorded yet. Execute checks in **🛡️ Data Quality Validation** to populate history.")
    else:
        st.dataframe(history_df, use_container_width=True)

        # Inspection of a selected run
        run_ids = history_df["run_id"].tolist()
        selected_run = st.selectbox("Select Run ID to Inspect Details:", options=run_ids)

        if selected_run:
            details = history_mgr.get_run_details(selected_run)
            if details:
                st.markdown(f"#### Run Details: `{selected_run}`")
                r_c1, r_c2, r_c3, r_c4 = st.columns(4)
                r_c1.metric("Dataset", details["dataset_name"])
                r_c2.metric("Timestamp (UTC)", details["timestamp_utc"][:19])
                r_c3.metric("DQ Score", f"{details['dq_score']}%")
                r_c4.metric("Status", details["status"])

                st.write("**Check Breakdown:**")
                st.dataframe(pd.DataFrame(details["checks"]), use_container_width=True)

        st.markdown("---")
        with st.expander("⚠️ Clear History Audit Database"):
            st.warning("This action permanently removes all logged validation runs from your local history database.")
            if st.button("Permanently Clear All History", type="secondary"):
                history_mgr.clear_history()
                st.success("History database cleared.")
                st.rerun()


# ============================================================================
# Page 7: Settings & Documentation
# ============================================================================
elif navigation == "⚙️ Settings & Documentation":
    st.subheader("⚙️ Settings & Documentation")

    st.markdown("### Rule Specification Format Reference")
    st.markdown(
        """
        OpenDataGuard supports declarative validation rules in JSON or YAML.
        Below is an example configuration demonstrating all supported assertion types:
        """
    )

    example_config = {
        "version": "1.0",
        "description": "Customer and Transaction Validation Rules",
        "rules": [
            {"rule": "required", "column": "customer_id", "threshold_percent": 0.0},
            {"rule": "unique", "columns": ["customer_id"]},
            {"rule": "duplicate_rows"},
            {"rule": "data_type", "column": "age", "type": "int"},
            {"rule": "range", "column": "age", "min": 18, "max": 120},
            {"rule": "allowed_values", "column": "status", "values": ["ACTIVE", "INACTIVE", "PENDING"]},
            {"rule": "min_length", "column": "username", "value": 3},
            {"rule": "regex", "column": "email", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
            {"rule": "email", "column": "email"},
            {"rule": "date_format", "column": "signup_date", "format": "%Y-%m-%d"},
            {"rule": "schema", "expected_columns": ["customer_id", "username", "email", "age", "status", "signup_date"]},
        ],
    }

    t_json, t_yaml = st.tabs(["JSON Schema Format", "YAML Schema Format"])
    with t_json:
        st.code(json.dumps(example_config, indent=2), language="json")
    with t_yaml:
        st.code(yaml.dump(example_config, sort_keys=False), language="yaml")

    st.markdown("### Privacy, Security & Compliance")
    st.markdown(
        """
        - **Local Processing**: All validations, file reading, and reconciliations are computed completely in-memory on your machine.
        - **No Telemetry**: OpenDataGuard does not transmit your data or analytics to external servers.
        - **Safe SQL**: Connection credentials are masked and never logged. Database interactions are restricted to read-only queries.
        - **Source Preservation**: Uploaded datasets are never modified or overwritten in-place.
        """
    )
