"""Validation history storage and retrieval engine for OpenDataGuard.

Stores lightweight execution metadata and summaries in a local SQLite database,
preventing sensitive source data persistence while providing full auditability.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from opendataguard.logging_config import logger
from opendataguard.reconciliation import ReconciliationResult, ReconciliationSummary
from opendataguard.validators import ValidationResult, calculate_data_quality_score

DEFAULT_DB_DIR = Path.home() / ".opendataguard"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "history.db"


def get_history_db_path() -> Path:
    """Return configured or default path to the history SQLite database."""
    env_path = os.getenv("OPENDATAGUARD_HISTORY_DB")
    if env_path:
        p = Path(env_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


class HistoryManager:
    """Manages SQLite storage for validation execution history."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize history manager and ensure schema tables exist."""
        self.db_path = db_path or get_history_db_path()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a sqlite3 connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        """Yield a managed sqlite3 connection that closes cleanly on exit."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        create_runs_table = """
        CREATE TABLE IF NOT EXISTS validation_runs (
            run_id TEXT PRIMARY KEY,
            timestamp_utc TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            total_columns INTEGER NOT NULL,
            total_checks INTEGER NOT NULL,
            passed_checks INTEGER NOT NULL,
            failed_checks INTEGER NOT NULL,
            dq_score REAL NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT
        );
        """
        create_details_table = """
        CREATE TABLE IF NOT EXISTS validation_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            check_name TEXT NOT NULL,
            column_name TEXT,
            passed INTEGER NOT NULL,
            total_records INTEGER NOT NULL,
            failed_records INTEGER NOT NULL,
            message TEXT,
            FOREIGN KEY (run_id) REFERENCES validation_runs (run_id) ON DELETE CASCADE
        );
        """
        create_recon_runs_table = """
        CREATE TABLE IF NOT EXISTS reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            timestamp_utc TEXT NOT NULL,
            source_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            key_columns TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            target_rows INTEGER NOT NULL,
            row_count_diff INTEGER NOT NULL,
            matched_records INTEGER NOT NULL,
            mismatched_records INTEGER NOT NULL,
            source_only_records INTEGER NOT NULL,
            target_only_records INTEGER NOT NULL,
            match_rate REAL NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT
        );
        """
        create_recon_mismatches_table = """
        CREATE TABLE IF NOT EXISTS reconciliation_column_mismatches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            column_name TEXT NOT NULL,
            mismatch_count INTEGER NOT NULL,
            FOREIGN KEY (run_id) REFERENCES reconciliation_runs (run_id) ON DELETE CASCADE
        );
        """
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(create_runs_table)
            conn.execute(create_details_table)
            conn.execute(create_recon_runs_table)
            conn.execute(create_recon_mismatches_table)
            conn.commit()

    def record_run(
        self,
        dataset_name: str,
        total_rows: int,
        total_columns: Any,
        results: Optional[List[ValidationResult]] = None,
        dq_score: Optional[float] = None,
        custom_run_id: Optional[str] = None,
    ) -> str:
        """Record validation run summary and individual check results.

        Supports both standard 4-argument and 3-argument calling forms.
        """
        if isinstance(total_columns, list):
            custom_run_id = dq_score if isinstance(dq_score, str) else custom_run_id
            dq_score = results if isinstance(results, (int, float)) else None
            results = total_columns
            total_columns = 0

        actual_results = results or []
        run_id = custom_run_id or str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        passed_count = sum(1 for r in actual_results if r.passed)
        failed_count = sum(1 for r in actual_results if not r.passed)
        score = dq_score if dq_score is not None else calculate_data_quality_score(actual_results)
        status = "PASSED" if failed_count == 0 else "FAILED"

        summary_payload = {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "total_checks": len(actual_results),
            "passed_checks": passed_count,
            "failed_checks": failed_count,
            "dq_score": score,
        }

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO validation_runs 
                (run_id, timestamp_utc, dataset_name, total_rows, total_columns, total_checks, passed_checks, failed_checks, dq_score, status, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    ts,
                    dataset_name,
                    total_rows,
                    total_columns,
                    len(actual_results),
                    passed_count,
                    failed_count,
                    score,
                    status,
                    json.dumps(summary_payload),
                ),
            )

            for r in actual_results:
                conn.execute(
                    """
                    INSERT INTO validation_details 
                    (run_id, check_name, column_name, passed, total_records, failed_records, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        r.check_name,
                        r.column_name or "",
                        1 if r.passed else 0,
                        r.total_records,
                        r.failed_records,
                        r.message,
                    ),
                )
            conn.commit()

        logger.info("Recorded validation run '%s' for dataset '%s' with score %.2f", run_id, dataset_name, score)
        return run_id

    def get_history(self, limit: int = 50) -> pd.DataFrame:
        """Fetch recent validation runs as a pandas DataFrame.

        Args:
            limit: Maximum number of recent runs to return.

        Returns:
            DataFrame of validation history.
        """
        query = """
        SELECT 
            run_id,
            timestamp_utc,
            dataset_name,
            total_rows,
            total_columns,
            total_checks,
            passed_checks,
            failed_checks,
            dq_score,
            status
        FROM validation_runs
        ORDER BY timestamp_utc DESC
        LIMIT ?
        """
        with self._connection() as conn:
            df = pd.read_sql_query(query, conn, params=(limit,))
        return df

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive details for a specific validation run.

        Args:
            run_id: The UUID of the run.

        Returns:
            Dictionary with run metadata and check details, or None if not found.
        """
        with self._connection() as conn:
            run_cursor = conn.execute("SELECT * FROM validation_runs WHERE run_id = ?", (run_id,))
            run_row = run_cursor.fetchone()
            if not run_row:
                return None

            details_cursor = conn.execute(
                "SELECT check_name, column_name, passed, total_records, failed_records, message FROM validation_details WHERE run_id = ?",
                (run_id,),
            )
            details_rows = details_cursor.fetchall()

        return {
            "run_id": run_row["run_id"],
            "timestamp_utc": run_row["timestamp_utc"],
            "dataset_name": run_row["dataset_name"],
            "total_rows": run_row["total_rows"],
            "total_columns": run_row["total_columns"],
            "total_checks": run_row["total_checks"],
            "passed_checks": run_row["passed_checks"],
            "failed_checks": run_row["failed_checks"],
            "dq_score": run_row["dq_score"],
            "status": run_row["status"],
            "checks": [dict(r) for r in details_rows],
        }

    def record_reconciliation_run(
        self,
        result_or_summary: Union[ReconciliationResult, ReconciliationSummary],
        custom_run_id: Optional[str] = None,
    ) -> str:
        """Record reconciliation run summary and column mismatch breakdown.

        Args:
            result_or_summary: ReconciliationResult or ReconciliationSummary instance.
            custom_run_id: Optional custom identifier.

        Returns:
            The recorded run_id UUID string.
        """
        if hasattr(result_or_summary, "summary"):
            s: ReconciliationSummary = result_or_summary.summary
        else:
            s = result_or_summary

        run_id = custom_run_id or str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        if s.has_key_errors:
            status = "FAILED"
        elif s.mismatched_records == 0 and s.source_only_records == 0 and s.target_only_records == 0:
            status = "MATCHED"
        else:
            status = "DISCREPANCIES"

        key_cols_str = json.dumps(s.key_columns)
        summary_payload = s.to_dict()

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_runs
                (run_id, timestamp_utc, source_name, target_name, key_columns,
                 source_rows, target_rows, row_count_diff, matched_records,
                 mismatched_records, source_only_records, target_only_records,
                 match_rate, status, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    ts,
                    s.source_name,
                    s.target_name,
                    key_cols_str,
                    s.source_rows,
                    s.target_rows,
                    s.row_count_diff,
                    s.matched_records,
                    s.mismatched_records,
                    s.source_only_records,
                    s.target_only_records,
                    s.match_rate_percent,
                    status,
                    json.dumps(summary_payload),
                ),
            )

            for col_name, mismatch_cnt in s.column_mismatch_counts.items():
                conn.execute(
                    """
                    INSERT INTO reconciliation_column_mismatches
                    (run_id, column_name, mismatch_count)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, str(col_name), int(mismatch_cnt)),
                )
            conn.commit()

        logger.info(
            "Recorded reconciliation run '%s' (%s vs %s) with match rate %.2f%%",
            run_id,
            s.source_name,
            s.target_name,
            s.match_rate_percent,
        )
        return run_id

    def get_reconciliation_history(self, limit: int = 50) -> pd.DataFrame:
        """Fetch recent reconciliation runs as a pandas DataFrame.

        Args:
            limit: Maximum number of recent runs to return.

        Returns:
            DataFrame of reconciliation history.
        """
        query = """
        SELECT
            run_id,
            timestamp_utc,
            source_name,
            target_name,
            key_columns,
            source_rows,
            target_rows,
            row_count_diff,
            matched_records,
            mismatched_records,
            source_only_records,
            target_only_records,
            match_rate,
            status
        FROM reconciliation_runs
        ORDER BY timestamp_utc DESC
        LIMIT ?
        """
        with self._connection() as conn:
            df = pd.read_sql_query(query, conn, params=(limit,))
        return df

    def get_reconciliation_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive details for a specific reconciliation run.

        Args:
            run_id: The UUID of the run.

        Returns:
            Dictionary with reconciliation metadata and column mismatches, or None if not found.
        """
        with self._connection() as conn:
            run_cursor = conn.execute("SELECT * FROM reconciliation_runs WHERE run_id = ?", (run_id,))
            run_row = run_cursor.fetchone()
            if not run_row:
                return None

            mismatches_cursor = conn.execute(
                "SELECT column_name, mismatch_count FROM reconciliation_column_mismatches WHERE run_id = ?",
                (run_id,),
            )
            mismatch_rows = mismatches_cursor.fetchall()

        summary_dict = {}
        if run_row["summary_json"]:
            try:
                summary_dict = json.loads(run_row["summary_json"])
            except Exception:
                summary_dict = {}

        return {
            "run_id": run_row["run_id"],
            "timestamp_utc": run_row["timestamp_utc"],
            "source_name": run_row["source_name"],
            "target_name": run_row["target_name"],
            "key_columns": json.loads(run_row["key_columns"]) if run_row["key_columns"].startswith("[") else [run_row["key_columns"]],
            "source_rows": run_row["source_rows"],
            "target_rows": run_row["target_rows"],
            "row_count_diff": run_row["row_count_diff"],
            "matched_records": run_row["matched_records"],
            "mismatched_records": run_row["mismatched_records"],
            "source_only_records": run_row["source_only_records"],
            "target_only_records": run_row["target_only_records"],
            "match_rate": run_row["match_rate"],
            "status": run_row["status"],
            "summary": summary_dict,
            "column_mismatches": {r["column_name"]: r["mismatch_count"] for r in mismatch_rows},
        }

    def clear_reconciliation_history(self) -> bool:
        """Delete all recorded reconciliation history records safely.

        Returns:
            True if cleared successfully.
        """
        with self._connection() as conn:
            conn.execute("DELETE FROM reconciliation_column_mismatches")
            conn.execute("DELETE FROM reconciliation_runs")
            conn.commit()
        logger.info("Cleared all reconciliation history from %s", self.db_path)
        return True

    def clear_history(self) -> bool:
        """Delete all recorded history records (validation and reconciliation) safely.

        Returns:
            True if cleared successfully.
        """
        with self._connection() as conn:
            conn.execute("DELETE FROM validation_details")
            conn.execute("DELETE FROM validation_runs")
            conn.execute("DELETE FROM reconciliation_column_mismatches")
            conn.execute("DELETE FROM reconciliation_runs")
            conn.commit()
        logger.info("Cleared all validation and reconciliation history from %s", self.db_path)
        return True
