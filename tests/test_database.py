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


def test_postgresql_connection_error_and_password_masking():
    # If psycopg2 is absent, create_safe_engine must raise ConnectionError and mask password
    pg_config = DatabaseConfig(
        dialect="postgresql",
        host="localhost",
        port=5432,
        database="testdb",
        username="admin",
        password="unexposed_secret_password_999",
    )
    with pytest.raises(ConnectionError) as exc_info:
        create_safe_engine(pg_config)

    err_msg = str(exc_info.value)
    assert "unexposed_secret_password_999" not in err_msg


def test_sqlite_file_database_roundtrip(tmp_path):
    import sqlite3
    db_file = tmp_path / "test_local.db"
    # Create the SQLite file first so it exists on disk
    init_conn = sqlite3.connect(str(db_file))
    init_conn.execute("CREATE TABLE init_tbl (id INTEGER);")
    init_conn.commit()
    init_conn.close()

    config = DatabaseConfig(dialect="sqlite", sqlite_path=str(db_file))
    engine = create_safe_engine(config)

    # Populate a test table
    sample_df = pd.DataFrame({"product": ["Widget", "Gadget"], "price": [19.99, 29.99]})
    sample_df.to_sql("inventory", engine, index=False)

    tables = list_database_tables(engine)
    assert "inventory" in tables

    schema = inspect_table_schema(engine, "inventory")
    assert len(schema) == 2

    row_count = get_table_row_count(engine, "inventory")
    assert row_count == 2

    fetched = fetch_table_sample(engine, "inventory", limit=5)
    assert len(fetched) == 2
    assert list(fetched["product"]) == ["Widget", "Gadget"]


def test_database_valid_tables_optimization(sqlite_engine):
    """Verify that passing pre-validated table collections works across schema, count, and sample."""
    valid_list = ["test_users"]
    schema = inspect_table_schema(sqlite_engine, "test_users", valid_tables=valid_list)
    assert len(schema) == 3

    cnt = get_table_row_count(sqlite_engine, "test_users", valid_tables=valid_list)
    assert cnt == 2

    df = fetch_table_sample(sqlite_engine, "test_users", limit=10, valid_tables=valid_list)
    assert len(df) == 2


def test_database_valid_tables_rejection(sqlite_engine):
    """Verify that passing a pre-validated collection rejects unlisted tables before querying."""
    valid_list = ["other_table"]
    with pytest.raises(ValueError, match="not found in database catalog"):
        get_table_row_count(sqlite_engine, "test_users", valid_tables=valid_list)

    with pytest.raises(ValueError, match="not found in database catalog"):
        fetch_table_sample(sqlite_engine, "test_users", valid_tables=valid_list)

    with pytest.raises(ValueError, match="does not exist in database catalog"):
        inspect_table_schema(sqlite_engine, "test_users", valid_tables=valid_list)


def test_database_fast_has_table_reflection(sqlite_engine):
    """Verify fast has_table inspection rejects invalid tables with proper ValueError."""
    with pytest.raises(ValueError, match="not found in database catalog"):
        get_table_row_count(sqlite_engine, "non_existent_quick_check")

    with pytest.raises(ValueError, match="not found in database catalog"):
        fetch_table_sample(sqlite_engine, "non_existent_quick_check")


def test_list_database_schemas_sqlite(sqlite_engine):
    """SQLite engine should return valid schemas list (such as ['main'])."""
    from opendataguard.database import list_database_schemas

    schemas = list_database_schemas(sqlite_engine)
    assert isinstance(schemas, list)
    assert len(schemas) >= 1
    assert "main" in schemas


def test_list_database_tables_with_schema(sqlite_engine):
    """Specifying schema='main' on SQLite should return tables in main schema."""
    tables = list_database_tables(sqlite_engine, schema="main")
    assert "test_users" in tables


def test_database_nonexistent_schema_raises(sqlite_engine):
    """Specifying an unknown schema when schema reflection is supported raises ValueError."""
    with pytest.raises(ValueError, match="Schema 'nonexistent_schema' does not exist"):
        list_database_tables(sqlite_engine, schema="nonexistent_schema")


def test_mock_multischema_database_inspection():
    """Verify schema parameter propagation to inspect, columns, count, and sampling."""
    from unittest.mock import MagicMock, patch
    from opendataguard.database import (
        list_database_schemas,
        list_database_tables,
        inspect_table_schema,
    )

    mock_engine = MagicMock()
    mock_inspector = MagicMock()
    mock_inspector.get_schema_names.return_value = ["analytics", "public"]
    mock_inspector.get_table_names.return_value = ["daily_active_users"]
    mock_inspector.has_table.return_value = True
    mock_inspector.get_columns.return_value = [
        {"name": "user_id", "type": "INTEGER", "nullable": False, "default": None},
        {"name": "event_date", "type": "DATE", "nullable": False, "default": None},
    ]
    mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["user_id", "event_date"]}

    with patch("opendataguard.database.inspect", return_value=mock_inspector):
        schemas = list_database_schemas(mock_engine)
        assert schemas == ["analytics", "public"]

        tables = list_database_tables(mock_engine, schema="analytics")
        assert tables == ["daily_active_users"]
        mock_inspector.get_table_names.assert_called_with(schema="analytics")

        col_defs = inspect_table_schema(mock_engine, "daily_active_users", schema="analytics")
        assert len(col_defs) == 2
        assert col_defs[0]["name"] == "user_id"
        assert col_defs[0]["is_primary_key"] is True
        mock_inspector.get_columns.assert_called_with("daily_active_users", schema="analytics")
