"""Unit tests for OpenDataGuard validators and ingestion engine."""

import io
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from opendataguard.validators import (
    load_dataset,
    validate_file_safety,
    read_csv_in_chunks,
    check_missing_values,
    check_duplicate_rows,
    check_key_uniqueness,
    check_data_types,
    check_date_validity,
    check_numeric_validity,
    check_value_range,
    check_string_length,
    check_allowed_values,
    check_regex_pattern,
    check_email_format,
    check_schema_mismatch,
    calculate_data_quality_score,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [25, 30, 45, 12, 60],
        "score": [85.5, 90.0, np.nan, 72.0, 99.5],
        "status": ["ACTIVE", "ACTIVE", "INACTIVE", "PENDING", "ACTIVE"],
        "joined": ["2023-01-01", "2023-02-15", "2023-03-20", "2023-04-10", "2023-05-01"],
    })


def test_load_dataset_csv_buffer():
    csv_bytes = b"col1,col2\n1,alpha\n2,beta\n"
    df, meta = load_dataset(io.BytesIO(csv_bytes), filename="test.csv")
    assert len(df) == 2
    assert meta.column_count == 2
    assert meta.name == "test.csv"


def test_load_dataset_excel_buffer(tmp_path):
    df_orig = pd.DataFrame({"a": [10, 20], "b": ["x", "y"]})
    excel_path = tmp_path / "test.xlsx"
    df_orig.to_excel(excel_path, index=False)

    df_loaded, meta = load_dataset(excel_path)
    assert len(df_loaded) == 2
    assert list(df_loaded.columns) == ["a", "b"]
    assert meta.row_count == 2


def test_load_dataset_empty_fails():
    empty_bytes = b""
    with pytest.raises(ValueError, match="completely empty"):
        load_dataset(io.BytesIO(empty_bytes), filename="empty.csv")


def test_load_dataset_oversized_fails():
    content = b"col1,col2\n" + (b"1,2\n" * 100)
    with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
        load_dataset(io.BytesIO(content), filename="large.csv", max_size_bytes=50)


def test_load_dataset_unsupported_extension():
    content = b"fake binary data"
    with pytest.raises(ValueError, match="Unsupported file format"):
        load_dataset(io.BytesIO(content), filename="malicious.exe")


def test_missing_values_check(sample_df):
    res_overall = check_missing_values(sample_df)
    assert not res_overall.passed
    assert res_overall.failed_records == 1  # 1 row contains NaN

    res_col = check_missing_values(sample_df, column="score")
    assert not res_col.passed
    assert res_col.failed_records == 1

    res_clean_col = check_missing_values(sample_df, column="name")
    assert res_clean_col.passed
    assert res_clean_col.failed_records == 0


def test_duplicate_rows_check():
    df_dups = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "val": ["a", "b", "b", "c"],
    })
    res = check_duplicate_rows(df_dups)
    assert not res.passed
    assert res.failed_records == 2  # Two duplicate rows

    df_clean = pd.DataFrame({"id": [1, 2, 3], "val": ["a", "b", "c"]})
    assert check_duplicate_rows(df_clean).passed


def test_key_uniqueness_check():
    df = pd.DataFrame({
        "id": [101, 102, 102, None],
        "name": ["A", "B", "C", "D"],
    })
    res = check_key_uniqueness(df, key_columns="id")
    assert not res.passed
    assert res.failed_records == 3  # Two duplicate 102s + 1 null key


def test_data_types_check(sample_df):
    expected = {"id": "int", "name": "string", "score": "float"}
    res = check_data_types(sample_df, expected_types=expected)
    assert res.passed

    # Intentionally bad expectation
    bad_expected = {"name": "int"}
    res_bad = check_data_types(sample_df, expected_types=bad_expected)
    assert not res_bad.passed


def test_date_validity_check():
    df = pd.DataFrame({
        "date_str": ["2023-01-01", "2023-02-29", "invalid-date", "1990-01-01"],
    })
    res = check_date_validity(df, column="date_str", min_date="2000-01-01")
    assert not res.passed
    assert res.failed_records >= 2  # 2023 is not leap year so 02-29 invalid, invalid-date, 1990 is < 2000


def test_numeric_validity_check():
    df = pd.DataFrame({
        "num": [10, 20.5, "not-a-number", np.inf],
    })
    res = check_numeric_validity(df, column="num", allow_inf=False)
    assert not res.passed
    assert res.failed_records == 2  # "not-a-number" and np.inf


def test_value_range_check(sample_df):
    res = check_value_range(sample_df, column="age", min_value=18, max_value=65)
    assert not res.passed
    assert res.failed_records == 1  # 12 is < 18

    res_pass = check_value_range(sample_df, column="age", min_value=0, max_value=100)
    assert res_pass.passed


def test_string_length_check(sample_df):
    res = check_string_length(sample_df, column="name", min_length=2, max_length=5)
    assert not res.passed
    assert res.failed_records == 1  # "Charlie" is 7 chars

    res_pass = check_string_length(sample_df, column="name", min_length=2, max_length=20)
    assert res_pass.passed


def test_allowed_values_check(sample_df):
    res = check_allowed_values(sample_df, column="status", allowed_values=["ACTIVE", "INACTIVE"])
    assert not res.passed
    assert res.failed_records == 1  # "PENDING" not in set

    res_pass = check_allowed_values(sample_df, column="status", allowed_values=["ACTIVE", "INACTIVE", "PENDING"])
    assert res_pass.passed


def test_schema_mismatch_check(sample_df):
    res = check_schema_mismatch(sample_df, expected_columns=["id", "name", "missing_col"])
    assert not res.passed
    assert "missing_col" in res.message

    res_pass = check_schema_mismatch(sample_df, expected_columns=["id", "name", "age"])
    assert res_pass.passed


def test_calculate_data_quality_score():
    r1 = check_missing_values(pd.DataFrame({"a": [1, 2, 3, 4]}))  # 100%
    r2 = check_missing_values(pd.DataFrame({"a": [1, None, 3, 4]}))  # 75%
    score = calculate_data_quality_score([r1, r2])
    assert score == 87.5


def test_read_csv_in_chunks(tmp_path):
    csv_file = tmp_path / "chunk_test.csv"
    pd.DataFrame({"x": range(100)}).to_csv(csv_file, index=False)
    chunks = list(read_csv_in_chunks(csv_file, chunksize=25))
    assert len(chunks) == 4
    assert sum(len(c) for c in chunks) == 100


def test_regex_pattern_check():
    df = pd.DataFrame({"code": ["AB-12", "CD-34", "INVALID", None]})
    res = check_regex_pattern(df, column="code", pattern=r"^[A-Z]{2}-\d{2}$")
    assert not res.passed
    assert res.failed_records == 1  # "INVALID" fails, None is ignored

    res_all_valid = check_regex_pattern(
        pd.DataFrame({"code": ["AB-12", "CD-34"]}),
        column="code",
        pattern=r"^[A-Z]{2}-\d{2}$",
    )
    assert res_all_valid.passed


def test_email_format_check():
    df = pd.DataFrame({
        "email": [
            "valid.user@example.com",
            "support@domain.org",
            "not-an-email",
            "@missing-local.com",
            "user@nodomain",
            None,
        ]
    })
    res = check_email_format(df, column="email")
    assert not res.passed
    assert res.failed_records == 3  # not-an-email, @missing-local.com, user@nodomain
    assert "email_format" == res.check_name

    df_clean = pd.DataFrame({"email": ["alice@work.co", "bob123@sub.domain.edu"]})
    res_clean = check_email_format(df_clean, column="email")
    assert res_clean.passed
    assert res_clean.failed_records == 0


def test_valid_dataset_passes_all_checks():
    df_clean = pd.DataFrame({
        "id": [1, 2, 3],
        "email": ["a@test.com", "b@test.com", "c@test.com"],
        "age": [25, 30, 35],
        "status": ["ACTIVE", "PENDING", "ACTIVE"],
        "signup": ["2023-01-01", "2023-02-01", "2023-03-01"],
    })
    assert check_missing_values(df_clean).passed
    assert check_duplicate_rows(df_clean).passed
    assert check_key_uniqueness(df_clean, key_columns="id").passed
    assert check_data_types(df_clean, expected_types={"id": "int", "age": "int"}).passed
    assert check_value_range(df_clean, column="age", min_value=18, max_value=65).passed
    assert check_email_format(df_clean, column="email").passed
    assert check_date_validity(df_clean, column="signup").passed
    assert check_allowed_values(df_clean, column="status", allowed_values=["ACTIVE", "PENDING"]).passed


def test_empty_dataframe_validator_handling():
    empty_df = pd.DataFrame(columns=["id", "name", "val"])
    # All checks should handle 0 rows gracefully without unhandled exceptions
    assert check_missing_values(empty_df).passed
    assert check_duplicate_rows(empty_df).passed
    assert check_key_uniqueness(empty_df, key_columns="id").passed
    assert check_data_types(empty_df, expected_types={"id": "int"}).passed
    assert check_value_range(empty_df, column="val", min_value=0, max_value=100).passed
    assert check_email_format(empty_df, column="name").passed
    assert check_date_validity(empty_df, column="name").passed


def test_missing_column_across_validators():
    df = pd.DataFrame({"existing_col": [1, 2, 3]})
    # When a non-existent column is passed, validators return passed=False with an informative message
    r1 = check_missing_values(df, column="non_existent")
    assert not r1.passed
    assert "does not exist" in r1.message

    r2 = check_key_uniqueness(df, key_columns="non_existent")
    assert not r2.passed
    assert "not found" in r2.message

    r3 = check_value_range(df, column="non_existent", min_value=0)
    assert not r3.passed
    assert "not found" in r3.message

    r4 = check_string_length(df, column="non_existent", min_length=1)
    assert not r4.passed
    assert "not found" in r4.message

    r5 = check_allowed_values(df, column="non_existent", allowed_values=["A"])
    assert not r5.passed
    assert "not found" in r5.message

    r6 = check_date_validity(df, column="non_existent")
    assert not r6.passed
    assert "not found" in r6.message

    r7 = check_numeric_validity(df, column="non_existent")
    assert not r7.passed
    assert "not found" in r7.message

    r8 = check_regex_pattern(df, column="non_existent", pattern=r"^\d+$")
    assert not r8.passed
    assert "not found" in r8.message


def test_load_dataset_tsv_file(tmp_path):
    tsv_file = tmp_path / "test.tsv"
    tsv_file.write_text("id\tname\tscore\n1\tAlice\t95\n2\tBob\t88\n", encoding="utf-8")
    df, meta = load_dataset(tsv_file)
    assert len(df) == 2
    assert meta.column_count == 3
    assert list(df.columns) == ["id", "name", "score"]
    assert df.iloc[0]["name"] == "Alice"


def test_load_dataset_duplicate_column_detection(tmp_path):
    csv_file = tmp_path / "dupe_cols.csv"
    csv_file.write_text("item,item,qty\napple,banana,10\n", encoding="utf-8")
    df, meta = load_dataset(csv_file)
    assert len(df) == 1
    assert meta.column_count == 3
    assert len(meta.duplicate_columns) >= 1
    assert "item.1" in meta.duplicate_columns


def test_missing_values_with_empty_strings():
    df = pd.DataFrame({"col": ["valid", "", "   ", None, "ok"]})
    # Default: empty strings are not considered null
    res_default = check_missing_values(df, column="col", treat_empty_as_missing=False)
    assert res_default.failed_records == 1  # Only None

    # With treat_empty_as_missing=True: empty and whitespace are also flagged
    res_strict = check_missing_values(df, column="col", treat_empty_as_missing=True)
    assert res_strict.failed_records == 3  # "", "   ", None


def test_key_uniqueness_composite_keys():
    df_valid = pd.DataFrame({
        "country": ["US", "US", "CA", "CA"],
        "postal": ["10001", "90210", "H3Z", "V6B"],
    })
    res_valid = check_key_uniqueness(df_valid, key_columns=["country", "postal"])
    assert res_valid.passed
    assert res_valid.failed_records == 0

    df_dupe = pd.DataFrame({
        "country": ["US", "US", "CA"],
        "postal": ["10001", "10001", "H3Z"],
    })
    res_dupe = check_key_uniqueness(df_dupe, key_columns=["country", "postal"])
    assert not res_dupe.passed
    assert res_dupe.failed_records == 2


def test_date_chronological_ordering():
    df_chrono = pd.DataFrame({
        "dates": ["2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01"]
    })
    res_pass = check_date_validity(df_chrono, column="dates", check_chronological_order=True)
    assert res_pass.passed
    assert res_pass.failed_records == 0

    df_out_of_order = pd.DataFrame({
        "dates": ["2023-01-01", "2023-03-01", "2023-02-01", "2023-04-01"]
    })
    res_fail = check_date_validity(df_out_of_order, column="dates", check_chronological_order=True)
    assert not res_fail.passed
    assert res_fail.failed_records == 1


def test_validators_do_not_mutate_input_dataframe(sample_df):
    df_copy = sample_df.copy(deep=True)
    # Execute multiple validators
    check_missing_values(sample_df)
    check_duplicate_rows(sample_df)
    check_key_uniqueness(sample_df, key_columns="id")
    check_data_types(sample_df, expected_types={"id": "int", "name": "string"})
    check_value_range(sample_df, column="age", min_value=0, max_value=120)
    check_date_validity(sample_df, column="joined")
    check_string_length(sample_df, column="name", min_length=1, max_length=50)
    check_allowed_values(sample_df, column="status", allowed_values=["ACTIVE", "INACTIVE", "PENDING"])
    check_regex_pattern(sample_df, column="name", pattern=r"^[A-Z][a-z]+$")

    # Assert DataFrame is completely unchanged
    pd.testing.assert_frame_equal(sample_df, df_copy)


def test_default_max_file_size_env_var(monkeypatch):
    from opendataguard.validators import get_default_max_file_size_bytes, validate_file_safety
    
    # Default without env var
    monkeypatch.delenv("OPENDATAGUARD_MAX_UPLOAD_BYTES", raising=False)
    assert get_default_max_file_size_bytes() == 100 * 1024 * 1024

    # Custom valid env var
    monkeypatch.setenv("OPENDATAGUARD_MAX_UPLOAD_BYTES", "52428800")
    assert get_default_max_file_size_bytes() == 52428800

    # Invalid env var fallback
    monkeypatch.setenv("OPENDATAGUARD_MAX_UPLOAD_BYTES", "not-a-number")
    assert get_default_max_file_size_bytes() == 100 * 1024 * 1024


def test_validate_file_safety_uses_env_var(monkeypatch):
    from opendataguard.validators import validate_file_safety
    
    # Set limit to 50 bytes
    monkeypatch.setenv("OPENDATAGUARD_MAX_UPLOAD_BYTES", "50")
    
    content_ok = b"a,b,c\n1,2,3\n"
    content_too_large = b"a" * 100
    
    ext, sz = validate_file_safety(io.BytesIO(content_ok), filename="test.csv")
    assert ext == ".csv"
    assert sz == len(content_ok)
    
    with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
        validate_file_safety(io.BytesIO(content_too_large), filename="large.csv")



