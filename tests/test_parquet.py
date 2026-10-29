"""Tests for native Parquet (.parquet) dataset ingestion."""

import io
from pathlib import Path
import unittest.mock as mock

import pandas as pd
import pytest

from opendataguard.cli import main as cli_main
from opendataguard.validators import load_dataset, validate_file_safety


@pytest.fixture
def sample_parquet_file(tmp_path: Path) -> Path:
    """Create a temporary Parquet file with sample records."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "Bob", "Charlie", "Diana"],
        "score": [95.5, 88.0, 72.5, 99.0],
        "active": [True, True, False, True],
    })
    path = tmp_path / "sample.parquet"
    df.to_parquet(path, index=False)
    return path


def test_validate_file_safety_allows_parquet(sample_parquet_file: Path):
    """validate_file_safety should accept .parquet extension without error."""
    ext, size = validate_file_safety(sample_parquet_file)
    assert ext == ".parquet"
    assert size > 0


def test_load_dataset_parquet_path(sample_parquet_file: Path):
    """load_dataset should parse a .parquet file path into DataFrame and metadata."""
    df, meta = load_dataset(sample_parquet_file)
    assert len(df) == 4
    assert list(df.columns) == ["id", "name", "score", "active"]
    assert meta.row_count == 4
    assert meta.column_count == 4
    assert "score" in meta.dtypes


def test_load_dataset_parquet_bytes_io(sample_parquet_file: Path):
    """load_dataset should parse Parquet from an in-memory BytesIO buffer."""
    data_bytes = sample_parquet_file.read_bytes()
    buf = io.BytesIO(data_bytes)
    df, meta = load_dataset(buf, filename="buffer.parquet")
    assert len(df) == 4
    assert meta.name == "buffer.parquet"


def test_load_dataset_parquet_raw_bytes(sample_parquet_file: Path):
    """load_dataset should parse Parquet directly from raw bytes."""
    data_bytes = sample_parquet_file.read_bytes()
    df, meta = load_dataset(data_bytes, filename="raw.parquet")
    assert len(df) == 4
    assert meta.name == "raw.parquet"


def test_load_dataset_empty_parquet(tmp_path: Path):
    """Empty Parquet file with zero rows should raise ValueError."""
    empty_df = pd.DataFrame(columns=["col1", "col2"])
    path = tmp_path / "empty.parquet"
    empty_df.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="contains no rows or records"):
        load_dataset(path)


def test_load_dataset_malformed_parquet(tmp_path: Path):
    """Corrupted Parquet file should raise actionable ValueError."""
    corrupt_path = tmp_path / "corrupt.parquet"
    corrupt_path.write_bytes(b"PAR1_NOT_REAL_PARQUET_CONTENT_12345")

    with pytest.raises(ValueError, match="Unable to parse Parquet file"):
        load_dataset(corrupt_path)


def test_missing_parquet_engine_raises_actionable_error(sample_parquet_file: Path):
    """When both pyarrow and fastparquet are missing, ImportError must be raised."""
    orig_import = __import__

    def mock_import(name, *args, **kwargs):
        if name in ("pyarrow", "fastparquet"):
            raise ImportError(f"No module named '{name}'")
        return orig_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ImportError, match="Reading Parquet files requires 'pyarrow' or 'fastparquet'"):
            load_dataset(sample_parquet_file)


def test_cli_validate_with_parquet(sample_parquet_file: Path, tmp_path: Path):
    """CLI validate command should accept .parquet files."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        """
rules:
  - rule: required
    column: id
  - rule: min_value
    column: score
    value: 50.0
""",
        encoding="utf-8",
    )
    exit_code = cli_main(["validate", "-d", str(sample_parquet_file), "-r", str(rules_file)])
    assert exit_code == 0


def test_cli_reconcile_with_parquet(sample_parquet_file: Path, tmp_path: Path):
    """CLI reconcile command should accept .parquet files."""
    target_path = tmp_path / "target.parquet"
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "Bob", "Charlie", "Diana"],
        "score": [95.5, 88.0, 72.5, 99.0],
        "active": [True, True, False, True],
    })
    df.to_parquet(target_path, index=False)

    exit_code = cli_main([
        "reconcile",
        "-s", str(sample_parquet_file),
        "-t", str(target_path),
        "-k", "id",
    ])
    assert exit_code == 0
