"""Logging configuration for OpenDataGuard.

Ensures structured, secure, and configurable logging across all components.
Masks credentials and sensitive patterns to prevent accidental leaks.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Optional

# Regex pattern to identify potential connection string passwords or secret tokens
_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|key|api_key)([\"']?\s*[:=]\s*[\"']?)([^\"'\s;,]+)",
)
_URI_PASSWORD_PATTERN = re.compile(
    r"(://[^:]+:)([^@]+)(@)",
)


class SafeFormatter(logging.Formatter):
    """Logging formatter that automatically masks credentials and sensitive values."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        # Mask URI credentials: e.g., postgresql://user:secret@host -> postgresql://user:***@host
        sanitized = _URI_PASSWORD_PATTERN.sub(r"\1***\3", original)
        # Mask key-value credentials: e.g., password=secret123 -> password=***
        sanitized = _SECRET_PATTERN.sub(r"\1\2***", sanitized)
        return sanitized


def setup_logger(
    name: str = "opendataguard",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Configure and return a standardized OpenDataGuard logger.

    Args:
        name: Logger name, defaults to 'opendataguard'.
        level: Logging level (e.g. logging.INFO, logging.DEBUG).
        log_file: Optional file path to write log output.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logger is invoked multiple times
    if not logger.handlers:
        formatter = SafeFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Standard console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Optional file handler
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except OSError as err:
                logger.warning("Could not attach file handler at %s: %s", log_file, err)

    return logger


# Default module logger
logger = setup_logger()
