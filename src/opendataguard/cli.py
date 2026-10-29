"""Command-Line Interface (CLI) for OpenDataGuard.

Provides native CLI commands for dataset validation, reconciliation,
interactive UI startup, and version verification.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import opendataguard
from opendataguard.logging_config import logger
from opendataguard.reconciliation import reconcile_datasets
from opendataguard.reports import (
    generate_reconciliation_excel,
    generate_validation_csv,
    generate_validation_excel,
    generate_validation_json,
)
from opendataguard.rules import execute_rule_suite, load_rules
from opendataguard.validators import calculate_data_quality_score, load_dataset


def _find_app_path(custom_path: Optional[str] = None) -> Optional[Path]:
    """Resolve the location of the OpenDataGuard Streamlit app.py."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_file():
            return p

    env_path = os.environ.get("OPENDATAGUARD_APP_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.is_file():
            return p

    # Check current working directory
    cwd_app = Path.cwd() / "app.py"
    if cwd_app.is_file():
        return cwd_app

    # Check relative to package location (e.g. repo root when running from source)
    repo_root_app = Path(__file__).resolve().parent.parent.parent / "app.py"
    if repo_root_app.is_file():
        return repo_root_app

    # Check inside package directory
    pkg_app = Path(__file__).resolve().parent / "app.py"
    if pkg_app.is_file():
        return pkg_app

    return None


def _handle_version(args: argparse.Namespace) -> int:
    """Handle the 'version' subcommand."""
    print(f"OpenDataGuard {opendataguard.__version__} (Python {platform.python_version()} on {platform.system()})")
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    """Handle the 'validate' subcommand."""
    data_path = Path(args.data)
    if not data_path.is_file():
        sys.stderr.write(f"Error: Data file not found at '{data_path}'\n")
        return 2

    rules_path = Path(args.rules)
    if not rules_path.is_file():
        sys.stderr.write(f"Error: Rules file not found at '{rules_path}'\n")
        return 2

    # Ingest dataset
    try:
        df, meta = load_dataset(str(data_path))
    except Exception as exc:
        sys.stderr.write(f"Error loading dataset from '{data_path}': {exc}\n")
        return 2

    # Load and validate rules
    try:
        rules_config = load_rules(rules_path)
    except Exception as exc:
        sys.stderr.write(f"Error loading rule suite from '{rules_path}': {exc}\n")
        return 2

    # Execute validation suite
    try:
        results = execute_rule_suite(df, rules_config)
    except Exception as exc:
        sys.stderr.write(f"Error executing rule suite: {exc}\n")
        return 2

    total_checks = len(results)
    passed_checks = sum(1 for r in results if r.passed)
    failed_checks = sum(1 for r in results if not r.passed)
    score = calculate_data_quality_score(results)
    dataset_name = args.dataset_name or data_path.stem

    # Print summary to stdout
    print("=" * 80)
    print("OpenDataGuard Quality Validation Report")
    print("=" * 80)
    print(f"Dataset:        {dataset_name}")
    print(f"File Path:      {data_path}")
    print(f"Total Rows:     {len(df):,}")
    print(f"Total Columns:  {len(df.columns):,}")
    print(f"Total Checks:   {total_checks}")
    print(f"Passed Checks:  {passed_checks}")
    print(f"Failed Checks:  {failed_checks}")
    print(f"Quality Score:  {score:.2f}%")
    print(f"Overall Status: {'PASSED' if failed_checks == 0 else 'FAILED'}")

    if failed_checks > 0:
        print("-" * 80)
        print("Failed Checks:")
        for r in results:
            if not r.passed:
                col_info = f" (column: {r.column_name})" if r.column_name else ""
                print(f"  [FAIL] {r.check_name}{col_info}")
                print(f"         {r.message}")
    print("=" * 80)

    # Save output report if requested
    if args.output:
        out_path = Path(args.output)
        out_format = args.format
        if not out_format:
            ext = out_path.suffix.lower()
            if ext == ".xlsx":
                out_format = "xlsx"
            elif ext == ".csv":
                out_format = "csv"
            else:
                out_format = "json"

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_format == "xlsx":
                generate_validation_excel(
                    results=results,
                    dataset_name=dataset_name,
                    row_count=len(df),
                    column_count=len(df.columns),
                    output_file=out_path,
                )
            elif out_format == "csv":
                csv_str = generate_validation_csv(
                    results=results,
                    dataset_name=dataset_name,
                )
                out_path.write_text(csv_str, encoding="utf-8")
            else:
                json_str = generate_validation_json(
                    results=results,
                    dataset_name=dataset_name,
                    row_count=len(df),
                    column_count=len(df.columns),
                )
                out_path.write_text(json_str, encoding="utf-8")

            print(f"Validation report saved to: {out_path.resolve()} ({out_format.upper()})")
        except Exception as exc:
            sys.stderr.write(f"Error saving validation report to '{out_path}': {exc}\n")
            return 2

    # Exit code determination:
    # 0 = All checks passed AND (min_score is None OR score >= min_score)
    # 1 = One or more checks failed OR score < min_score OR (strict and score < 100.0)
    is_passing = (failed_checks == 0)
    if args.min_score is not None:
        if score < args.min_score:
            is_passing = False
    if getattr(args, "strict", False):
        if failed_checks > 0 or score < 100.0:
            is_passing = False

    return 0 if is_passing else 1


def _handle_reconcile(args: argparse.Namespace) -> int:
    """Handle the 'reconcile' subcommand."""
    source_path = Path(args.source)
    if not source_path.is_file():
        sys.stderr.write(f"Error: Source file not found at '{source_path}'\n")
        return 2

    target_path = Path(args.target)
    if not target_path.is_file():
        sys.stderr.write(f"Error: Target file not found at '{target_path}'\n")
        return 2

    # Parse key columns (allow comma-separated or space-separated)
    keys: List[str] = []
    for raw_k in args.keys:
        for part in raw_k.split(","):
            cleaned = part.strip()
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

    if not keys:
        sys.stderr.write("Error: At least one key column must be specified via --keys.\n")
        return 2

    # Parse compare columns if given
    compare_cols: Optional[List[str]] = None
    if args.columns:
        compare_cols = []
        for raw_c in args.columns:
            for part in raw_c.split(","):
                cleaned = part.strip()
                if cleaned and cleaned not in compare_cols:
                    compare_cols.append(cleaned)

    # Ingest datasets
    try:
        df_source, _ = load_dataset(str(source_path))
    except Exception as exc:
        sys.stderr.write(f"Error loading source dataset from '{source_path}': {exc}\n")
        return 2

    try:
        df_target, _ = load_dataset(str(target_path))
    except Exception as exc:
        sys.stderr.write(f"Error loading target dataset from '{target_path}': {exc}\n")
        return 2

    # Perform reconciliation
    try:
        result = reconcile_datasets(
            source_df=df_source,
            target_df=df_target,
            key_columns=keys,
            source_name=args.source_name or source_path.stem,
            target_name=args.target_name or target_path.stem,
            float_atol=args.atol,
            float_rtol=args.rtol,
            ignore_whitespace=not args.no_ignore_whitespace,
            case_sensitive=not args.ignore_case,
            columns_to_compare=compare_cols,
        )
    except Exception as exc:
        sys.stderr.write(f"Error during reconciliation: {exc}\n")
        return 2

    s = result.summary
    is_exact_match = (
        s.mismatched_records == 0
        and s.source_only_records == 0
        and s.target_only_records == 0
        and not s.has_key_errors
    )

    # Print summary to stdout
    print("=" * 80)
    print("OpenDataGuard Dataset Reconciliation Report")
    print("=" * 80)
    print(f"Source Dataset:      {s.source_name} ({s.source_rows:,} rows)")
    print(f"Target Dataset:      {s.target_name} ({s.target_rows:,} rows)")
    print(f"Key Column(s):       {', '.join(s.key_columns)}")
    print(f"Row Difference:      {s.row_count_diff:+,}")
    print("-" * 80)
    print(f"Matched Records:     {s.matched_records:,}")
    print(f"Mismatched Records:  {s.mismatched_records:,}")
    print(f"Source-Only Records: {s.source_only_records:,}")
    print(f"Target-Only Records: {s.target_only_records:,}")
    print(f"Match Rate:          {s.match_rate_percent:.2f}%")
    print(f"Overall Status:      {'MATCHED (100%)' if is_exact_match else 'DISCREPANCIES DETECTED'}")

    if s.has_key_errors:
        print(f"Key Warnings:        {s.key_error_message}")

    if s.column_mismatch_counts:
        print("-" * 80)
        print("Mismatches per Column:")
        for col, count in sorted(s.column_mismatch_counts.items(), key=lambda x: -x[1]):
            print(f"  {col}: {count:,} mismatches")
    print("=" * 80)

    # Save output report if requested
    if args.output:
        out_path = Path(args.output)
        out_format = args.format
        if not out_format:
            ext = out_path.suffix.lower()
            if ext == ".xlsx":
                out_format = "xlsx"
            else:
                out_format = "json"

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_format == "xlsx":
                generate_reconciliation_excel(result, output_file=out_path)
            else:
                report_dict = {
                    "summary": s.to_dict(),
                    "total_mismatched_rows": len(result.mismatched_df),
                    "total_source_only_rows": len(result.source_only_df),
                    "total_target_only_rows": len(result.target_only_df),
                }
                out_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

            print(f"Reconciliation report saved to: {out_path.resolve()} ({out_format.upper()})")
        except Exception as exc:
            sys.stderr.write(f"Error saving reconciliation report to '{out_path}': {exc}\n")
            return 2

    return 0 if is_exact_match else 1


def _handle_ui(args: argparse.Namespace) -> int:
    """Handle the 'ui' subcommand to launch Streamlit platform."""
    app_path = _find_app_path(args.app_path)
    if app_path is None or not app_path.is_file():
        sys.stderr.write(
            "Error: OpenDataGuard Streamlit app.py could not be located.\n"
            "Please specify the path using '--app-path /path/to/app.py' "
            "or set the OPENDATAGUARD_APP_PATH environment variable.\n"
        )
        return 2

    # Check if streamlit is installed
    try:
        import streamlit  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Error: Streamlit is not installed in the current environment.\n"
            "Install it via: pip install streamlit\n"
        )
        return 2

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(args.port),
        "--server.address",
        str(args.host),
    ]

    if getattr(args, "no_browser", False):
        cmd.extend(["--server.headless", "true"])

    print(f"Launching OpenDataGuard UI from '{app_path}' on http://{args.host}:{args.port}...")
    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except KeyboardInterrupt:
        print("\nOpenDataGuard UI stopped.")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error running OpenDataGuard UI: {exc}\n")
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser for the OpenDataGuard CLI."""
    parser = argparse.ArgumentParser(
        prog="opendataguard",
        description="OpenDataGuard: Open-Source Data Quality, Validation, and Reconciliation Platform.",
        epilog="For more information, visit https://github.com/RushikeshAlase7879/OpenDataGuard",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"OpenDataGuard {opendataguard.__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: validate
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate a dataset against declarative JSON or YAML quality rules.",
        description="Run automated data quality checks against a CSV or Excel dataset using declarative rules.",
    )
    val_parser.add_argument(
        "-d",
        "--data",
        required=True,
        help="Path to dataset file (CSV or Excel) to validate.",
    )
    val_parser.add_argument(
        "-r",
        "--rules",
        required=True,
        help="Path to JSON or YAML rule suite definition.",
    )
    val_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to write the validation report (e.g. report.json, report.csv, report.xlsx).",
    )
    val_parser.add_argument(
        "-f",
        "--format",
        choices=["json", "csv", "xlsx"],
        default=None,
        help="Output report format (overrides file extension).",
    )
    val_parser.add_argument(
        "-n",
        "--dataset-name",
        default=None,
        help="Logical dataset name for the report (defaults to data filename stem).",
    )
    val_parser.add_argument(
        "-s",
        "--min-score",
        type=float,
        default=None,
        help="Minimum data quality score (0.0 to 100.0) required to pass. If score is lower, exits with code 1.",
    )
    val_parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: fail if any check or warning occurs.",
    )
    val_parser.set_defaults(func=_handle_validate)

    # Subcommand: reconcile
    rec_parser = subparsers.add_parser(
        "reconcile",
        help="Reconcile two datasets on primary/composite keys and detect discrepancies.",
        description="Compare source and target datasets row-by-row on key columns, identifying mismatches and missing rows.",
    )
    rec_parser.add_argument(
        "-s",
        "--source",
        required=True,
        help="Path to source dataset file (CSV or Excel).",
    )
    rec_parser.add_argument(
        "-t",
        "--target",
        required=True,
        help="Path to target dataset file (CSV or Excel).",
    )
    rec_parser.add_argument(
        "-k",
        "--keys",
        required=True,
        nargs="+",
        help="Primary or composite key column name(s). Accepts space- or comma-separated lists.",
    )
    rec_parser.add_argument(
        "--source-name",
        default=None,
        help="Display label for the source dataset (defaults to file stem).",
    )
    rec_parser.add_argument(
        "--target-name",
        default=None,
        help="Display label for the target dataset (defaults to file stem).",
    )
    rec_parser.add_argument(
        "--atol",
        type=float,
        default=1e-5,
        help="Absolute numeric tolerance for float comparisons (default: 1e-5).",
    )
    rec_parser.add_argument(
        "--rtol",
        type=float,
        default=1e-5,
        help="Relative numeric tolerance for float comparisons (default: 1e-5).",
    )
    rec_parser.add_argument(
        "--no-ignore-whitespace",
        action="store_true",
        help="Do NOT strip leading/trailing whitespace when comparing strings.",
    )
    rec_parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Case-insensitive comparison for text columns.",
    )
    rec_parser.add_argument(
        "-c",
        "--columns",
        nargs="+",
        default=None,
        help="Subset of columns to compare (defaults to all common columns).",
    )
    rec_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to write the reconciliation report (.xlsx or .json).",
    )
    rec_parser.add_argument(
        "-f",
        "--format",
        choices=["xlsx", "json"],
        default=None,
        help="Output report format (overrides file extension).",
    )
    rec_parser.set_defaults(func=_handle_reconcile)

    # Subcommand: ui
    ui_parser = subparsers.add_parser(
        "ui",
        help="Launch the interactive Streamlit web platform in your browser.",
        description="Start the OpenDataGuard interactive data quality and reconciliation web application.",
    )
    ui_parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8501,
        help="Port number for the Streamlit server (default: 8501).",
    )
    ui_parser.add_argument(
        "--host",
        default="localhost",
        help="Host address for the Streamlit server (default: localhost).",
    )
    ui_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Run Streamlit in headless mode without opening a web browser.",
    )
    ui_parser.add_argument(
        "--app-path",
        default=None,
        help="Explicit path to OpenDataGuard app.py file (optional).",
    )
    ui_parser.set_defaults(func=_handle_ui)

    # Subcommand: version
    ver_parser = subparsers.add_parser(
        "version",
        help="Show detailed OpenDataGuard version and runtime environment information.",
    )
    ver_parser.set_defaults(func=_handle_version)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entry point for OpenDataGuard.

    Args:
        argv: Optional command-line arguments sequence. Defaults to sys.argv[1:].

    Returns:
        Exit code (0: Success, 1: Quality/Reconciliation Failure, 2: Runtime/Config Error).
    """
    parser = build_parser()

    # If no arguments provided, show help and exit cleanly with 0
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        parser.print_help()
        return 0

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        return handler(args)
    except Exception as exc:
        logger.error("Unhandled CLI exception: %s", exc, exc_info=True)
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
