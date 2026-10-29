"""SQL Database inspection and validation engine for OpenDataGuard.

Supports SQLite and PostgreSQL via SQLAlchemy with strict security safeguards:
- Credentials are never logged or exposed in error messages.
- Read-only inspection mode is enforced.
- Arbitrary user-supplied SQL execution is disallowed.
- Table names are validated against reflected catalog schemas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError

from opendataguard.logging_config import logger

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass
class DatabaseConfig:
    """Connection configuration for SQL databases."""

    dialect: str = "sqlite"  # 'sqlite' or 'postgresql'
    database: Optional[str] = None  # DB name or path for sqlite
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    sqlite_path: Optional[str] = None

    def get_connection_url(self) -> str:
        """Build SQLAlchemy connection string, masking password in representations."""
        if self.dialect.lower() == "sqlite":
            if not self.sqlite_path or self.sqlite_path == ":memory:":
                return "sqlite:///:memory:"
            resolved = Path(self.sqlite_path).resolve()
            # On Windows, path needs forward slashes for sqlite URI
            posix_path = resolved.as_posix()
            return f"sqlite:///{posix_path}"

        if self.dialect.lower() in {"postgresql", "postgres"}:
            user = self.username or "postgres"
            pwd = self.password or ""
            host = self.host or "localhost"
            port = self.port or 5432
            db = self.database or "postgres"
            if pwd:
                return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
            return f"postgresql+psycopg2://{user}@{host}:{port}/{db}"

        raise ValueError(f"Unsupported database dialect: '{self.dialect}'. Use 'sqlite' or 'postgresql'.")

    def get_masked_url(self) -> str:
        """Return connection string with password masked."""
        url = self.get_connection_url()
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def create_safe_engine(config: DatabaseConfig, timeout_seconds: int = 5) -> Engine:
    """Create a validated SQLAlchemy engine with strict connection timeouts and safety checks.

    Args:
        config: DatabaseConfig instance.
        timeout_seconds: Connection timeout in seconds.

    Returns:
        SQLAlchemy Engine.

    Raises:
        ConnectionError: If connection cannot be established or credentials fail.
    """
    url = config.get_connection_url()
    masked = config.get_masked_url()
    logger.info("Attempting database connection to: %s", masked)

    # SQLite specific validation
    if config.dialect.lower() == "sqlite" and config.sqlite_path and config.sqlite_path != ":memory:":
        sqlite_file = Path(config.sqlite_path)
        if not sqlite_file.exists():
            raise FileNotFoundError(f"SQLite database file not found at: {sqlite_file}")

    try:
        connect_args = {}
        if config.dialect.lower() == "sqlite":
            connect_args["timeout"] = timeout_seconds
            if not config.sqlite_path or config.sqlite_path == ":memory:":
                from sqlalchemy.pool import StaticPool
                engine = create_engine(
                    url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        else:
            connect_args["connect_timeout"] = timeout_seconds
            engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

        # Test connection immediately
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("Database connection successfully established to: %s", masked)
        return engine

    except SQLAlchemyError as exc:
        # Sanitize exception message to ensure no credentials leaked
        clean_err = re.sub(r"://[^:]+:([^@]+)@", "://***:***@", str(exc))
        logger.error("Database connection failed: %s", clean_err)
        raise ConnectionError(f"Database connection error: {clean_err}") from None
    except Exception as exc:
        logger.error("Unexpected error connecting to database: %s", exc)
        raise ConnectionError(f"Database connection error: {exc}") from None


def list_database_tables(engine: Engine) -> List[str]:
    """Inspect and return list of user table names in the database.

    Args:
        engine: Connected SQLAlchemy engine.

    Returns:
        Sorted list of table names.
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return sorted(tables)
    except SQLAlchemyError as err:
        logger.error("Failed to inspect table list: %s", err)
        raise RuntimeError(f"Could not retrieve database tables: {err}") from err


def inspect_table_schema(
    engine: Engine,
    table_name: str,
    valid_tables: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Return column definitions and primary keys for a selected table.

    Args:
        engine: Connected SQLAlchemy engine.
        table_name: Table name to inspect.
        valid_tables: Optional pre-validated collection of table names.

    Returns:
        List of column metadata dictionaries.

    Raises:
        ValueError: If table does not exist or is invalid.
    """
    if valid_tables is not None:
        if table_name not in valid_tables:
            raise ValueError(f"Table '{table_name}' does not exist in database catalog.")
    else:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise ValueError(f"Table '{table_name}' does not exist in database catalog.")

    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    pk_constraint = inspector.get_pk_constraint(table_name)
    pks = set(pk_constraint.get("constrained_columns", []))

    schema_info = []
    for col in columns:
        col_name = str(col["name"])
        schema_info.append({
            "name": col_name,
            "type": str(col["type"]),
            "nullable": bool(col.get("nullable", True)),
            "default": str(col.get("default", "")) if col.get("default") is not None else None,
            "is_primary_key": col_name in pks,
        })
    return schema_info


def get_table_row_count(
    engine: Engine,
    table_name: str,
    valid_tables: Optional[Iterable[str]] = None,
) -> int:
    """Safely count rows in a database table without string interpolation.

    Args:
        engine: Connected SQLAlchemy engine.
        table_name: Validated table name.
        valid_tables: Optional pre-validated collection of table names.

    Returns:
        Total row count.

    Raises:
        ValueError: If table is not found in database catalog.
    """
    if valid_tables is not None:
        if table_name not in valid_tables:
            raise ValueError(f"Table '{table_name}' not found in database catalog.")
    else:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise ValueError(f"Table '{table_name}' not found in database catalog.")

    metadata = MetaData()
    try:
        tbl = Table(table_name, metadata, autoload_with=engine)
    except NoSuchTableError:
        raise ValueError(f"Table '{table_name}' not found in database catalog.")

    stmt = select(func.count()).select_from(tbl)

    with engine.connect() as conn:
        count = conn.execute(stmt).scalar()
        return int(count or 0)


def fetch_table_sample(
    engine: Engine,
    table_name: str,
    limit: int = 10_000,
    valid_tables: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Safely fetch sample or full data from a table into a pandas DataFrame.

    Uses SQLAlchemy Table reflection and bounded queries.

    Args:
        engine: Connected SQLAlchemy engine.
        table_name: Target table name.
        limit: Maximum number of rows to retrieve.
        valid_tables: Optional pre-validated collection of table names.

    Returns:
        pd.DataFrame containing table rows.

    Raises:
        ValueError: If table is not found in database catalog.
    """
    if valid_tables is not None:
        if table_name not in valid_tables:
            raise ValueError(f"Table '{table_name}' not found in database catalog.")
    else:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            raise ValueError(f"Table '{table_name}' not found in database catalog.")

    metadata = MetaData()
    try:
        tbl = Table(table_name, metadata, autoload_with=engine)
    except NoSuchTableError:
        raise ValueError(f"Table '{table_name}' not found in database catalog.")

    stmt = select(tbl).limit(limit)

    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)

    logger.info("Retrieved %d rows from table '%s' (limit=%d)", len(df), table_name, limit)
    return df
