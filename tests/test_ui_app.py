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


