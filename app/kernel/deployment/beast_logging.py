"""Structured Logging for BEAST.

Uses standard library logging with JSON formatter for structured output.
Adds correlation IDs to all log records when available.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for correlation ID (propagates across async/sync code)
correlation_id_var: ContextVar[Optional[str]] = ContextVar("beast_correlation_id", default=None)


def get_correlation_id() -> str:
    """Get or create a correlation ID for the current context."""
    cid = correlation_id_var.get()
    if cid is None:
        cid = f"beast_{uuid.uuid4().hex[:12]}"
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    correlation_id_var.set(cid)


class JsonFormatter(logging.Formatter):
    """JSON log formatter with BEAST-specific fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields passed via extra={}
        for key, value in record.__dict__.items():
            if key not in (
                "args", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module",
                "msecs", "message", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread",
                "threadName",
            ):
                log_data[key] = value

        return json.dumps(log_data, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO, stream=None) -> None:
    """Configure root logger with JSON formatting for BEAST."""
    if stream is None:
        stream = sys.stdout

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    # Remove existing handlers to avoid duplicate logs
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# Convenience logger for modules that don't want to configure
logger = logging.getLogger("beast")

# Auto-configure on import if not already configured
if not logging.getLogger().handlers:
    configure_logging()