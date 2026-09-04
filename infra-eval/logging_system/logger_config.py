"""
Logger configuration module.

Provides a Pydantic-backed configuration model for the activity logging
system and a ``setup_logging`` entrypoint that configures console, file,
and rotating-file handlers for the standard :mod:`logging` module.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Set

from pydantic import BaseModel, Field, field_validator

from .log_formatter import JSONFormatter

#: All log levels supported by the activity logging system.
LOG_LEVELS: Set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class LoggingConfig(BaseModel):
    """
    Configuration for the activity logging system.

    Attributes:
        log_level: Root log level name.
        json_format: Emit JSON-formatted records when ``True``.
        console_enabled: Attach a console handler.
        file_enabled: Attach a file handler.
        file_path: Path of the log file (used for file handler and rotation).
        max_bytes: Maximum size (bytes) of a single log file before rotation.
        backup_count: Number of rotated log files to retain.
        root_logger_name: Root logger name under which handlers are attached.
    """

    log_level: str = Field(default="INFO")
    json_format: bool = Field(default=True)
    console_enabled: bool = Field(default=True)
    file_enabled: bool = Field(default=False)
    file_path: str = Field(default="logs/activity.log")
    max_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    backup_count: int = Field(default=3, ge=0)
    root_logger_name: str = Field(default="infra-eval")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Ensure the log level is one of the supported values."""
        normalized = value.upper()
        if normalized not in LOG_LEVELS:
            raise ValueError(
                f"Invalid log level '{value}'. Must be one of {sorted(LOG_LEVELS)}"
            )
        return normalized

    def get_level(self) -> int:
        """Return the numeric logging level."""
        return getattr(logging, self.log_level)

    def get_file_path(self) -> Path:
        """Return the log file path with parent directories created."""
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class ActivityLoggerManager:
    """
    Manages handlers for a named logger.

    This is a small helper that keeps a registry of configured loggers so
    ``setup_logging`` can be re-invoked idempotently without duplicating
    handlers on subsequent calls.
    """

    _configured_loggers: Set[str] = set()

    @classmethod
    def mark_configured(cls, name: str) -> None:
        """Record a logger as already configured."""
        cls._configured_loggers.add(name)

    @classmethod
    def is_configured(cls, name: str) -> bool:
        """Check whether a logger has already been configured."""
        return name in cls._configured_loggers

    @classmethod
    def reset(cls) -> None:
        """Clear the registry (mainly useful in tests)."""
        cls._configured_loggers.clear()


def _build_console_handler(config: LoggingConfig) -> logging.Handler:
    """Build a stream handler writing to stderr."""
    handler = logging.StreamHandler(stream=sys.stderr)
    if config.json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    return handler


def _build_file_handler(config: LoggingConfig) -> logging.Handler:
    """
    Build a rotating file handler.

    Rotates when the file reaches ``max_bytes`` and retains
    ``backup_count`` rotated files.
    """
    file_path = config.get_file_path()
    handler = RotatingFileHandler(
        filename=str(file_path),
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    if config.json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    return handler


def setup_logging(config: Optional[LoggingConfig] = None) -> logging.Logger:
    """
    Configure the root ``infra-eval`` logger with console and/or file handlers.

    The configuration is idempotent: calling this function multiple times
    with the same logger name does not duplicate handlers.

    Args:
        config: Optional :class:`LoggingConfig`. Defaults are used when
            omitted.

    Returns:
        The configured root logger instance.
    """
    cfg = config or LoggingConfig()
    logger_name = cfg.root_logger_name
    logger = logging.getLogger(logger_name)

    if ActivityLoggerManager.is_configured(logger_name):
        return logger

    logger.setLevel(cfg.get_level())
    logger.propagate = False

    if cfg.console_enabled:
        logger.addHandler(_build_console_handler(cfg))

    if cfg.file_enabled:
        logger.addHandler(_build_file_handler(cfg))

    ActivityLoggerManager.mark_configured(logger_name)
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the ``infra-eval`` root logger.

    Args:
        name: Sub-module name (e.g. ``"logging_system"``).

    Returns:
        A logger instance with the fully qualified ``infra-eval.<name>`` name.
    """
    return logging.getLogger(f"infra-eval.{name}")
