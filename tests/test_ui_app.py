"""Automated UI smoke and page rendering tests using Streamlit AppTest."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def app():
    return AppTest.from_file(APP_PATH, default_timeout=30)


def test_streamlit_app_loads_overview(app):
    app.run()
    assert len(app.exception) == 0
    assert len(app.error) == 0


@pytest.mark.parametrize(
    "page_name",
    [
        "📊 Overview",
        "📁 Dataset Explorer",
        "🛡️ Data Quality Validation",
        "🔄 Dataset Reconciliation",
        "🗄️ SQL Database Validation",
        "📜 Validation History",
        "⚙️ Settings & Documentation",
    ],
)
def test_streamlit_pages_render_without_error(page_name):
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(page_name).run()
    assert len(at.exception) == 0, f"Exception occurred while rendering page: {page_name}"
    assert len(at.error) == 0, f"Error occurred while rendering page: {page_name}"


def test_overview_metrics_empty_history(monkeypatch, tmp_path):
    from opendataguard.history import HistoryManager
    # Point history to an empty SQLite database
    empty_db = tmp_path / "empty_audit.db"
    mgr = HistoryManager(db_path=str(empty_db))
    monkeypatch.setattr("app.history_mgr", mgr)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert len(at.exception) == 0
    # Verify metric displays N/A when no audit history exists
    metric_values = [m.value for m in at.metric]
    assert "N/A" in metric_values


def test_history_page_with_reconciliation_runs(tmp_path: Path, monkeypatch):
    from opendataguard.history import HistoryManager
    from opendataguard.reconciliation import reconcile_datasets
    import pandas as pd

    test_db = tmp_path / "test_hist.db"
    mgr = HistoryManager(db_path=str(test_db))
    monkeypatch.setattr("app.history_mgr", mgr)

    # Perform a reconciliation and record run
    df_src = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
    df_tgt = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
    rec_res = reconcile_datasets(
        source_df=df_src,
        target_df=df_tgt,
        key_columns=["id"],
        source_name="src.csv",
        target_name="tgt.csv",
    )
    mgr.record_reconciliation_run(rec_res)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("📜 Validation History").run()
    assert len(at.exception) == 0
    assert len(at.error) == 0


def test_ui_reconciliation_details_with_key_errors(tmp_path: Path, monkeypatch):
    from opendataguard.history import HistoryManager
    from opendataguard.reconciliation import reconcile_datasets
    import pandas as pd

    test_db = tmp_path / "test_hist_err.db"
    mgr = HistoryManager(db_path=str(test_db))
    monkeypatch.setattr("app.history_mgr", mgr)

    # Reconciliation with duplicate keys triggers key error
    df_src = pd.DataFrame({"id": [1, 1], "val": [10, 20]})
    df_tgt = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
    rec_res = reconcile_datasets(
        source_df=df_src,
        target_df=df_tgt,
        key_columns=["id"],
        source_name="src_dup.csv",
        target_name="tgt.csv",
    )
    mgr.record_reconciliation_run(rec_res)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("📜 Validation History").run()
    assert len(at.exception) == 0
    assert len(at.error) == 0


