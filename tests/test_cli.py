"""Tests for the native OpenDataGuard Command-Line Interface (CLI)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from opendataguard.cli import _find_app_path, build_parser, main


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a sample valid CSV dataset."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [25, 30, 35, 40, 45],
        "email": ["alice@test.com", "bob@test.com", "charlie@test.com", "david@test.com", "eve@test.com"],
        "status": ["active", "active", "pending", "inactive", "active"],
    })
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def failing_csv(tmp_path: Path) -> Path:
    """Create a sample CSV dataset with known data quality defects."""
    df = pd.DataFrame({
        "id": [1, 2, 2, 4, None],  # duplicate id 2, null id
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [25, -5, 35, 200, 45],  # out of range (-5, 200)
        "email": ["alice@test.com", "invalid-email", "charlie@test.com", "david", "eve@test.com"],
        "status": ["active", "unknown", "pending", "banned", "active"],
    })
    path = tmp_path / "failing.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def valid_rules_yaml(tmp_path: Path) -> Path:
    """Create a valid rules YAML file."""
    content = """
version: "1.0"
dataset: "users"
rules:
  - rule: required
    column: id
  - rule: unique
    column: id
  - rule: range
    column: age
    min: 18
    max: 100
  - rule: allowed_values
    column: status
    values: ["active", "pending", "inactive"]
  - rule: email
    column: email
"""
    path = tmp_path / "rules.yaml"
    path.write_text(content.strip(), encoding="utf-8")
    return path


@pytest.fixture
def target_csv_matching(tmp_path: Path, sample_csv: Path) -> Path:
    """Create a target CSV matching sample_csv."""
    df = pd.read_csv(sample_csv)
    path = tmp_path / "target_match.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def target_csv_mismatched(tmp_path: Path) -> Path:
    """Create a target CSV with discrepancies."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 6],  # 5 is missing (source only), 6 is extra (target only)
        "name": ["Alice", "Bob", "Charlie Mismatched", "David", "Frank"],  # Charlie differs
        "age": [25, 30, 99, 40, 50],  # age differs for id=3
        "email": ["alice@test.com", "bob@test.com", "charlie@test.com", "david@test.com", "frank@test.com"],
        "status": ["active", "active", "pending", "inactive", "active"],
    })
    path = tmp_path / "target_mismatch.csv"
    df.to_csv(path, index=False)
    return path


# ==============================================================================
# 1. Top-Level CLI Tests (Help, Version, Empty)
# ==============================================================================

def test_cli_empty_args_shows_help(capsys):
    """Running CLI with no arguments should show help and return exit code 0."""
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OpenDataGuard" in captured.out
    assert "validate" in captured.out
    assert "reconcile" in captured.out
    assert "ui" in captured.out


def test_cli_help_flag(capsys):
    """Running CLI with --help should return exit code 0."""
    exit_code = main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OpenDataGuard" in captured.out


def test_cli_version_flag(capsys):
    """Running CLI with --version should return exit code 0 and show version."""
    exit_code = main(["--version"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OpenDataGuard 1.0.0" in captured.out


def test_cli_version_subcommand(capsys):
    """Running CLI 'version' subcommand should return exit code 0 with platform info."""
    exit_code = main(["version"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OpenDataGuard 1.0.0" in captured.out
    assert "Python" in captured.out


# ==============================================================================
# 2. 'validate' Subcommand Tests
# ==============================================================================

def test_validate_all_checks_passing(sample_csv: Path, valid_rules_yaml: Path, capsys):
    """Valid dataset matching all rules should exit with code 0."""
    exit_code = main(["validate", "--data", str(sample_csv), "--rules", str(valid_rules_yaml)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PASSED" in captured.out
    assert "Quality Score:  100.00%" in captured.out
    assert "Failed Checks:  0" in captured.out


def test_validate_failing_checks(failing_csv: Path, valid_rules_yaml: Path, capsys):
    """Dataset with quality defects should exit with code 1."""
    exit_code = main(["validate", "--data", str(failing_csv), "--rules", str(valid_rules_yaml)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "FAILED" in captured.out
    assert "Failed Checks:" in captured.out


def test_validate_min_score_threshold(sample_csv: Path, valid_rules_yaml: Path):
    """Min-score threshold should succeed if score >= min_score."""
    # 100% score with 90% required -> 0
    assert main(["validate", "-d", str(sample_csv), "-r", str(valid_rules_yaml), "--min-score", "90"]) == 0
    # 100% score with 100% required -> 0
    assert main(["validate", "-d", str(sample_csv), "-r", str(valid_rules_yaml), "--min-score", "100"]) == 0


def test_validate_min_score_threshold_failure(failing_csv: Path, valid_rules_yaml: Path):
    """Min-score threshold should fail with code 1 if score < min_score."""
    assert main(["validate", "-d", str(failing_csv), "-r", str(valid_rules_yaml), "--min-score", "99.9"]) == 1


def test_validate_strict_mode(sample_csv: Path, failing_csv: Path, valid_rules_yaml: Path):
    """Strict mode should succeed when all checks pass and fail when checks fail."""
    assert main(["validate", "-d", str(sample_csv), "-r", str(valid_rules_yaml), "--strict"]) == 0
    assert main(["validate", "-d", str(failing_csv), "-r", str(valid_rules_yaml), "--strict"]) == 1


def test_validate_output_json(sample_csv: Path, valid_rules_yaml: Path, tmp_path: Path):
    """Output JSON report should be generated on disk."""
    out_file = tmp_path / "report.json"
    exit_code = main([
        "validate",
        "-d", str(sample_csv),
        "-r", str(valid_rules_yaml),
        "-o", str(out_file),
    ])
    assert exit_code == 0
    assert out_file.is_file()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["summary"]["overall_status"] == "PASSED"
    assert data["summary"]["data_quality_score"] == 100.0


def test_validate_output_csv(sample_csv: Path, valid_rules_yaml: Path, tmp_path: Path):
    """Output CSV report should be generated on disk."""
    out_file = tmp_path / "report.csv"
    exit_code = main([
        "validate",
        "-d", str(sample_csv),
        "-r", str(valid_rules_yaml),
        "-o", str(out_file),
    ])
    assert exit_code == 0
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "check_name" in content
    assert "passed" in content


def test_validate_output_excel(sample_csv: Path, valid_rules_yaml: Path, tmp_path: Path):
    """Output Excel report should be generated on disk."""
    out_file = tmp_path / "report.xlsx"
    exit_code = main([
        "validate",
        "-d", str(sample_csv),
        "-r", str(valid_rules_yaml),
        "-o", str(out_file),
    ])
    assert exit_code == 0
    assert out_file.is_file()
    assert out_file.stat().st_size > 0


def test_validate_missing_data_file(valid_rules_yaml: Path, capsys):
    """Missing data file should print error and exit with code 2."""
    exit_code = main(["validate", "-d", "non_existent_file.csv", "-r", str(valid_rules_yaml)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Data file not found" in captured.err


def test_validate_missing_rules_file(sample_csv: Path, capsys):
    """Missing rules file should print error and exit with code 2."""
    exit_code = main(["validate", "-d", str(sample_csv), "-r", "non_existent_rules.yaml"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Rules file not found" in captured.err


def test_validate_malformed_rules(sample_csv: Path, tmp_path: Path, capsys):
    """Invalid rule format should exit with code 2."""
    bad_rules = tmp_path / "bad_rules.yaml"
    bad_rules.write_text("not_a_valid_dict_structure: [1, 2, 3]", encoding="utf-8")
    exit_code = main(["validate", "-d", str(sample_csv), "-r", str(bad_rules)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error loading rule suite" in captured.err


# ==============================================================================
# 3. 'reconcile' Subcommand Tests
# ==============================================================================

def test_reconcile_exact_match(sample_csv: Path, target_csv_matching: Path, capsys):
    """Reconciling identical datasets should return exit code 0."""
    exit_code = main([
        "reconcile",
        "-s", str(sample_csv),
        "-t", str(target_csv_matching),
        "-k", "id",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MATCHED (100%)" in captured.out
    assert "Match Rate:          100.00%" in captured.out
    assert "Mismatched Records:  0" in captured.out


def test_reconcile_discrepancies_detected(sample_csv: Path, target_csv_mismatched: Path, capsys):
    """Reconciling datasets with mismatches should return exit code 1."""
    exit_code = main([
        "reconcile",
        "-s", str(sample_csv),
        "-t", str(target_csv_mismatched),
        "-k", "id",
    ])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "DISCREPANCIES DETECTED" in captured.out
    assert "Mismatched Records:  1" in captured.out
    assert "Source-Only Records: 1" in captured.out
    assert "Target-Only Records: 1" in captured.out


def test_reconcile_composite_keys(tmp_path: Path):
    """Reconciling on composite keys should parse space- and comma-separated keys."""
    df1 = pd.DataFrame({
        "country": ["US", "US", "CA"],
        "store_id": [101, 102, 201],
        "sales": [1000.0, 2000.0, 3000.0],
    })
    df2 = pd.DataFrame({
        "country": ["US", "US", "CA"],
        "store_id": [101, 102, 201],
        "sales": [1000.0, 2000.0, 3000.0],
    })
    p1 = tmp_path / "df1.csv"
    p2 = tmp_path / "df2.csv"
    df1.to_csv(p1, index=False)
    df2.to_csv(p2, index=False)

    # Test space-separated keys
    code1 = main(["reconcile", "-s", str(p1), "-t", str(p2), "-k", "country", "store_id"])
    assert code1 == 0

    # Test comma-separated keys
    code2 = main(["reconcile", "-s", str(p1), "-t", str(p2), "-k", "country,store_id"])
    assert code2 == 0


def test_reconcile_output_json_and_excel(sample_csv: Path, target_csv_matching: Path, tmp_path: Path):
    """Reconciliation should write JSON and Excel outputs."""
    out_json = tmp_path / "rec.json"
    out_xlsx = tmp_path / "rec.xlsx"

    code_json = main([
        "reconcile",
        "-s", str(sample_csv),
        "-t", str(target_csv_matching),
        "-k", "id",
        "-o", str(out_json),
    ])
    assert code_json == 0
    assert out_json.is_file()
    rec_data = json.loads(out_json.read_text(encoding="utf-8"))
    assert rec_data["summary"]["match_rate_percent"] == 100.0

    code_xlsx = main([
        "reconcile",
        "-s", str(sample_csv),
        "-t", str(target_csv_matching),
        "-k", "id",
        "-o", str(out_xlsx),
    ])
    assert code_xlsx == 0
    assert out_xlsx.is_file()
    assert out_xlsx.stat().st_size > 0


def test_reconcile_missing_key_column_error(sample_csv: Path, target_csv_matching: Path, capsys):
    """Reconciliation with non-existent key column should exit with code 2."""
    exit_code = main([
        "reconcile",
        "-s", str(sample_csv),
        "-t", str(target_csv_matching),
        "-k", "non_existent_key",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error during reconciliation" in captured.err


def test_reconcile_missing_source_file(target_csv_matching: Path, capsys):
    """Missing source file should exit with code 2."""
    exit_code = main([
        "reconcile",
        "-s", "missing_src.csv",
        "-t", str(target_csv_matching),
        "-k", "id",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Source file not found" in captured.err


# ==============================================================================
# 4. 'ui' Subcommand Tests
# ==============================================================================

def test_find_app_path_resolution(tmp_path: Path):
    """Verify _find_app_path discovers custom path, env var, or local app.py."""
    fake_app = tmp_path / "app.py"
    fake_app.write_text("# fake app", encoding="utf-8")

    # Custom path passed
    assert _find_app_path(str(fake_app)) == fake_app.resolve()

    # Environment variable passed
    with patch.dict("os.environ", {"OPENDATAGUARD_APP_PATH": str(fake_app)}):
        assert _find_app_path() == fake_app.resolve()


def test_ui_subcommand_invokes_streamlit(tmp_path: Path):
    """Verify 'ui' subcommand constructs the expected Streamlit CLI command."""
    fake_app = tmp_path / "app.py"
    fake_app.write_text("# fake app", encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        exit_code = main([
            "ui",
            "--port", "8555",
            "--host", "127.0.0.1",
            "--no-browser",
            "--app-path", str(fake_app),
        ])
        assert exit_code == 0
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert "-m" in cmd_args
        assert "streamlit" in cmd_args
        assert "run" in cmd_args
        assert str(fake_app) in cmd_args
        assert "--server.port" in cmd_args
        assert "8555" in cmd_args
        assert "--server.address" in cmd_args
        assert "127.0.0.1" in cmd_args
        assert "--server.headless" in cmd_args
        assert "true" in cmd_args


def test_ui_app_not_found(capsys):
    """If app.py cannot be found, 'ui' exits with code 2."""
    with patch("opendataguard.cli._find_app_path", return_value=None):
        exit_code = main(["ui"])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "Streamlit app.py could not be located" in captured.err
