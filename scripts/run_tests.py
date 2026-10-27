"""Test execution runner script for OpenDataGuard."""

import os
import sys
from pathlib import Path
import pytest


def main() -> int:
    """Configure environment and execute OpenDataGuard test suite."""
    project_root = Path(__file__).parent.parent.resolve()
    src_dir = project_root / "src"
    tests_dir = project_root / "tests"

    # Ensure src is in sys.path
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    os.environ["PYTHONPATH"] = str(src_dir)

    print(f"Running OpenDataGuard test suite from: {tests_dir}")
    print(f"Source path: {src_dir}")

    # Run pytest
    exit_code = pytest.main([
        str(tests_dir),
        "-v",
        "--tb=short",
    ])

    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
