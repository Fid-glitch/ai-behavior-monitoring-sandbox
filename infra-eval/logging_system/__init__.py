"""
Activity Logging System.

Structured, thread-safe logging for the Secure Autonomous AI Behavior
Monitoring Sandbox. Records requests, responses, security events, container
events, performance metrics, and errors in JSON format with optional CSV
export.

Public API:
    - Logging functions: ``log_request``, ``log_response``,
      ``log_security_event``, ``log_container_event``, ``log_performance``,
      ``log_error``, ``log_system_event``.
    - :class:`ActivityLogger` for instance-based logging.
    - :class:`LogEntry` Pydantic-style model and enums
      (:class:`LogDecision`, :class:`LogLevel`, :class:`LogEventType`).
    - :class:`CSVExporter` and :func:`setup_logging`.
"""

from __future__ import annotations

from .activity_logger import (
    ActivityLogger,
    JSONLogFormatter,
    CsvExporter,
    create_activity_logger,
    log_container_event,
    log_error,
    log_performance,
    log_request,
    log_response,
    log_security_event,
    log_system_event,
    logger,
    timed,
)
from .log_formatter import (
    CSVExporter,
    DEFAULT_CSV_FIELDS,
    JSONFormatter,
    create_csv_exporter,
)
from .log_models import (
    LogBatch,
    LogData,
    LogDecision,
    LogEntry,
    LogEventType,
    LogLevel,
)
from .logger_config import (
    ActivityLoggerManager,
    LoggingConfig,
    get_logger,
    setup_logging,
)

__all__ = [
    "ActivityLogger",
    "ActivityLoggerManager",
    "CSVExporter",
    "CsvExporter",
    "DEFAULT_CSV_FIELDS",
    "JSONFormatter",
    "JSONLogFormatter",
    "LogBatch",
    "LogData",
    "LogDecision",
    "LogEntry",
    "LogEventType",
    "LogLevel",
    "LoggingConfig",
    "create_activity_logger",
    "create_csv_exporter",
    "get_logger",
    "log_container_event",
    "log_error",
    "log_performance",
    "log_request",
    "log_response",
    "log_security_event",
    "log_system_event",
    "logger",
    "setup_logging",
    "timed",
]

__version__ = "0.1.0"

