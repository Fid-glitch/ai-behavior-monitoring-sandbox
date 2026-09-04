"""
Backward-compatible alias for the activity logging system.

This module re-exports the canonical public API from
:mod:`logging_system.activity_logger` and :mod:`logging_system.logger_config`
so existing imports such as ``from logging_system.logger import setup_logging``
keep working. New code should import directly from
:mod:`logging_system.activity_logger` or :mod:`logging_system`.
"""

from __future__ import annotations

from .activity_logger import (
    ActivityLogger,
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
from .log_formatter import CSVExporter, JSONFormatter
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
    "JSONFormatter",
    "LogBatch",
    "LogData",
    "LogDecision",
    "LogEntry",
    "LogEventType",
    "LogLevel",
    "LoggingConfig",
    "create_activity_logger",
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

