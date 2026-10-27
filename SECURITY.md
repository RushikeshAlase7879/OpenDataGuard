# Security Policy for OpenDataGuard

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Philosophy & Architecture

OpenDataGuard is designed with security, privacy, and non-destructive execution as first principles:
- **Local In-Memory Execution**: Files uploaded into the platform are processed exclusively in your local Python runtime. No dataset contents or row records are transferred to external cloud endpoints or telemetry collectors.
- **Credential Protection**: Database passwords and connection URI secrets are masked via `SafeFormatter` and are never written to disk, output streams, or historical audit tables.
- **SQL Injection Prevention**: SQL operations strictly prohibit raw, arbitrary user SQL strings. All queries utilize SQLAlchemy table reflection, parameterized statements, and catalog identifier verification.
- **Untrusted File Safeguards**: Uploaded files undergo file size validation (default 100MB threshold), extension checks, and safe encoding fallbacks. No macros or embedded scripts are executed.

## Reporting a Vulnerability

If you discover a potential security vulnerability within OpenDataGuard, please do **NOT** open a public GitHub issue.

Instead, please send a responsible disclosure email to the project maintainers with:
1. Description of the vulnerability.
2. Step-by-step instructions or proof-of-concept demonstrating the issue.
3. Potential impact on local environments or data confidentiality.

Maintainers will acknowledge receipt within 48 hours and coordinate a coordinated disclosure timeline and fix.

*Note: As an open-source project, OpenDataGuard does not claim an external formal security audit has been completed.*
