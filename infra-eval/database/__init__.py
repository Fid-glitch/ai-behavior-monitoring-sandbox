"""
SQLite Database Layer.

Provides a thread-safe SQLite store for activity logs, security events,
and performance/evaluation records. Built on Python's built-in ``sqlite3``
module and fully compatible with the :mod:`logging_system.LogEntry` model.

Public API:
    - :class:`Database`: main entrypoint for all database operations.
    - :func:`parse_database_url`: convert ``sqlite:///`` URLs to paths.
    - Exceptions: :class:`DatabaseError`, :class:`DatabaseConnectionError`,
      :class:`InvalidRecordError`, :class:`ConstraintViolationError`.
"""

from __future__ import annotations

from .db import (
    ConstraintViolationError,
    Database,
    DatabaseConnectionError,
    DatabaseError,
    InvalidRecordError,
    parse_database_url,
)

__all__ = [
    "ConstraintViolationError",
    "Database",
    "DatabaseConnectionError",
    "DatabaseError",
    "InvalidRecordError",
    "parse_database_url",
]

__version__ = "0.1.0"