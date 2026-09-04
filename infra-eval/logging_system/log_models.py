"""
Log models module.

Defines the Pydantic models and enums used throughout the activity logging
system. These models are intentionally independent of the logging framework
so they can be imported by other modules without coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class LogLevel(str, Enum):
    """Standard logging levels mapped to the Python logging module."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogDecision(str, Enum):
    """Decision outcome for a security or risk evaluation."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    WARNING = "WARNING"


class LogEventType(str, Enum):
    """Categorisation of log event types for structured filtering."""

    REQUEST = "request"
    RESPONSE = "response"
    SECURITY = "security"
    CONTAINER = "container"
    PERFORMANCE = "performance"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class LogEntry:
    """
    Structured representation of a single log entry.

    All fields are optional with sensible defaults so callers can construct
    partial entries for specific use cases (e.g. performance logging may
    omit the prompt fields).
    """

    # Core fields
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    level: LogLevel = LogLevel.INFO
    event_type: LogEventType = LogEventType.SYSTEM

    # Request / response fields
    user_prompt: Optional[str] = None
    sanitized_prompt: Optional[str] = None
    ai_response: Optional[str] = None
    tool_used: Optional[str] = None

    # Security / risk fields
    risk_score: Optional[float] = None
    decision: Optional[LogDecision] = None

    # Performance fields
    execution_time_ms: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None

    # Container fields
    container_id: Optional[str] = None

    # Status and error fields
    status: Optional[str] = None
    error_message: Optional[str] = None
    traceback: Optional[str] = None

    # Metadata
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialise the log entry to a JSON-serialisable dictionary.

        Returns:
            A dictionary with all non-None fields.
        """
        result: Dict[str, Any] = {}
        for field_name, field_value in self.__dataclass_fields__.items():
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, Enum):
                    result[field_name] = value.value
                else:
                    result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LogEntry:
        """
        Build a :class:`LogEntry` from a dictionary (e.g. JSON deserialisation).

        Args:
            data: Dictionary containing log entry fields.

        Returns:
            A new :class:`LogEntry` instance.
        """
        safe = {}
        for key, value in data.items():
            if key == "level":
                safe[key] = LogLevel(value)
            elif key == "event_type":
                safe[key] = LogEventType(value)
            elif key == "decision":
                safe[key] = LogDecision(value) if value else None
            else:
                safe[key] = value
        return cls(**safe)

    @classmethod
    def create_error_entry(
        cls,
        error_message: str,
        traceback: Optional[str] = None,
        level: LogLevel = LogLevel.ERROR,
        container_id: Optional[str] = None,
        **extra: Any,
    ) -> LogEntry:
        """
        Factory method for creating an error log entry.

        Args:
            error_message: Description of the error.
            traceback: Optional stack trace string.
            level: Severity level (default ERROR).
            container_id: Optional container identifier.
            **extra: Additional metadata fields.

        Returns:
            A pre-populated :class:`LogEntry`.
        """
        return cls(
            level=level,
            event_type=LogEventType.ERROR,
            error_message=error_message,
            traceback=traceback,
            container_id=container_id,
            status="failed",
            extra=extra,
        )

    @classmethod
    def create_security_entry(
        cls,
        user_prompt: str,
        sanitized_prompt: str,
        risk_score: float,
        decision: LogDecision,
        ai_response: Optional[str] = None,
        tool_used: Optional[str] = None,
        container_id: Optional[str] = None,
        **extra: Any,
    ) -> LogEntry:
        """
        Factory method for creating a security event log entry.

        Args:
            user_prompt: The original user prompt.
            sanitized_prompt: The sanitised version of the prompt.
            risk_score: Computed risk score.
            decision: The decision outcome (ALLOW / BLOCK / WARNING).
            ai_response: Optional AI-generated response.
            tool_used: Optional tool used for processing.
            container_id: Optional container identifier.
            **extra: Additional metadata fields.

        Returns:
            A pre-populated :class:`LogEntry`.
        """
        return cls(
            level=LogLevel.WARNING if risk_score >= 0.7 else LogLevel.INFO,
            event_type=LogEventType.SECURITY,
            user_prompt=user_prompt,
            sanitized_prompt=sanitized_prompt,
            ai_response=ai_response,
            tool_used=tool_used,
            risk_score=risk_score,
            decision=decision,
            container_id=container_id,
            status="completed",
            extra=extra,
        )

    @classmethod
    def create_performance_entry(
        cls,
        execution_time_ms: float,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_mb: Optional[float] = None,
        container_id: Optional[str] = None,
        tool_used: Optional[str] = None,
        **extra: Any,
    ) -> LogEntry:
        """
        Factory method for creating a performance log entry.

        Args:
            execution_time_ms: Execution time in milliseconds.
            cpu_usage_percent: Optional CPU usage percentage.
            memory_usage_mb: Optional memory usage in megabytes.
            container_id: Optional container identifier.
            tool_used: Optional tool used.
            **extra: Additional metadata fields.

        Returns:
            A pre-populated :class:`LogEntry`.
        """
        return cls(
            level=LogLevel.INFO,
            event_type=LogEventType.PERFORMANCE,
            execution_time_ms=execution_time_ms,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_mb=memory_usage_mb,
            container_id=container_id,
            tool_used=tool_used,
            status="completed",
            extra=extra,
        )


# Alias for backward compatibility with earlier drafts
LogData = LogEntry


# ---------------------------------------------------------------------------
# Collection of log entries for batch operations
# ---------------------------------------------------------------------------
@dataclass
class LogBatch:
    """
    A batch of log entries for bulk export or processing.

    Attributes:
        entries: List of log entries in the batch.
        source: Optional identifier for the source of this batch.
        created_at: ISO-format timestamp of batch creation.
    """

    entries: List[LogEntry] = field(default_factory=list)
    source: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add(self, entry: LogEntry) -> None:
        """Add a log entry to the batch."""
        self.entries.append(entry)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serialise all entries to a list of dictionaries."""
        return [entry.to_dict() for entry in self.entries]

    def __len__(self) -> int:
        return len(self.entries)
