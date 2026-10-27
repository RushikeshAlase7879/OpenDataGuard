"""Unit tests for report generation."""

import json
import pytest
import pandas as pd

from opendataguard.validators import check_missing_values, check_duplicate_rows
from opendataguard.reconciliation import reconcile_datasets
from opendataguard.reports import (
    generate_validation_csv,
    generate_validation_json,
    generate_validation_excel,
    generate_reconciliation_excel,
)


@pytest.fixture
def mock_validation_results():
    df = pd.DataFrame({"a": [1, None, 3], "b": [10, 20, 30]})
    r1 = check_missing_values(df, column="a")
    r2 = check_duplicate_rows(df)
    return [r1, r2]


def test_generate_validation_csv(mock_validation_results):
    csv_str = generate_validation_csv(mock_validation_results, dataset_name="test_data")
    assert "timestamp_utc" in csv_str
    assert "test_data" in csv_str
    assert "missing_values" in csv_str
    assert "duplicate_rows" in csv_str


def test_generate_validation_json(mock_validation_results):
    json_str = generate_validation_json(
        mock_validation_results,
        dataset_name="test_data",
        row_count=3,
        column_count=2,
    )
    parsed = json.loads(json_str)
    assert parsed["metadata"]["dataset_name"] == "test_data"
    assert parsed["summary"]["total_checks"] == 2
    assert "results" in parsed


def test_generate_validation_excel(mock_validation_results):
    excel_bytes = generate_validation_excel(
        mock_validation_results,
        dataset_name="test_data",
        row_count=3,
        column_count=2,
    )
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 1000  # Valid non-empty workbook


def test_generate_reconciliation_excel():
    s_df = pd.DataFrame({"id": [1, 2], "val": ["x", "y"]})
    t_df = pd.DataFrame({"id": [1, 3], "val": ["x", "z"]})
    rec_res = reconcile_datasets(s_df, t_df, key_columns="id")

    excel_bytes = generate_reconciliation_excel(rec_res)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 1000
