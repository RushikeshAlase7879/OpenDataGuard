"""End-to-end integration verification script testing all 6 core workflows."""

import os
from pathlib import Path
import pytest
import pandas as pd

from opendataguard.validators import load_dataset, calculate_data_quality_score
from opendataguard.reconciliation import reconcile_datasets
from opendataguard.database import (
    DatabaseConfig,
    create_safe_engine,
    list_database_tables,
    inspect_table_schema,
    get_table_row_count,
    fetch_table_sample,
)
from opendataguard.reports import (
    generate_validation_csv,
    generate_validation_excel,
    generate_validation_json,
    generate_reconciliation_excel,
)
from opendataguard.history import HistoryManager
from opendataguard.rules import load_rules, execute_rule_suite


def test_end_to_end_core_workflows(tmp_path):
    base = Path(__file__).parent.parent

    # 1. Dataset Ingestion / Upload
    src_csv = base / "examples" / "sample_source.csv"
    assert src_csv.exists()
    df_src, meta = load_dataset(src_csv)
    assert meta.row_count == 12
    assert meta.column_count == 7
    assert len(df_src) == 12

    # 2. Quality Rules Validation
    rules_path = base / "config" / "sample_rules.json"
    assert rules_path.exists()
    rules = load_rules(rules_path)
    results = execute_rule_suite(df_src, rules)
    score = calculate_data_quality_score(results)
    assert len(results) == 8
    assert 0.0 < score < 100.0  # Intentional defects exist in sample_source.csv

    # 3. Dataset Reconciliation
    src_deduped_csv = base / "examples" / "sample_source_deduped.csv"
    tgt_csv = base / "examples" / "sample_target.csv"
    df_dedup, _ = load_dataset(src_deduped_csv)
    df_tgt, _ = load_dataset(tgt_csv)
    rec = reconcile_datasets(df_dedup, df_tgt, key_columns="customer_id", float_atol=1e-4)
    assert rec.summary.matched_records > 0
    assert rec.summary.mismatched_records > 0
    assert rec.summary.source_only_records > 0
    assert rec.summary.target_only_records > 0

    # 4. Database Operations
    engine = create_safe_engine(DatabaseConfig(dialect="sqlite", sqlite_path=":memory:"))
    df_src.to_sql("customers", engine, index=False)
    tables = list_database_tables(engine)
    assert "customers" in tables
    schema = inspect_table_schema(engine, "customers")
    assert len(schema) == 7
    row_count = get_table_row_count(engine, "customers")
    assert row_count == 12
    fetched_df = fetch_table_sample(engine, "customers", limit=5)
    assert len(fetched_df) == 5

    # 5. Report Generation
    csv_rep = generate_validation_csv(results, "sample_source.csv")
    assert "timestamp_utc" in csv_rep
    json_rep = generate_validation_json(results, "sample_source.csv", meta.row_count, meta.column_count)
    assert "data_quality_score" in json_rep
    excel_rep = generate_validation_excel(results, "sample_source.csv", meta.row_count, meta.column_count)
    assert len(excel_rep) > 1000
    rec_excel = generate_reconciliation_excel(rec)
    assert len(rec_excel) > 1000

    # 6. Validation History
    test_db = tmp_path / "test_history.db"
    hist_mgr = HistoryManager(db_path=test_db)
    run_id = hist_mgr.record_run("sample_source.csv", meta.row_count, meta.column_count, results, score)
    assert run_id is not None
    history_df = hist_mgr.get_history(limit=5)
    assert len(history_df) == 1
    run_details = hist_mgr.get_run_details(run_id)
    assert run_details["dataset_name"] == "sample_source.csv"
    assert run_details["total_checks"] == 8
