"""Unit tests for OpenDataGuard reconciliation engine."""

import pytest
import pandas as pd
import numpy as np

from opendataguard.reconciliation import reconcile_datasets


@pytest.fixture
def source_data():
    return pd.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "Bob", "Charlie", "SourceOnly"],
        "balance": [100.0, 200.5, 300.00001, 400.0],
    })


@pytest.fixture
def target_data():
    return pd.DataFrame({
        "id": [1, 2, 3, 5],
        "name": ["Alice", "Bob Mismatch", "Charlie", "TargetOnly"],
        "balance": [100.0, 999.0, 300.00002, 500.0],
    })


def test_reconciliation_exact_match():
    df = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})
    res = reconcile_datasets(df, df, key_columns="id")
    assert res.summary.match_rate_percent == 100.0
    assert res.summary.matched_records == 2
    assert res.summary.mismatched_records == 0
    assert len(res.source_only_df) == 0
    assert len(res.target_only_df) == 0


def test_reconciliation_source_and_target_only(source_data, target_data):
    res = reconcile_datasets(source_data, target_data, key_columns="id")
    # Record 4 is source only
    assert len(res.source_only_df) == 1
    assert res.source_only_df.iloc[0]["id"] == 4
    # Record 5 is target only
    assert len(res.target_only_df) == 1
    assert res.target_only_df.iloc[0]["id"] == 5


def test_reconciliation_value_mismatches(source_data, target_data):
    res = reconcile_datasets(source_data, target_data, key_columns="id")
    # Record 2 has mismatch in 'name' and 'balance'
    assert not res.mismatched_df.empty
    mismatches = res.mismatched_df[res.mismatched_df["id"] == 2]
    cols = mismatches["mismatched_column"].tolist()
    assert "name" in cols
    assert "balance" in cols


def test_reconciliation_float_tolerance(source_data, target_data):
    # Record 3 has 300.00001 vs 300.00002. Absolute diff is 1e-5.
    # With default atol=1e-4, this should be considered MATCHED.
    res = reconcile_datasets(source_data, target_data, key_columns="id", float_atol=1e-4)
    mismatches = res.mismatched_df[res.mismatched_df["id"] == 3]
    assert len(mismatches) == 0


def test_reconciliation_duplicate_keys_detected():
    df_src = pd.DataFrame({"id": [1, 1, 2], "val": ["a", "b", "c"]})
    df_tgt = pd.DataFrame({"id": [1, 2], "val": ["a", "c"]})

    res = reconcile_datasets(df_src, df_tgt, key_columns="id")
    assert res.summary.has_key_errors
    assert res.summary.source_duplicate_keys > 0
    assert "duplicate key" in res.summary.key_error_message


def test_reconciliation_null_keys_handled():
    df_src = pd.DataFrame({"id": [1, None], "val": ["a", "b"]})
    df_tgt = pd.DataFrame({"id": [1, 2], "val": ["a", "c"]})

    res = reconcile_datasets(df_src, df_tgt, key_columns="id")
    assert res.summary.has_key_errors
    assert res.summary.source_null_keys == 1


def test_reconciliation_missing_key_column_raises():
    df_src = pd.DataFrame({"id_src": [1, 2]})
    df_tgt = pd.DataFrame({"id_tgt": [1, 2]})

    with pytest.raises(ValueError, match="Key column.*missing"):
        reconcile_datasets(df_src, df_tgt, key_columns="id")
