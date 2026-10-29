"""Unit tests for validation history manager."""

import pytest
import pandas as pd
from opendataguard.history import HistoryManager
from opendataguard.validators import check_missing_values, check_duplicate_rows


@pytest.fixture
def temp_history_mgr(tmp_path):
    db_file = tmp_path / "test_history.db"
    return HistoryManager(db_path=db_file)


def test_history_manager_record_and_get(temp_history_mgr):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    results = [check_missing_values(df), check_duplicate_rows(df)]

    run_id = temp_history_mgr.record_run(
        dataset_name="test_dataset",
        total_rows=3,
        total_columns=2,
        results=results,
    )
    assert run_id is not None

    history_df = temp_history_mgr.get_history()
    assert len(history_df) == 1
    assert history_df.iloc[0]["dataset_name"] == "test_dataset"
    assert history_df.iloc[0]["total_checks"] == 2
    assert history_df.iloc[0]["status"] == "PASSED"


def test_history_manager_run_details(temp_history_mgr):
    df = pd.DataFrame({"col": [1, None]})
    results = [check_missing_values(df, column="col")]

    run_id = temp_history_mgr.record_run(
        dataset_name="failing_dataset",
        total_rows=2,
        total_columns=1,
        results=results,
    )

    details = temp_history_mgr.get_run_details(run_id)
    assert details is not None
    assert details["run_id"] == run_id
    assert details["failed_checks"] == 1
    assert len(details["checks"]) == 1
    assert details["checks"][0]["check_name"] == "missing_values"


def test_history_manager_clear(temp_history_mgr):
    df = pd.DataFrame({"a": [1]})
    temp_history_mgr.record_run("sample", 1, 1, [check_missing_values(df)])
    assert len(temp_history_mgr.get_history()) == 1

    temp_history_mgr.clear_history()
    assert len(temp_history_mgr.get_history()) == 0


def test_history_persistence_across_manager_restarts(tmp_path):
    db_file = tmp_path / "persistent_history.db"

    # First session: instantiate manager and record runs
    mgr1 = HistoryManager(db_path=db_file)
    df_clean = pd.DataFrame({"x": [10, 20]})
    run1 = mgr1.record_run("dataset_clean", 2, 1, [check_missing_values(df_clean)])
    assert run1 is not None

    # Second session: new manager instance connecting to the same SQLite database file
    mgr2 = HistoryManager(db_path=db_file)
    history_df = mgr2.get_history()
    assert len(history_df) == 1
    assert history_df.iloc[0]["run_id"] == run1
    assert history_df.iloc[0]["dataset_name"] == "dataset_clean"


def test_history_records_both_passed_and_failed_runs(temp_history_mgr):
    df_pass = pd.DataFrame({"x": [1, 2]})
    df_fail = pd.DataFrame({"x": [1, None]})

    id_pass = temp_history_mgr.record_run("pass_run", 2, 1, [check_missing_values(df_pass)])
    id_fail = temp_history_mgr.record_run("fail_run", 2, 1, [check_missing_values(df_fail)])

    det_pass = temp_history_mgr.get_run_details(id_pass)
    det_fail = temp_history_mgr.get_run_details(id_fail)

    assert det_pass["status"] == "PASSED"
    assert det_fail["status"] == "FAILED"
    assert det_pass["failed_checks"] == 0
    assert det_fail["failed_checks"] == 1


def test_reconciliation_history_record_and_get(temp_history_mgr):
    from opendataguard.reconciliation import reconcile_datasets

    src = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})
    tgt = pd.DataFrame({"id": [1, 2], "val": ["a", "c"]})
    res = reconcile_datasets(src, tgt, key_columns=["id"], source_name="src_data", target_name="tgt_data")

    run_id = temp_history_mgr.record_reconciliation_run(res)
    assert run_id is not None

    recon_df = temp_history_mgr.get_reconciliation_history()
    assert len(recon_df) == 1
    assert recon_df.iloc[0]["source_name"] == "src_data"
    assert recon_df.iloc[0]["target_name"] == "tgt_data"
    assert recon_df.iloc[0]["mismatched_records"] == 1
    assert recon_df.iloc[0]["matched_records"] == 1
    assert recon_df.iloc[0]["status"] == "DISCREPANCIES"


def test_reconciliation_history_run_details(temp_history_mgr):
    from opendataguard.reconciliation import reconcile_datasets

    src = pd.DataFrame({"id": [1, 2], "val": ["a", "b"], "status": ["OK", "WARN"]})
    tgt = pd.DataFrame({"id": [1, 2], "val": ["a", "z"], "status": ["OK", "ERR"]})
    res = reconcile_datasets(src, tgt, key_columns=["id"])

    run_id = temp_history_mgr.record_reconciliation_run(res)
    details = temp_history_mgr.get_reconciliation_run_details(run_id)

    assert details is not None
    assert details["run_id"] == run_id
    assert details["matched_records"] == 1
    assert details["mismatched_records"] == 1
    assert "val" in details["column_mismatches"]
    assert "status" in details["column_mismatches"]


def test_reconciliation_history_persistence_across_restarts(tmp_path):
    from opendataguard.reconciliation import reconcile_datasets

    db_file = tmp_path / "recon_persistence.db"
    mgr1 = HistoryManager(db_path=db_file)

    src = pd.DataFrame({"id": [10], "amt": [100.0]})
    tgt = pd.DataFrame({"id": [10], "amt": [100.0]})
    res = reconcile_datasets(src, tgt, key_columns=["id"], source_name="s1", target_name="t1")
    run_id = mgr1.record_reconciliation_run(res)

    mgr2 = HistoryManager(db_path=db_file)
    hist_df = mgr2.get_reconciliation_history()
    assert len(hist_df) == 1
    assert hist_df.iloc[0]["run_id"] == run_id
    assert hist_df.iloc[0]["status"] == "MATCHED"


def test_reconciliation_history_clear(temp_history_mgr):
    from opendataguard.reconciliation import reconcile_datasets

    src = pd.DataFrame({"id": [1], "v": [10]})
    tgt = pd.DataFrame({"id": [1], "v": [10]})
    res = reconcile_datasets(src, tgt, key_columns=["id"])
    temp_history_mgr.record_reconciliation_run(res)

    assert len(temp_history_mgr.get_reconciliation_history()) == 1
    temp_history_mgr.clear_reconciliation_history()
    assert len(temp_history_mgr.get_reconciliation_history()) == 0


def test_reconciliation_history_nonexistent_run_returns_none(temp_history_mgr):
    assert temp_history_mgr.get_reconciliation_run_details("non-existent-uuid") is None

