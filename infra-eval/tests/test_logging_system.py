"""
Unit tests for the activity logging system.

Tests cover the :mod:`logging_system` package: JSON formatting, CSV export,
log entry models, reusable logging functions, log rotation, and thread safety.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from logging_system import (
    CSVExporter,
    JSONFormatter,
    LogBatch,
    LogDecision,
    LogEntry,
    LogEventType,
    LogLevel,
    LoggingConfig,
    setup_logging,
)
from logging_system.activity_logger import (
    create_activity_logger,
    log_container_event,
    log_error,
    log_performance,
    log_request,
    log_response,
    log_security_event,
    log_system_event,
)
from logging_system.logger_config import ActivityLoggerManager


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset the logging configuration between tests.

    The :func:`setup_logging` function is idempotent, so without a reset the
    ``infra-eval`` root logger would retain file handlers from earlier tests,
    causing assertions about file contents to leak across tests.
    """
    root_logger = logging.getLogger("infra-eval")
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    root_logger.setLevel(logging.NOTSET)
    ActivityLoggerManager.reset()
    yield
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    ActivityLoggerManager.reset()


# ----------------------------------------------------------------------
# LogEntry model tests
# ----------------------------------------------------------------------
class TestLogEntryModel:
    """Tests for the LogEntry dataclass and its factories."""

    def test_default_timestamp(self) -> None:
        entry = LogEntry()
        assert entry.timestamp
        assert entry.level == LogLevel.INFO

    def test_to_dict_stringifies_enums(self) -> None:
        entry = LogEntry(
            level=LogLevel.WARNING,
            decision=LogDecision.BLOCK,
            event_type=LogEventType.SECURITY,
            risk_score=0.9,
        )
        data = entry.to_dict()
        assert data["level"] == "WARNING"
        assert data["decision"] == "BLOCK"
        assert data["event_type"] == "security"
        assert data["risk_score"] == 0.9

    def test_to_dict_omits_none(self) -> None:
        entry = LogEntry(user_prompt="hi")
        data = entry.to_dict()
        assert "ai_response" not in data
        assert "cpu_usage_percent" not in data

    def test_from_dict_roundtrip(self) -> None:
        original = LogEntry(
            level=LogLevel.ERROR,
            event_type=LogEventType.ERROR,
            error_message="boom",
            decision=None,
        )
        restored = LogEntry.from_dict(original.to_dict())
        assert restored.level == LogLevel.ERROR
        assert restored.event_type == LogEventType.ERROR
        assert restored.error_message == "boom"

    def test_create_error_entry(self) -> None:
        entry = LogEntry.create_error_entry("disk full", container_id="abc")
        assert entry.level == LogLevel.ERROR
        assert entry.event_type == LogEventType.ERROR
        assert entry.status == "failed"
        assert entry.container_id == "abc"

    def test_create_security_entry_levels(self) -> None:
        high = LogEntry.create_security_entry(
            "p", "p", 0.9, LogDecision.BLOCK
        )
        low = LogEntry.create_security_entry(
            "p", "p", 0.2, LogDecision.ALLOW
        )
        assert high.level == LogLevel.WARNING or high.level == LogLevel.INFO
        assert low.level == LogLevel.INFO

    def test_create_performance_entry(self) -> None:
        entry = LogEntry.create_performance_entry(
            execution_time_ms=12.5,
            cpu_usage_percent=3.1,
            memory_usage_mb=64.0,
        )
        assert entry.event_type == LogEventType.PERFORMANCE
        assert entry.execution_time_ms == 12.5
        assert entry.cpu_usage_percent == 3.1

    def test_log_batch(self) -> None:
        batch = LogBatch(source="test")
        batch.add(LogEntry(level=LogLevel.INFO))
        batch.add(LogEntry(level=LogLevel.ERROR))
        assert len(batch) == 2
        assert len(batch.to_dict_list()) == 2


# ----------------------------------------------------------------------
# JSONFormatter tests
# ----------------------------------------------------------------------
class TestJSONFormatter:
    """Tests for the JSON formatter."""

    def _record(self, **kwargs) -> logging.LogRecord:
        defaults = {
            "name": "test",
            "level": logging.INFO,
            "pathname": __file__,
            "lineno": 1,
            "msg": "hello %s",
            "args": ("world",),
            "exc_info": None,
        }
        defaults.update(kwargs)
        return logging.LogRecord(**defaults)

    def test_formats_json(self) -> None:
        formatter = JSONFormatter()
        out = formatter.format(self._record())
        data = json.loads(out)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert "timestamp" in data

    def test_includes_extra_fields(self) -> None:
        formatter = JSONFormatter()
        record = self._record()
        record.risk_score = 0.85
        record.container_id = "abc123"
        data = json.loads(formatter.format(record))
        assert data["risk_score"] == 0.85
        assert data["container_id"] == "abc123"

    def test_no_timestamp_when_disabled(self) -> None:
        formatter = JSONFormatter(include_timestamp=False)
        data = json.loads(formatter.format(self._record()))
        assert "timestamp" not in data

    def test_exception_included(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = self._record(exc_info=exc_info)
        data = json.loads(formatter.format(record))
        assert "exception" in data
        assert "ValueError" in data["exception"]


# ----------------------------------------------------------------------
# CSVExporter tests
# ----------------------------------------------------------------------
class TestCSVExporter:
    """Tests for CSV export functionality."""

    @pytest.fixture
    def exporter(self) -> CSVExporter:
        return CSVExporter()

    def test_export_rows_writes_csv(self, exporter: CSVExporter, tmp_path: Path) -> None:
        csv_path = tmp_path / "out.csv"
        rows = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "level": "INFO",
                "event_type": "request",
                "user_prompt": "hello",
                "risk_score": "",
                "decision": "",
                "container_id": "abc",
                "status": "received",
            },
            {
                "timestamp": "2024-01-01T00:00:01",
                "level": "WARNING",
                "event_type": "security",
                "user_prompt": "drop table",
                "risk_score": "0.9",
                "decision": "BLOCK",
                "container_id": "abc",
                "status": "completed",
            },
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            count = exporter.export_rows(fh, rows, include_header=True)
        assert count == 2
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            parsed = list(reader)
        assert len(parsed) == 2
        assert parsed[0]["user_prompt"] == "hello"
        assert parsed[1]["decision"] == "BLOCK"

    def test_export_log_entries(self, exporter: CSVExporter, tmp_path: Path) -> None:
        csv_path = tmp_path / "entries.csv"
        entries = [
            LogEntry(user_prompt="p1", event_type=LogEventType.REQUEST).to_dict(),
            LogEntry(user_prompt="p2", event_type=LogEventType.REQUEST).to_dict(),
        ]
        count = exporter.export_log_entries(csv_path, entries, include_header=True)
        assert count == 2
        assert exporter.read_csv(csv_path)[0]["user_prompt"] == "p1"

    def test_export_file_from_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "activity.log"
        csv_path = tmp_path / "activity.csv"
        json_path.write_text(
            json.dumps(
                {
                    "timestamp": "2024-01-01T00:00:00",
                    "level": "INFO",
                    "event_type": "request",
                    "user_prompt": "hello",
                    "status": "received",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        exporter = CSVExporter()
        count = exporter.export_file(json_path, csv_path)
        assert count == 1
        assert exporter.read_csv(csv_path)[0]["user_prompt"] == "hello"

    def test_export_file_missing_raises(self, tmp_path: Path) -> None:
        exporter = CSVExporter()
        with pytest.raises(FileNotFoundError):
            exporter.export_file(tmp_path / "missing.log", tmp_path / "out.csv")


# ----------------------------------------------------------------------
# setup_logging tests
# ----------------------------------------------------------------------
class TestSetupLogging:
    """Tests for logger configuration and rotation."""

    def test_setup_returns_logger(self, tmp_path: Path) -> None:
        cfg = LoggingConfig(
            log_level="DEBUG",
            file_enabled=True,
            file_path=str(tmp_path / "test.log"),
        )
        logger = setup_logging(cfg)
        assert logger.level == logging.DEBUG
        # Idempotent: re-calling does not duplicate a handle error.
        logger2 = setup_logging(cfg)
        assert logger2 is logger

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValidationError):
            LoggingConfig(log_level="NOT_A_LEVEL")

    def test_writes_json_lines_to_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "rotate.log"
        cfg = LoggingConfig(
            log_level="INFO",
            file_enabled=True,
            file_path=str(log_file),
            json_format=True,
        )
        logger = setup_logging(cfg)
        logger.info("test message", extra={"event_type": "system", "status": "ok"})
        # Ensure the handler flushes.
        for handler in logger.handlers:
            handler.flush()
        content = log_file.read_text(encoding="utf-8")
        data = json.loads(content.strip().splitlines()[-1])
        assert data["message"] == "test message"
        assert data["event_type"] == "system"

    def test_rotating_file_handler(self, tmp_path: Path) -> None:
        log_file = tmp_path / "tiny.log"
        cfg = LoggingConfig(
            log_level="DEBUG",
            file_enabled=True,
            file_path=str(log_file),
            max_bytes=200,
            backup_count=2,
            json_format=True,
        )
        logger = setup_logging(cfg)
        for i in range(50):
            logger.info(f"message number {i}", extra={"event_type": "system"})
        for handler in logger.handlers:
            handler.flush()
        # Rotation should have created at least one backup file.
        backups = list(tmp_path.glob("tiny.log.*"))
        assert len(backups) >= 1


# ----------------------------------------------------------------------
# ActivityLogger function tests
# ----------------------------------------------------------------------
class TestActivityLoggerFunctions:
    """Tests for the reusable logging functions."""

    @pytest.fixture
    def caplog_logger(self, caplog) -> logging.Logger:
        caplog.set_level(logging.DEBUG)
        return caplog

    def test_log_request(self, caplog) -> None:
        logger = create_activity_logger("test_mod")
        with caplog.at_level(logging.DEBUG):
            logger.log_request(
                "hello", sanitized_prompt="hello", tool_used="tool", container_id="cid"
            )
        assert any("Request received" in r.message for r in caplog.records)

    def test_log_security_event_block_sets_critical(self, caplog) -> None:
        logger = create_activity_logger("test_sec")
        with caplog.at_level(logging.DEBUG):
            logger.log_security_event(
                "prompt", "prompt", 0.95, LogDecision.BLOCK, container_id="cid"
            )
        assert any(r.levelno == logging.CRITICAL for r in caplog.records)

    def test_log_error_records_exception(self, caplog) -> None:
        logger = create_activity_logger("test_err")
        with caplog.at_level(logging.DEBUG):
            try:
                raise ValueError("boom")
            except ValueError as exc:
                logger.log_error(exc, container_id="cid")
        assert any("Error:" in r.message for r in caplog.records)

    def test_module_level_functions_run_without_error(self, caplog) -> None:
        with caplog.at_level(logging.DEBUG):
            log_request("module req", container_id="cid")
            log_response("module resp", risk_score=0.1, decision=LogDecision.ALLOW)
            log_security_event(
                "module prompt", "module sanitized", 0.5, LogDecision.WARNING
            )
            log_container_event("start", "cid")
            log_performance(execution_time_ms=1.0, cpu_usage_percent=0.5)
            log_system_event("module system event")
            try:
                raise RuntimeError("module err")
            except RuntimeError as exc:
                log_error(exc)
        assert caplog.records


# ----------------------------------------------------------------------
# Thread-safety tests
# ----------------------------------------------------------------------
class TestThreadSafety:
    """Tests that concurrent logging does not corrupt output."""

    def test_concurrent_logging_to_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "thread.log"
        cfg = LoggingConfig(
            log_level="DEBUG",
            file_enabled=True,
            file_path=str(log_file),
            json_format=True,
        )
        logger = setup_logging(cfg)
        errors: list = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(50):
                    logger.info(
                        f"worker {worker_id} msg {i}",
                        extra={"event_type": "thread", "worker_id": worker_id},
                    )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        for handler in logger.handlers:
            handler.flush()

        lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line]
        assert len(lines) == 200
        # Every line must be valid JSON.
        for line in lines:
            data = json.loads(line)
            assert "message" in data

    def test_concurrent_csv_exporter(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "thread.csv"
        exporter = CSVExporter()
        errors: list = []

        def worker(worker_id: int) -> None:
            try:
                rows = [
                    {
                        "timestamp": "t",
                        "level": "INFO",
                        "event_type": "thread",
                        "worker_id": worker_id,
                    }
                ]
                with open(csv_path, "a", newline="", encoding="utf-8") as fh:
                    exporter.export_rows(fh, rows, include_header=False)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert exporter.read_csv(csv_path)
