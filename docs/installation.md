# Installation & Setup Guide

This guide walks you through setting up **OpenDataGuard** locally for development, pipeline testing, or interactive use.

---

## 1. System Requirements

- **Python**: 3.10, 3.11, or 3.12 (verified compatible)
- **Operating System**: Windows 10/11, macOS, or Linux
- **Disk Space**: ~200 MB for Python environment and dependencies
- **RAM**: Minimum 2 GB (4 GB recommended for larger datasets)

---

## 2. Quickstart Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/<your-username>/OpenDataGuard.git
cd OpenDataGuard
```

### Step 2: Create a Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### On Linux or macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Install OpenDataGuard in Editable Mode
```bash
pip install -e .
```

---

## 3. Optional PostgreSQL Driver

If you plan to validate PostgreSQL tables, install the optional PostgreSQL binary driver:
```bash
pip install psycopg2-binary>=2.9.9
# Or via optional dependencies:
pip install -e .[postgres]
```

---

## 4. Verify Installation

Run the automated test runner:
```bash
python scripts/run_tests.py
```
You should see all 41 test cases pass.

---

## 5. Launch the Streamlit Web Application

To launch the interactive dashboard:
```bash
streamlit run app.py
```
By default, the application will open at: `http://localhost:8501`.
