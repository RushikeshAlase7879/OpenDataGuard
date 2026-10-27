# Contributing to OpenDataGuard

Thank you for your interest in contributing to **OpenDataGuard**! As an open-source platform, we welcome genuine contributions from data engineers, software developers, analysts, and QA practitioners.

Please take a moment to review this guide before submitting issues or pull requests.

---

## 1. Ground Rules & Code of Conduct

- All contributors are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).
- GitHub issues, discussions, and pull requests must represent genuine work by real contributors.
- Do not submit low-effort AI-generated spam, automated vanity PRs, or unsolicited dependency bumps without testing.

---

## 2. Reporting Bugs & Proposing Features

### Bug Reports
When reporting a bug, include:
1. Operating system and Python version.
2. Steps to reproduce the issue.
3. Expected vs. actual behavior.
4. Minimal reproducible example dataset (synthetic only, never real PII).
5. Relevant traceback or sanitized log snippet.

### Feature Requests
Feature suggestions should explain:
1. The user problem being solved.
2. Proposed design or API ergonomics.
3. Whether it impacts core validation, reconciliation, or the web dashboard.

---

## 3. Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/<your-username>/OpenDataGuard.git
   cd OpenDataGuard
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # On Linux/macOS:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. Install dependencies in editable mode:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. Run the test suite:
   ```bash
   python scripts/run_tests.py
   # Or directly:
   pytest tests/ -v
   ```

---

## 4. Coding Standards

- **Type Hints**: Add type annotations to all public functions and methods.
- **Documentation**: Provide clear, Google-style or Sphinx-style docstrings.
- **Security**: Never log raw credentials or tokens. Always use `opendataguard.logging_config.logger`.
- **Memory & Performance**: Avoid redundant DataFrame copies; use generator/chunked processing where applicable.
- **Test Coverage**: Every new check or feature must have corresponding unit tests in `tests/`.

---

## 5. Pull Request Workflow

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/new-validator-rule
   ```
2. Implement your changes with accompanying tests.
3. Ensure all tests pass:
   ```bash
   pytest tests/ -v
   ```
4. Commit your changes with clear, semantic commit messages:
   ```bash
   git commit -m "feat(validators): add regex pattern validation check"
   ```
5. Push to your fork and submit a Pull Request against `main`.
