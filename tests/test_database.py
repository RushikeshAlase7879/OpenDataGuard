"""Unit tests for SQL database inspection engine."""

import pytest
import pandas as pd
from sqlalchemy import text

from opendataguard.database import (
    DatabaseConfig,
    create_safe_engine,
    list_database_tables,
    inspect_table_schema,
    get_table_row_count,
    fetch_table_sample,
)


@pytest.fixture
def sqlite_engine():
    config = DatabaseConfig(dialect="sqlite", sqlite_path=":memory:")
    engine = create_safe_engine(config)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE test_users ("
                "  id INTEGER PRIMARY KEY,"
                "  username TEXT NOT NULL,"
                "  score REAL"
                ");"
            )
        )
        conn.execute(
            text(
                "INSERT INTO test_users (id, username, score) VALUES (1, 'alice', 90.5), (2, 'bob', 82.0);"
            )
        )
        conn.commit()
    return engine


def test_sqlite_in_memory_connection_and_inspection(sqlite_engine):
    tables = list_database_tables(sqlite_engine)
    assert "test_users" in tables

    schema = inspect_table_schema(sqlite_engine, "test_users")
    col_names = [col["name"] for col in schema]
    assert "id" in col_names
    assert "username" in col_names
    assert "score" in col_names

    # Check primary key detection
    id_col = next(col for col in schema if col["name"] == "id")
    assert id_col["is_primary_key"] is True


def test_sqlite_file_not_found():
    bad_config = DatabaseConfig(dialect="sqlite", sqlite_path="non_existent_file_12345.db")
    with pytest.raises(FileNotFoundError):
        create_safe_engine(bad_config)


def test_database_credentials_masked_in_url():
    pg_config = DatabaseConfig(
        dialect="postgresql",
        host="localhost",
        port=5432,
        database="testdb",
        username="admin",
        password="super_secret_password_123",
    )
    masked = pg_config.get_masked_url()
    assert "super_secret_password_123" not in masked
    assert "admin:***@" in masked


def test_table_row_count_and_sample_fetch(sqlite_engine):
    cnt = get_table_row_count(sqlite_engine, "test_users")
    assert cnt == 2

    df = fetch_table_sample(sqlite_engine, "test_users", limit=10)
    assert len(df) == 2
    assert list(df["username"]) == ["alice", "bob"]


def test_invalid_table_name_rejected(sqlite_engine):
    with pytest.raises(ValueError, match="does not exist"):
        inspect_table_schema(sqlite_engine, "non_existent_table")

    with pytest.raises(ValueError, match="not found"):
        get_table_row_count(sqlite_engine, "non_existent_table")


def test_destructive_sql_table_name_rejected(sqlite_engine):
    destructive_payloads = [
        "DROP TABLE test_users;--",
        "test_users; DELETE FROM test_users;",
        "SELECT * FROM test_users",
    ]
    for payload in destructive_payloads:
        with pytest.raises(ValueError):
            inspect_table_schema(sqlite_engine, payload)
        with pytest.raises(ValueError):
            get_table_row_count(sqlite_engine, payload)
        with pytest.raises(ValueError):
            fetch_table_sample(sqlite_engine, payload)


def test_table_sample_bounded_limit(sqlite_engine):
    # Verify limit parameter enforces bounded result
    df = fetch_table_sample(sqlite_engine, "test_users", limit=1)
    assert len(df) == 1

