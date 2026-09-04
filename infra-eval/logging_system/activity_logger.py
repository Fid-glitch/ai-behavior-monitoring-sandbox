"""
Activity logger module.

Provides reusable, thread-safe logging functions for recording every stage
of the AI behaviour monitoring pipeline: user requests, AI responses,
security events, container lifecycle events, performance metrics, and errors.

Each function accepts a ``container_id`` and optional ``extra`` fields and
emits a structured log record that the :class:`JSONFormatter` serialises to
JSON lines.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from .log_formatter import CSVExporter, JSONFormatter
from .log_models import (
    LogDecision,
    LogEventType,
)

#: Root logger name for the activity logging system.
ROOT_LOGGER_NAME = "infra-eval"

#: Registry of functions tracked for invocation-time measurement.
_execution_times: Dict[str, float] = {}

#: Lock protecting the internal execution-time registry.
_execution_lock = threading.Lock()


class ActivityLogger:
    """
    High-level logger that wraps the standard :mod:`logging` module.

    All methods emit structured records with a common set of fields
    (timestamp, level, event type, and any caller-supplied attributes).
    """

    def __init__(
        self,
        name: str = "activity",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialise the activity logger.

        Args:
            name: Sub-logger name.
            logger: Optional logger instance. Defaults to a child of the
                ``infra-eval`` root logger.
        """
        self.name = name
        self.logger = logger or logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")

    def _log(
        self,
        level: int,
        message: str,
        event_type: LogEventType,
        *,
        user_prompt: Optional[str] = None,
        sanitized_prompt: Optional[str] = None,
        ai_response: Optional[str] = None,
        tool_used: Optional[str] = None,
        risk_score: Optional[float] = None,
        decision: Optional[LogDecision] = None,
        execution_time_ms: Optional[float] = None,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_mb: Optional[float] = None,
        container_id: Optional[str] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a structured log record.

        Args:
            level: Numeric logging level.
            message: Human-readable log message.
            event_type: Category of the event.
            user_prompt: Original user prompt.
            sanitized_prompt: Sanitised version of the prompt.
            ai_response: AI-generated response.
            tool_used: Tool used to process the request.
            risk_score: Risk score in the ``[0, 1]`` range.
            decision: Decision outcome (ALLOW / BLOCK / WARNING).
            execution_time_ms: Execution time in milliseconds.
            cpu_usage_percent: CPU usage percentage.
            memory_usage_mb: Memory usage in megabytes.
            container_id: Sandbox container identifier.
            status: Human-readable status (e.g. ``"completed"``).
            error_message: Error description when applicable.
            extra: Arbitrary additional metadata.
        """
        extra_fields: Dict[str, Any] = {
            "event_type": event_type.value,
        }
        if user_prompt is not None:
            extra_fields["user_prompt"] = user_prompt
        if sanitized_prompt is not None:
            extra_fields["sanitized_prompt"] = sanitized_prompt
        if ai_response is not None:
            extra_fields["ai_response"] = ai_response
        if tool_used is not None:
            extra_fields["tool_used"] = tool_used
        if risk_score is not None:
            extra_fields["risk_score"] = risk_score
        if decision is not None:
            extra_fields["decision"] = decision.value
        if execution_time_ms is not None:
            extra_fields["execution_time_ms"] = execution_time_ms
        if cpu_usage_percent is not None:
            extra_fields["cpu_usage_percent"] = cpu_usage_percent
        if memory_usage_mb is not None:
            extra_fields["memory_usage_mb"] = memory_usage_mb
        if container_id is not None:
            extra_fields["container_id"] = container_id
        if status is not None:
            extra_fields["status"] = status
        if error_message is not None:
            extra_fields["error_message"] = error_message
        if extra:
            extra_fields.update(extra)

        self.logger.log(level, message, extra=extra_fields)

    # ------------------------------------------------------------------
    # Reusable public functions
    # ------------------------------------------------------------------
    def log_request(
        self,
        user_prompt: str,
        *,
        sanitized_prompt: Optional[str] = None,
        tool_used: Optional[str] = None,
        container_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record an incoming user request.

        Args:
            user_prompt: Original user prompt.
            sanitized_prompt: Optional sanitised version of the prompt.
            tool_used: Optional tool that will process the request.
            container_id: Optional sandbox container identifier.
            **extra: Additional structured metadata.
        """
        self._log(
            logging.INFO,
            f"Request received: {user_prompt[:200]!r}",
            LogEventType.REQUEST,
            user_prompt=user_prompt,
            sanitized_prompt=sanitized_prompt,
            tool_used=tool_used,
            container_id=container_id,
            status="received",
            extra=extra,
        )

    def log_response(
        self,
        ai_response: str,
        *,
        user_prompt: Optional[str] = None,
        sanitized_prompt: Optional[str] = None,
        tool_used: Optional[str] = None,
        risk_score: Optional[float] = None,
        decision: Optional[LogDecision] = None,
        execution_time_ms: Optional[float] = None,
        container_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record an AI-generated response.

        Args:
            ai_response: The AI-generated response.
            user_prompt: Optional associated user prompt.
            sanitized_prompt: Optional sanitised prompt.
            tool_used: Optional tool that produced the response.
            risk_score: Optional computed risk score.
            decision: Optional decision outcome.
            execution_time_ms: Optional execution time in milliseconds.
            container_id: Optional sandbox container identifier.
            **extra: Additional structured metadata.
        """
        self._log(
            logging.INFO,
            "Response generated",
            LogEventType.RESPONSE,
            ai_response=ai_response,
            user_prompt=user_prompt,
            sanitized_prompt=sanitized_prompt,
            tool_used=tool_used,
            risk_score=risk_score,
            decision=decision,
            execution_time_ms=execution_time_ms,
            container_id=container_id,
            status="completed",
            extra=extra,
        )

    def log_security_event(
        self,
        user_prompt: str,
        sanitized_prompt: str,
        risk_score: float,
        decision: LogDecision,
        *,
        ai_response: Optional[str] = None,
        tool_used: Optional[str] = None,
        container_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record a security event such as prompt injection detection.

        Args:
            user_prompt: Original user prompt.
            sanitized_prompt: Sanitised version of the prompt.
            risk_score: Computed risk score in ``[0, 1]``.
            decision: Decision outcome (ALLOW / BLOCK / WARNING).
            ai_response: Optional AI response.
            tool_used: Optional tool used.
            container_id: Optional sandbox container identifier.
            **extra: Additional structured metadata.
        """
        if decision == LogDecision.BLOCK:
            level = logging.CRITICAL
        elif decision == LogDecision.WARNING or risk_score >= 0.7:
            level = logging.WARNING
        else:
            level = logging.INFO

        self._log(
            level,
            f"Security event decision={decision.value} risk={risk_score:.2f}",
            LogEventType.SECURITY,
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

    def log_container_event(
        self,
        event: str,
        container_id: str,
        *,
        status: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record a container lifecycle event.

        Args:
            event: Event name (e.g. ``"start"``, ``"stop"``, ``"remove"``).
            container_id: Sandbox container identifier.
            status: Optional container status.
            **extra: Additional structured metadata.
        """
        self._log(
            logging.INFO,
            f"Container event: {event}",
            LogEventType.CONTAINER,
            container_id=container_id,
            status=status or event,
            extra=extra,
        )

    def log_performance(
        self,
        *,
        execution_time_ms: Optional[float] = None,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_mb: Optional[float] = None,
        container_id: Optional[str] = None,
        tool_used: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record performance metrics for a pipeline stage.

        Args:
            execution_time_ms: Execution time in milliseconds.
            cpu_usage_percent: CPU usage percentage.
            memory_usage_mb: Memory usage in megabytes.
            container_id: Optional sandbox container identifier.
            tool_used: Optional tool that was measured.
            **extra: Additional structured metadata.
        """
        self._log(
            logging.INFO,
            "Performance metrics recorded",
            LogEventType.PERFORMANCE,
            execution_time_ms=execution_time_ms,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_mb=memory_usage_mb,
            container_id=container_id,
            tool_used=tool_used,
            status="completed",
            extra=extra,
        )

    def log_error(
        self,
        error: Exception,
        *,
        message: Optional[str] = None,
        container_id: Optional[str] = None,
        tool_used: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Record an exception with its traceback.

        Args:
            error: The exception to log.
            message: Optional human-readable description.
            container_id: Optional sandbox container identifier.
            tool_used: Optional tool involved.
            **extra: Additional structured metadata.
        """
        description = message or str(error) or error.__class__.__name__
        self.logger.error(
            f"Error: {description}",
            exc_info=error,
            extra={
                "event_type": LogEventType.ERROR.value,
                "error_message": str(error) or error.__class__.__name__,
                "container_id": container_id,
                "tool_used": tool_used,
                "status": "failed",
                **extra,
            },
        )

    def log_system_event(
        self,
        message: str,
        *,
        level: int = logging.INFO,
        **extra: Any,
    ) -> None:
        """
        Record a generic system event.

        Args:
            message: Description of the system event.
            level: Logging level (default INFO).
            **extra: Additional structured metadata.
        """
        self.logger.log(level, message, extra={"event_type": LogEventType.SYSTEM.value, **extra})

    def export_to_csv(
        self,
        json_log_path: Any,
        csv_output_path: Any,
        fields: Optional[Any] = None,
    ) -> int:
        """
        Export a JSON-lines log file to CSV.

        Args:
            json_log_path: Path to the source JSON log file.
            csv_output_path: Destination CSV path.
            fields: Optional ordered column names.

        Returns:
            Number of rows written.
        """
        exporter = CSVExporter(fields=fields)
        return exporter.export_file(
            json_log_path=json_log_path,
            csv_output_path=csv_output_path,
            include_header=True,
        )


# ----------------------------------------------------------------------
# Module-level singleton and convenience functions
# ----------------------------------------------------------------------
#: Default module-level activity logger instance.
logger = ActivityLogger()


def log_request(
    user_prompt: str,
    *,
    sanitized_prompt: Optional[str] = None,
    tool_used: Optional[str] = None,
    container_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record an incoming user request (module-level convenience function).

    Args:
        user_prompt: Original user prompt.
        sanitized_prompt: Optional sanitised version of the prompt.
        tool_used: Optional tool that will process the request.
        container_id: Optional sandbox container identifier.
        **extra: Additional structured metadata.
    """
    logger.log_request(
        user_prompt,
        sanitized_prompt=sanitized_prompt,
        tool_used=tool_used,
        container_id=container_id,
        **extra,
    )


def log_response(
    ai_response: str,
    *,
    user_prompt: Optional[str] = None,
    sanitized_prompt: Optional[str] = None,
    tool_used: Optional[str] = None,
    risk_score: Optional[float] = None,
    decision: Optional[LogDecision] = None,
    execution_time_ms: Optional[float] = None,
    container_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record an AI-generated response (module-level convenience function).

    Args:
        ai_response: The AI-generated response.
        user_prompt: Optional associated user prompt.
        sanitized_prompt: Optional sanitised prompt.
        tool_used: Optional tool that produced the response.
        risk_score: Optional computed risk score.
        decision: Optional decision outcome.
        execution_time_ms: Optional execution time in milliseconds.
        container_id: Optional sandbox container identifier.
        **extra: Additional structured metadata.
    """
    logger.log_response(
        ai_response,
        user_prompt=user_prompt,
        sanitized_prompt=sanitized_prompt,
        tool_used=tool_used,
        risk_score=risk_score,
        decision=decision,
        execution_time_ms=execution_time_ms,
        container_id=container_id,
        **extra,
    )


def log_security_event(
    user_prompt: str,
    sanitized_prompt: str,
    risk_score: float,
    decision: LogDecision,
    *,
    ai_response: Optional[str] = None,
    tool_used: Optional[str] = None,
    container_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record a security event such as prompt injection detection
    (module-level convenience function).

    Args:
        user_prompt: Original user prompt.
        sanitized_prompt: Sanitised version of the prompt.
        risk_score: Computed risk score in ``[0, 1]``.
        decision: Decision outcome (ALLOW / BLOCK / WARNING).
        ai_response: Optional AI response.
        tool_used: Optional tool used.
        container_id: Optional sandbox container identifier.
        **extra: Additional structured metadata.
    """
    logger.log_security_event(
        user_prompt,
        sanitized_prompt,
        risk_score,
        decision,
        ai_response=ai_response,
        tool_used=tool_used,
        container_id=container_id,
        **extra,
    )


def log_container_event(
    event: str,
    container_id: str,
    *,
    status: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record a container lifecycle event (module-level convenience function).

    Args:
        event: Event name (e.g. ``"start"``, ``"stop"``, ``"remove"``).
        container_id: Sandbox container identifier.
        status: Optional container status.
        **extra: Additional structured metadata.
    """
    logger.log_container_event(event, container_id, status=status, **extra)


def log_performance(
    *,
    execution_time_ms: Optional[float] = None,
    cpu_usage_percent: Optional[float] = None,
    memory_usage_mb: Optional[float] = None,
    container_id: Optional[str] = None,
    tool_used: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record performance metrics (module-level convenience function).

    Args:
        execution_time_ms: Execution time in milliseconds.
        cpu_usage_percent: CPU usage percentage.
        memory_usage_mb: Memory usage in megabytes.
        container_id: Optional sandbox container identifier.
        tool_used: Optional tool that was measured.
        **extra: Additional structured metadata.
    """
    logger.log_performance(
        execution_time_ms=execution_time_ms,
        cpu_usage_percent=cpu_usage_percent,
        memory_usage_mb=memory_usage_mb,
        container_id=container_id,
        tool_used=tool_used,
        **extra,
    )


def log_error(
    error: Exception,
    *,
    message: Optional[str] = None,
    container_id: Optional[str] = None,
    tool_used: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Record an exception (module-level convenience function).

    Args:
        error: The exception to log.
        message: Optional human-readable description.
        container_id: Optional sandbox container identifier.
        tool_used: Optional tool involved.
        **extra: Additional structured metadata.
    """
    logger.log_error(
        error,
        message=message,
        container_id=container_id,
        tool_used=tool_used,
        **extra,
    )


def log_system_event(
    message: str,
    *,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    """
    Record a generic system event (module-level convenience function).

    Args:
        message: Description of the system event.
        level: Logging level (default INFO).
        **extra: Additional structured metadata.
    """
    logger.log_system_event(message, level=level, **extra)


def timed(activity_logger: Optional[ActivityLogger] = None):
    """
    Decorator that logs execution time for a callable.

    Args:
        activity_logger: Optional :class:`ActivityLogger` instance. Defaults
            to the module-level singleton.

    Returns:
        A decorator wrapping the target callable.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            import time

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                (activity_logger or logger).log_performance(
                    execution_time_ms=elapsed_ms,
                    tool_used=func.__qualname__,
                )
                return result
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                (activity_logger or logger).log_error(
                    exc,
                    tool_used=func.__qualname__,
                )
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator


def create_activity_logger(
    name: str = "activity",
    logger_instance: Optional[logging.Logger] = None,
) -> ActivityLogger:
    """
    Factory for creating a named :class:`ActivityLogger`.

    Args:
        name: Sub-logger name.
        logger_instance: Optional logger instance.

    Returns:
        A configured :class:`ActivityLogger`.
    """
    return ActivityLogger(name=name, logger=logger_instance)


# Export the JSON formatter and CSV exporter for convenience.
JSONLogFormatter = JSONFormatter
CsvExporter = CSVExporter
