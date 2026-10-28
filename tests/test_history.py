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

