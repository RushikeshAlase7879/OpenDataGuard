# Installation & Setup Guide

This guide walks you through setting up **OpenDataGuard** for terminal CLI usage, pipeline integration, local development, or interactive web dashboard exploration.

---

## 1. System Requirements

- **Python**: 3.9, 3.10, 3.11, or 3.12 (verified across Ubuntu and Windows in continuous integration)
- **Operating System**: Windows 10/11, macOS, or Linux
- **Disk Space**: ~200 MB for Python environment and dependencies
- **RAM**: Minimum 2 GB (4 GB recommended for larger datasets)

---

## 2. Installation Options

### Option A: Install from PyPI (Recommended for CLI & Pipelines)

For data engineers, analysts, and automated pipelines who need the embeddable Python library and native `opendataguard` CLI:

```bash
# 1. Create and activate a virtual environment
# Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# 2. Install OpenDataGuard from PyPI
pip install --upgrade pip
pip install opendataguard
```

This registers the `opendataguard` binary command in your environment's PATH.

---

### Option B: Clone from GitHub (For Development & Contributing)

For contributors extending OpenDataGuard or running the test suite locally:

```bash
# 1. Clone the repository
git clone https://github.com/RushikeshAlase7879/OpenDataGuard.git
cd OpenDataGuard

# 2. Create and activate a virtual environment
# Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies in editable mode
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

# Optional: Install development & testing tools
pip install -e ".[dev]"
```

---

## 3. Optional PostgreSQL Driver

If you plan to inspect PostgreSQL databases, install the optional PostgreSQL binary driver:

```bash
pip install "psycopg2-binary>=2.9.9"
# Or via optional dependencies:
pip install -e ".[postgres]"
```

---

## 4. Verify Installation

### 1. Verify the Command-Line Interface (CLI)
Verify that the native CLI is registered and functional:

```bash
opendataguard --version
opendataguard --help
```

You should see `OpenDataGuard 1.1.0` and the list of available subcommands (`validate`, `reconcile`, `ui`, `version`).

### 2. Run the Automated Test Suite (Repository Checkouts)
When working within a cloned repository checkout, execute the automated test runner:

```bash
python scripts/run_tests.py
```

You should see all **115 test cases** pass across CLI, unit, integration, and UI modules.

---

## 5. Launch the Streamlit Web Application

OpenDataGuard provides two ways to start the interactive web application:

### Recommended: Via Native CLI Entry Point
For both PyPI installations and repository checkouts:

```bash
opendataguard ui
```

To run in headless mode on a custom port:

```bash
opendataguard ui --port 8501 --no-browser
```

### Alternative: Direct Streamlit Runner
From the root directory of a cloned repository checkout:

```bash
streamlit run app.py
```

> **Note**: `streamlit run app.py` requires `app.py` to be present in the active working directory. For standalone Python environments where OpenDataGuard was installed via `pip install opendataguard`, always use `opendataguard ui`.

By default, the application opens in your browser at `http://localhost:8501`.
