"""
SQLite database layer for the infrastructure and activity logging system.

Provides a thread-safe :class:`Database` built on Python's built-in
``sqlite3`` module. The layer stores:

- Activity log records compatible with :class:`logging_system.LogEntry`.
- Security events (severity, risk scores, decisions).
- Performance / evaluation records for later Member 4 stages.

All SQL uses parameterised queries to avoid SQL injection risks.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from logging_system.log_models import (
    LogDecision,
    LogEntry,
    LogEventType,
    LogLevel,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DatabaseError(RuntimeError):
    """Base exception for all database-layer failures."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection cannot be established."""


class InvalidRecordError(DatabaseError):
    """Raised when a record is missing required fields or has invalid values."""


class ConstraintViolationError(DatabaseError):
    """Raised when an insert/update violates a database constraint."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    """Return the underlying value of an enum, or the value itself."""
    return value.value if isinstance(value, Enum) else value


def _json_dumps(value: Any) -> str:
    """Serialise a value to a JSON string."""
    return json.dumps(value, default=str)


def _json_loads(value: Optional[str]) -> Any:
    """Deserialise a JSON string, returning ``None`` for empty input."""
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def parse_database_url(url: str) -> str:
    """
    Convert a ``sqlite:///`` URL to a plain filesystem path.

    Args:
        url: Database URL (e.g. ``"sqlite:///./data/sandbox.db"``).

    Returns:
        A plain path string suitable for :func:`sqlite3.connect`.

    Raises:
        ValueError: If the URL is not a SQLite URL.
    """
    if url == "sqlite:///:memory:":
        return ":memory:"
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///") :]
    raise ValueError(f"Unsupported database URL: {url!r}")


def _validate_log_level(level: str) -> str:
    """Validate a log level string and return it in upper case."""
    normalized = level.upper()
    if normalized not in {lv.value for lv in LogLevel}:
        raise InvalidRecordError(f"Invalid log level: {level!r}")
    return normalized


def _validate_event_type(event_type: str) -> str:
    """Validate an event type string and return it in lower case."""
    normalized = event_type.lower()
    if normalized not in {et.value for et in LogEventType}:
        raise InvalidRecordError(f"Invalid event type: {event_type!r}")
    return normalized


def _validate_decision(decision: Optional[str]) -> Optional[str]:
    """Validate a decision string, returning ``None`` when absent."""
    if decision is None:
        return None
    normalized = decision.upper()
    if normalized not in {d.value for d in LogDecision}:
        raise InvalidRecordError(f"Invalid decision: {decision!r}")
    return normalized


def _validate_severity(severity: str) -> str:
    """Validate a security severity string and return it in upper case."""
    normalized = severity.upper()
    if normalized not in {lv.value for lv in LogLevel}:
        raise InvalidRecordError(f"Invalid severity: {severity!r}")
    return normalized


def _default_message(data: Dict[str, Any], event_type: str) -> str:
    """
    Derive a human-readable message from a log record dictionary.

    Args:
        data: Log record fields.
        event_type: Normalised event type.

    Returns:
        A human-readable message string.
    """
    if event_type == LogEventType.REQUEST.value:
        prompt = data.get("user_prompt") or ""
        return f"Request received: {prompt[:200]!r}"
    if event_type == LogEventType.RESPONSE.value:
        return "Response generated"
    if event_type == LogEventType.SECURITY.value:
        decision = data.get("decision") or "UNKNOWN"
        risk = data.get("risk_score")
        risk_str = f"{risk:.2f}" if isinstance(risk, (int, float)) else "N/A"
        return f"Security event decision={decision} risk={risk_str}"
    if event_type == LogEventType.CONTAINER.value:
        return f"Container event: {data.get('status') or data.get('container_id') or 'unknown'}"
    if event_type == LogEventType.PERFORMANCE.value:
        return "Performance metrics recorded"
    if event_type == LogEventType.ERROR.value:
        return f"Error: {data.get('error_message') or 'unknown error'}"
    return "System event"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    user_prompt TEXT,
    sanitized_prompt TEXT,
    ai_response TEXT,
    tool_used TEXT,
    container_id TEXT,
    status TEXT,
    error_message TEXT,
    traceback TEXT,
    execution_time_ms REAL,
    cpu_usage_percent REAL,
    memory_usage_mb REAL,
    risk_score REAL,
    decision TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp
    ON activity_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_logs_event_type
    ON activity_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_logs_container_id
    ON activity_logs(container_id);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    risk_score REAL,
    decision TEXT,
    user_prompt TEXT,
    sanitized_prompt TEXT,
    ai_response TEXT,
    tool_used TEXT,
    container_id TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_security_events_timestamp
    ON security_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_security_events_severity
    ON security_events(severity);
CREATE INDEX IF NOT EXISTS idx_security_events_decision
    ON security_events(decision);

CREATE TABLE IF NOT EXISTS performance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    benchmark_name TEXT,
    execution_time_ms REAL,
    cpu_usage_percent REAL,
    memory_usage_mb REAL,
    latency_ms REAL,
    container_id TEXT,
    tool_used TEXT,
    result REAL,
    evaluation_score REAL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_performance_records_timestamp
    ON performance_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_performance_records_benchmark
    ON performance_records(benchmark_name);
CREATE INDEX IF NOT EXISTS idx_performance_records_container_id
    ON performance_records(container_id);
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """
    Thread-safe SQLite database for activity logs, security events, and
    performance/evaluation records.

    Args:
        db_path: Filesystem path, ``sqlite:///`` URL, or ``":memory:"``
            for an in-memory database (mainly for tests).
        timeout: Connection timeout in seconds (default 30).
    """

    def __init__(self, db_path: Union[str, Path], timeout: float = 30.0) -> None:
        self.db_path = str(db_path)
        if self.db_path.startswith("sqlite:///"):
            self.db_path = parse_database_url(self.db_path)
        self.timeout = timeout
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection (or return the cached one)."""
        if self._conn is not None:
            return self._conn
        try:
            if self.db_path != ":memory:":
                path = Path(self.db_path)
                if path.exists() and path.is_dir():
                    raise DatabaseConnectionError(
                        f"Database path is a directory: {self.db_path}"
                    )
                path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._conn = conn
            return conn
        except sqlite3.Error as exc:
            raise DatabaseConnectionError(
                f"Failed to connect to SQLite database at {self.db_path!r}: {exc}"
            ) from exc

    def initialize(self) -> None:
        """
        Create the database tables if they do not already exist.

        Raises:
            DatabaseError: If the schema cannot be created.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Failed to initialise database schema: {exc}"
                ) from exc

    def close(self) -> None:
        """Close the underlying connection safely."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    def table_names(self) -> List[str]:
        """
        Return the names of all user tables in the database.

        Returns:
            A list of table names.
        """
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
                return [r["name"] for r in rows]
            except sqlite3.Error as exc:
                raise DatabaseError(f"Failed to list tables: {exc}") from exc

    def __enter__(self) -> "Database":
        """Context-manager entry: initialise the schema and return self."""
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context-manager exit: close the connection."""
        self.close()

    # ------------------------------------------------------------------
    # Activity logs
    # ------------------------------------------------------------------

    def insert_activity_log(
        self,
        entry: Union[LogEntry, Dict[str, Any]],
        message: Optional[str] = None,
    ) -> int:
        """
        Insert an activity log record.

        Args:
            entry: A :class:`LogEntry` instance or a dictionary of fields.
            message: Optional human-readable message. When omitted, a
                message is derived from the entry fields.

        Returns:
            The new record ID.

        Raises:
            InvalidRecordError: If the record is missing required fields.
            ConstraintViolationError: If the insert violates a constraint.
            DatabaseError: On any other database failure.
        """
        with self._lock:
            self.initialize()
            conn = self._connect()
            data = entry.to_dict() if isinstance(entry, LogEntry) else dict(entry)
            timestamp = str(data.get("timestamp") or _now_iso())
            level = _validate_log_level(str(_enum_value(data.get("level", "INFO"))))
            event_type = _validate_event_type(
                str(_enum_value(data.get("event_type", "system")))
            )
            decision = _validate_decision(
                str(_enum_value(data["decision"]))
                if data.get("decision") is not None
                else None
            )
            metadata = data.get("extra") or {}
            if not isinstance(metadata, dict):
                raise InvalidRecordError("'extra' metadata must be a dictionary")
            msg = message or _default_message(data, event_type)
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO activity_logs (
                        timestamp, level, event_type, message,
                        user_prompt, sanitized_prompt, ai_response, tool_used,
                        container_id, status, error_message, traceback,
                        execution_time_ms, cpu_usage_percent, memory_usage_mb,
                        risk_score, decision, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        level,
                        event_type,
                        msg,
                        data.get("user_prompt"),
                        data.get("sanitized_prompt"),
                        data.get("ai_response"),
                        data.get("tool_used"),
                        data.get("container_id"),
                        data.get("status"),
                        data.get("error_message"),
                        data.get("traceback"),
                        data.get("execution_time_ms"),
                        data.get("cpu_usage_percent"),
                        data.get("memory_usage_mb"),
                        data.get("risk_score"),
                        decision,
                        _json_dumps(metadata),
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ConstraintViolationError(
                    f"Constraint violation while inserting activity log: {exc}"
                ) from exc
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Failed to insert activity log: {exc}"
                ) from exc

    def insert_activity_logs(
        self,
        entries: List[Union[LogEntry, Dict[str, Any]]],
    ) -> List[int]:
        """
        Insert multiple activity log records in a single transaction.

        Args:
            entries: List of :class:`LogEntry` instances or dictionaries.

        Returns:
            A list of the new record IDs in insertion order.

        Raises:
            InvalidRecordError: If any record is invalid.
            DatabaseError: On any database failure.
        """
        with self._lock:
            conn = self._connect()
            ids: List[int] = []
            try:
                for entry in entries:
                    data = (
                        entry.to_dict()
                        if isinstance(entry, LogEntry)
                        else dict(entry)
                    )
                    timestamp = str(data.get("timestamp") or _now_iso())
                    level = _validate_log_level(
                        str(_enum_value(data.get("level", "INFO")))
                    )
                    event_type = _validate_event_type(
                        str(_enum_value(data.get("event_type", "system")))
                    )
                    decision = _validate_decision(
                        str(_enum_value(data["decision"]))
                        if data.get("decision") is not None
                        else None
                    )
                    metadata = data.get("extra") or {}
                    if not isinstance(metadata, dict):
                        raise InvalidRecordError(
                            "'extra' metadata must be a dictionary"
                        )
                    msg = _default_message(data, event_type)
                    cursor = conn.execute(
                        """
                        INSERT INTO activity_logs (
                            timestamp, level, event_type, message,
                            user_prompt, sanitized_prompt, ai_response, tool_used,
                            container_id, status, error_message, traceback,
                            execution_time_ms, cpu_usage_percent, memory_usage_mb,
                            risk_score, decision, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            timestamp,
                            level,
                            event_type,
                            msg,
                            data.get("user_prompt"),
                            data.get("sanitized_prompt"),
                            data.get("ai_response"),
                            data.get("tool_used"),
                            data.get("container_id"),
                            data.get("status"),
                            data.get("error_message"),
                            data.get("traceback"),
                            data.get("execution_time_ms"),
                            data.get("cpu_usage_percent"),
                            data.get("memory_usage_mb"),
                            data.get("risk_score"),
                            decision,
                            _json_dumps(metadata),
                        ),
                    )
                    ids.append(int(cursor.lastrowid))
                conn.commit()
                return ids
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ConstraintViolationError(
                    f"Constraint violation while inserting activity logs: {exc}"
                ) from exc
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Failed to insert activity logs: {exc}"
                ) from exc

    def get_activity_log(self, log_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single activity log record by ID.

        Args:
            log_id: The record ID.

        Returns:
            A dictionary of the record, or ``None`` if not found.
        """
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM activity_logs WHERE id = ?", (log_id,)
                ).fetchone()
                return self._row_to_dict(row) if row is not None else None
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to retrieve activity log {log_id}: {exc}"
                ) from exc

    def query_activity_logs(
        self,
        *,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        container_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query activity log records with optional filters.

        Args:
            event_type: Filter by event type (e.g. ``"security"``).
            level: Filter by log level (e.g. ``"ERROR"``).
            container_id: Filter by container ID.
            start_time: Inclusive lower bound on the timestamp.
            end_time: Inclusive upper bound on the timestamp.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            A list of record dictionaries ordered newest-first.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(_validate_event_type(event_type))
        if level is not None:
            clauses.append("level = ?")
            params.append(_validate_log_level(level))
        if container_id is not None:
            clauses.append("container_id = ?")
            params.append(container_id)
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM activity_logs {where} "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to query activity logs: {exc}"
                ) from exc

    def count_activity_logs(
        self,
        *,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        container_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        """
        Count activity log records matching the given filters.

        Args:
            event_type: Filter by event type.
            level: Filter by log level.
            container_id: Filter by container ID.
            start_time: Inclusive lower bound on the timestamp.
            end_time: Inclusive upper bound on the timestamp.

        Returns:
            The number of matching records.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(_validate_event_type(event_type))
        if level is not None:
            clauses.append("level = ?")
            params.append(_validate_log_level(level))
        if container_id is not None:
            clauses.append("container_id = ?")
            params.append(container_id)
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT COUNT(*) AS n FROM activity_logs {where}"
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(sql, params).fetchone()
                return int(row["n"])
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to count activity logs: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Security events
    # ------------------------------------------------------------------

    def insert_security_event(
        self,
        *,
        event_type: str = "security",
        severity: str = "INFO",
        risk_score: Optional[float] = None,
        decision: Optional[str] = None,
        timestamp: Optional[str] = None,
        user_prompt: Optional[str] = None,
        sanitized_prompt: Optional[str] = None,
        ai_response: Optional[str] = None,
        tool_used: Optional[str] = None,
        container_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Insert a security event record.

        Args:
            event_type: Event type (default ``"security"``).
            severity: Severity level (one of DEBUG/INFO/WARNING/ERROR/CRITICAL).
            risk_score: Optional risk score in ``[0, 1]``.
            decision: Optional decision (ALLOW / BLOCK / WARNING).
            timestamp: Optional ISO timestamp (defaults to now).
            user_prompt: Optional original user prompt.
            sanitized_prompt: Optional sanitised prompt.
            ai_response: Optional AI response.
            tool_used: Optional tool used.
            container_id: Optional container identifier.
            metadata: Optional structured metadata dictionary.

        Returns:
            The new record ID.

        Raises:
            InvalidRecordError: If required fields are invalid.
            ConstraintViolationError: If the insert violates a constraint.
            DatabaseError: On any other database failure.
        """
        with self._lock:
            conn = self._connect()
            ts = timestamp or _now_iso()
            evt = _validate_event_type(event_type)
            sev = _validate_severity(severity)
            dec = _validate_decision(decision)
            meta = metadata or {}
            if not isinstance(meta, dict):
                raise InvalidRecordError("'metadata' must be a dictionary")
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO security_events (
                        timestamp, event_type, severity, risk_score, decision,
                        user_prompt, sanitized_prompt, ai_response, tool_used,
                        container_id, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        evt,
                        sev,
                        risk_score,
                        dec,
                        user_prompt,
                        sanitized_prompt,
                        ai_response,
                        tool_used,
                        container_id,
                        _json_dumps(meta),
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ConstraintViolationError(
                    f"Constraint violation while inserting security event: {exc}"
                ) from exc
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Failed to insert security event: {exc}"
                ) from exc

    def get_security_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single security event by ID.

        Args:
            event_id: The record ID.

        Returns:
            A dictionary of the record, or ``None`` if not found.
        """
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM security_events WHERE id = ?", (event_id,)
                ).fetchone()
                return self._row_to_dict(row) if row is not None else None
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to retrieve security event {event_id}: {exc}"
                ) from exc

    def query_security_events(
        self,
        *,
        severity: Optional[str] = None,
        decision: Optional[str] = None,
        container_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query security events with optional filters.

        Args:
            severity: Filter by severity level.
            decision: Filter by decision (ALLOW / BLOCK / WARNING).
            container_id: Filter by container ID.
            start_time: Inclusive lower bound on the timestamp.
            end_time: Inclusive upper bound on the timestamp.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            A list of record dictionaries ordered newest-first.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if severity is not None:
            clauses.append("severity = ?")
            params.append(_validate_severity(severity))
        if decision is not None:
            clauses.append("decision = ?")
            params.append(_validate_decision(decision))
        if container_id is not None:
            clauses.append("container_id = ?")
            params.append(container_id)
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM security_events {where} "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to query security events: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Performance / evaluation records
    # ------------------------------------------------------------------

    def insert_performance_record(
        self,
        *,
        benchmark_name: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_mb: Optional[float] = None,
        latency_ms: Optional[float] = None,
        container_id: Optional[str] = None,
        tool_used: Optional[str] = None,
        result: Optional[float] = None,
        evaluation_score: Optional[float] = None,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Insert a performance / evaluation record.

        The schema is intentionally extensible for later Member 4 stages
        (benchmarks, evaluation scores, latency, resource usage).

        Args:
            benchmark_name: Optional benchmark identifier.
            execution_time_ms: Execution time in milliseconds.
            cpu_usage_percent: CPU usage percentage.
            memory_usage_mb: Memory usage in megabytes.
            latency_ms: Latency in milliseconds.
            container_id: Optional container identifier.
            tool_used: Optional tool that was measured.
            result: Optional numeric benchmark result.
            evaluation_score: Optional evaluation score.
            timestamp: Optional ISO timestamp (defaults to now).
            metadata: Optional structured metadata dictionary.

        Returns:
            The new record ID.

        Raises:
            InvalidRecordError: If required fields are invalid.
            ConstraintViolationError: If the insert violates a constraint.
            DatabaseError: On any other database failure.
        """
        with self._lock:
            conn = self._connect()
            ts = timestamp or _now_iso()
            meta = metadata or {}
            if not isinstance(meta, dict):
                raise InvalidRecordError("'metadata' must be a dictionary")
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO performance_records (
                        timestamp, benchmark_name, execution_time_ms,
                        cpu_usage_percent, memory_usage_mb, latency_ms,
                        container_id, tool_used, result, evaluation_score,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        benchmark_name,
                        execution_time_ms,
                        cpu_usage_percent,
                        memory_usage_mb,
                        latency_ms,
                        container_id,
                        tool_used,
                        result,
                        evaluation_score,
                        _json_dumps(meta),
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ConstraintViolationError(
                    f"Constraint violation while inserting performance record: {exc}"
                ) from exc
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Failed to insert performance record: {exc}"
                ) from exc

    def get_performance_record(self, record_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single performance record by ID.

        Args:
            record_id: The record ID.

        Returns:
            A dictionary of the record, or ``None`` if not found.
        """
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM performance_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
                return self._row_to_dict(row) if row is not None else None
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to retrieve performance record {record_id}: {exc}"
                ) from exc

    def query_performance_records(
        self,
        *,
        benchmark_name: Optional[str] = None,
        container_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query performance / evaluation records with optional filters.

        Args:
            benchmark_name: Filter by benchmark name.
            container_id: Filter by container ID.
            start_time: Inclusive lower bound on the timestamp.
            end_time: Inclusive upper bound on the timestamp.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            A list of record dictionaries ordered newest-first.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if benchmark_name is not None:
            clauses.append("benchmark_name = ?")
            params.append(benchmark_name)
        if container_id is not None:
            clauses.append("container_id = ?")
            params.append(container_id)
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM performance_records {where} "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Failed to query performance records: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def insert_log_entry(
        self,
        entry: Union[LogEntry, Dict[str, Any]],
        message: Optional[str] = None,
    ) -> int:
        """
        Insert a :class:`LogEntry` into the activity log table.

        When the entry's event type is ``security`` or ``performance`` the
        record is also stored in the corresponding dedicated table so the
        specialised query methods can find it.

        Args:
            entry: A :class:`LogEntry` instance or a dictionary of fields.
            message: Optional human-readable message.

        Returns:
            The activity log record ID.
        """
        log_id = self.insert_activity_log(entry, message=message)
        data = entry.to_dict() if isinstance(entry, LogEntry) else dict(entry)
        event_type = _validate_event_type(
            str(_enum_value(data.get("event_type", "system")))
        )
        if event_type == LogEventType.SECURITY.value:
            self.insert_security_event(
                event_type=event_type,
                severity=str(_enum_value(data.get("level", "INFO"))),
                risk_score=data.get("risk_score"),
                decision=(
                    str(_enum_value(data["decision"]))
                    if data.get("decision") is not None
                    else None
                ),
                timestamp=str(data.get("timestamp") or _now_iso()),
                user_prompt=data.get("user_prompt"),
                sanitized_prompt=data.get("sanitized_prompt"),
                ai_response=data.get("ai_response"),
                tool_used=data.get("tool_used"),
                container_id=data.get("container_id"),
                metadata=data.get("extra") or {},
            )
        elif event_type == LogEventType.PERFORMANCE.value:
            self.insert_performance_record(
                execution_time_ms=data.get("execution_time_ms"),
                cpu_usage_percent=data.get("cpu_usage_percent"),
                memory_usage_mb=data.get("memory_usage_mb"),
                container_id=data.get("container_id"),
                tool_used=data.get("tool_used"),
                timestamp=str(data.get("timestamp") or _now_iso()),
                metadata=data.get("extra") or {},
            )
        return log_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a :class:`sqlite3.Row` to a dictionary with JSON metadata."""
        result = dict(row)
        if "metadata" in result:
            result["metadata"] = _json_loads(result["metadata"])
        return result