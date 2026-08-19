"""
Unit tests for the SQLite database layer.

Tests cover database initialisation, table creation, activity log
insertion/retrieval, querying, security event storage, performance /
evaluation storage, error handling, and thread safety. All tests use
temporary or in-memory SQLite databases so no real database files are
touched.
"""

from __future__ import annotations

import threading

import pytest

from database import (
    Database,
    DatabaseConnectionError,
    InvalidRecordError,
    parse_database_url,
)
from logging_system import (
    LogDecision,
    LogEntry,
    LogEventType,
    LogLevel,
)


@pytest.fixture
def db(tmp_path) -> Database:
    """Build a Database backed by a temporary file."""
    database = Database(tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()


# ----------------------------------------------------------------------
# Database initialisation / table creation
# ----------------------------------------------------------------------
class TestDatabaseInitialization:
    """Tests for database initialisation and schema creation."""

    def test_initialize_creates_tables(self, tmp_path) -> None:
        db = Database(tmp_path / "init.db")
        db.initialize()
        tables = db.table_names()
        assert "activity_logs" in tables
        assert "security_events" in tables
        assert "performance_records" in tables
        db.close()

    def test_initialize_is_idempotent(self, tmp_path) -> None:
        db = Database(tmp_path / "idem.db")
        db.initialize()
        db.initialize()
        assert len(db.table_names()) == 3
        db.close()

    def test_auto_create_on_first_insert(self, tmp_path) -> None:
        db = Database(tmp_path / "auto.db")
        log_id = db.insert_activity_log(
            LogEntry(level=LogLevel.INFO, event_type=LogEventType.SYSTEM)
        )
        assert log_id > 0
        assert "activity_logs" in db.table_names()
        db.close()

    def test_context_manager(self, tmp_path) -> None:
        with Database(tmp_path / "ctx.db") as db:
            log_id = db.insert_activity_log(
                LogEntry(level=LogLevel.INFO, event_type=LogEventType.SYSTEM)
            )
            assert log_id > 0

    def test_directory_path_raises(self, tmp_path) -> None:
        with pytest.raises(DatabaseConnectionError):
            Database(tmp_path).initialize()

    def test_parse_database_url(self) -> None:
        assert parse_database_url("sqlite:///./data/sandbox.db") == "./data/sandbox.db"
        assert parse_database_url("sqlite:///:memory:") == ":memory:"
        with pytest.raises(ValueError):
            parse_database_url("postgres://localhost/db")


# ----------------------------------------------------------------------
# Activity log insertion / retrieval
# ----------------------------------------------------------------------
class TestActivityLogInsertion:
    """Tests for inserting and retrieving activity log records."""

    def test_insert_log_entry(self, db: Database) -> None:
        entry = LogEntry(
            level=LogLevel.INFO,
            event_type=LogEventType.REQUEST,
            user_prompt="hello world",
            container_id="abc123",
            status="received",
        )
        log_id = db.insert_activity_log(entry)
        record = db.get_activity_log(log_id)
        assert record is not None
        assert record["event_type"] == "request"
        assert record["level"] == "INFO"
        assert record["user_prompt"] == "hello world"
        assert record["container_id"] == "abc123"

    def test_insert_dict(self, db: Database) -> None:
        log_id = db.insert_activity_log(
            {
                "level": "ERROR",
                "event_type": "error",
                "error_message": "boom",
                "container_id": "cid",
            }
        )
        record = db.get_activity_log(log_id)
        assert record["level"] == "ERROR"
        assert record["event_type"] == "error"
        assert record["error_message"] == "boom"

    def test_insert_enum_values(self, db: Database) -> None:
        entry = LogEntry(
            level=LogLevel.CRITICAL,
            event_type=LogEventType.SECURITY,
            decision=LogDecision.BLOCK,
            risk_score=0.95,
        )
        log_id = db.insert_activity_log(entry)
        record = db.get_activity_log(log_id)
        assert record["level"] == "CRITICAL"
        assert record["decision"] == "BLOCK"
        assert record["risk_score"] == pytest.approx(0.95)

    def test_insert_with_metadata(self, db: Database) -> None:
        entry = LogEntry(
            level=LogLevel.INFO,
            event_type=LogEventType.SYSTEM,
            extra={"source": "test", "iteration": 3},
        )
        log_id = db.insert_activity_log(entry)
        assert db.get_activity_log(log_id)["metadata"] == {
            "source": "test",
            "iteration": 3,
        }

    def test_retrieve_missing_returns_none(self, db: Database) -> None:
        assert db.get_activity_log(999999) is None

    def test_insert_multiple_records(self, db: Database) -> None:
        entries = [
            LogEntry(level=LogLevel.INFO, event_type=LogEventType.REQUEST),
            LogEntry(level=LogLevel.WARNING, event_type=LogEventType.SECURITY),
            LogEntry(level=LogLevel.ERROR, event_type=LogEventType.ERROR),
        ]
        ids = [db.insert_activity_log(e) for e in entries]
        assert len(set(ids)) == 3
        assert db.count_activity_logs() == 3

    def test_batch_insert(self, db: Database) -> None:
        entries = [
            LogEntry(level=LogLevel.INFO, event_type=LogEventType.REQUEST),
            LogEntry(level=LogLevel.ERROR, event_type=LogEventType.ERROR),
        ]
        ids = db.insert_activity_logs(entries)
        assert len(ids) == 2
        assert db.count_activity_logs() == 2


# ----------------------------------------------------------------------
# Querying activity logs
# ----------------------------------------------------------------------
class TestActivityLogQueries:
    """Tests for querying and filtering activity log records."""

    @pytest.fixture
    def populated(self, db: Database) -> Database:
        entries = [
            LogEntry(
                level=LogLevel.INFO,
                event_type=LogEventType.REQUEST,
                user_prompt="p1",
                container_id="c1",
                timestamp="2026-01-01T10:00:00+00:00",
            ),
            LogEntry(
                level=LogLevel.WARNING,
                event_type=LogEventType.SECURITY,
                user_prompt="p2",
                container_id="c2",
                timestamp="2026-01-02T10:00:00+00:00",
            ),
            LogEntry(
                level=LogLevel.ERROR,
                event_type=LogEventType.ERROR,
                user_prompt="p3",
                container_id="c1",
                timestamp="2026-01-03T10:00:00+00:00",
            ),
        ]
        for e in entries:
            db.insert_activity_log(e)
        return db

    def test_query_all(self, populated: Database) -> None:
        assert len(populated.query_activity_logs()) == 3

    def test_query_by_event_type(self, populated: Database) -> None:
        records = populated.query_activity_logs(event_type="security")
        assert len(records) == 1
        assert records[0]["event_type"] == "security"

    def test_query_by_level(self, populated: Database) -> None:
        records = populated.query_activity_logs(level="ERROR")
        assert len(records) == 1
        assert records[0]["level"] == "ERROR"

    def test_query_by_container(self, populated: Database) -> None:
        assert len(populated.query_activity_logs(container_id="c1")) == 2

    def test_query_by_time_range(self, populated: Database) -> None:
        records = populated.query_activity_logs(
            start_time="2026-01-02T00:00:00+00:00",
            end_time="2026-01-03T23:59:59+00:00",
        )
        assert len(records) == 2

    def test_query_limit_offset(self, populated: Database) -> None:
        assert len(populated.query_activity_logs(limit=2)) == 2
        assert len(populated.query_activity_logs(limit=2, offset=2)) == 1

    def test_count_filters(self, populated: Database) -> None:
        assert populated.count_activity_logs(event_type="security") == 1
        assert populated.count_activity_logs(level="ERROR") == 1
        assert populated.count_activity_logs(container_id="c1") == 2

    def test_query_orders_newest_first(self, populated: Database) -> None:
        records = populated.query_activity_logs()
        assert records[0]["timestamp"] == "2026-01-03T10:00:00+00:00"
        assert records[2]["timestamp"] == "2026-01-01T10:00:00+00:00"


# ----------------------------------------------------------------------
# LogEntry compatibility
# ----------------------------------------------------------------------
class TestLogEntryCompatibility:
    """Verify LogEntry objects can be stored and round-tripped."""

    def test_insert_log_entry_factory(self, db: Database) -> None:
        entry = LogEntry.create_error_entry("disk full", container_id="c1")
        log_id = db.insert_log_entry(entry)
        record = db.get_activity_log(log_id)
        assert record["event_type"] == "error"
        assert record["error_message"] == "disk full"
        assert record["container_id"] == "c1"
        assert record["status"] == "failed"

    def test_security_entries_also_populate_security_table(self, db: Database) -> None:
        entry = LogEntry.create_security_entry(
            "prompt", "sanitized", 0.9, LogDecision.BLOCK, container_id="c1"
        )
        db.insert_log_entry(entry)
        events = db.query_security_events()
        assert len(events) == 1
        assert events[0]["decision"] == "BLOCK"
        assert events[0]["risk_score"] == pytest.approx(0.9)

    def test_performance_entries_also_populate_performance_table(
        self, db: Database
    ) -> None:
        entry = LogEntry.create_performance_entry(
            execution_time_ms=12.5,
            cpu_usage_percent=3.1,
            memory_usage_mb=64.0,
            container_id="c1",
        )
        db.insert_log_entry(entry)
        records = db.query_performance_records()
        assert len(records) == 1
        assert records[0]["execution_time_ms"] == pytest.approx(12.5)
        assert records[0]["cpu_usage_percent"] == pytest.approx(3.1)


# ----------------------------------------------------------------------
# Security events
# ----------------------------------------------------------------------
class TestSecurityEvents:
    """Tests for security event storage and retrieval."""

    def test_insert_security_event(self, db: Database) -> None:
        event_id = db.insert_security_event(
            event_type="security",
            severity="CRITICAL",
            risk_score=0.95,
            decision="BLOCK",
            user_prompt="drop table users",
            sanitized_prompt="sanitized prompt",
            container_id="c1",
        )
        assert event_id > 0
        event = db.get_security_event(event_id)
        assert event["severity"] == "CRITICAL"
        assert event["decision"] == "BLOCK"
        assert event["risk_score"] == pytest.approx(0.95)
        assert event["user_prompt"] == "drop table users"

    def test_insert_security_event_defaults(self, db: Database) -> None:
        event_id = db.insert_security_event()
        assert event_id > 0
        event = db.get_security_event(event_id)
        assert event["event_type"] == "security"
        assert event["severity"] == "INFO"

    def test_security_event_metadata(self, db: Database) -> None:
        event_id = db.insert_security_event(
            metadata={"threat": "prompt-injection", "model": "test"}
        )
        event = db.get_security_event(event_id)
        assert event["metadata"] == {
            "threat": "prompt-injection",
            "model": "test",
        }

    def test_query_security_events_by_severity(self, db: Database) -> None:
        db.insert_security_event(severity="INFO", decision="ALLOW")
        db.insert_security_event(severity="WARNING", decision="WARNING")
        db.insert_security_event(severity="CRITICAL", decision="BLOCK")
        assert len(db.query_security_events(severity="CRITICAL")) == 1
        assert len(db.query_security_events(decision="BLOCK")) == 1

    def test_query_security_events_by_container(self, db: Database) -> None:
        db.insert_security_event(container_id="c1")
        db.insert_security_event(container_id="c2")
        events = db.query_security_events(container_id="c1")
        assert len(events) == 1
        assert events[0]["container_id"] == "c1"


# ----------------------------------------------------------------------
# Performance / evaluation records
# ----------------------------------------------------------------------
class TestPerformanceRecords:
    """Tests for performance / evaluation record storage and retrieval."""

    def test_insert_performance_record(self, db: Database) -> None:
        record_id = db.insert_performance_record(
            benchmark_name="agentdojo-basic",
            execution_time_ms=123.4,
            cpu_usage_percent=25.5,
            memory_usage_mb=128.0,
            latency_ms=120.0,
            container_id="c1",
            result=0.85,
            evaluation_score=0.92,
        )
        assert record_id > 0
        record = db.get_performance_record(record_id)
        assert record["benchmark_name"] == "agentdojo-basic"
        assert record["execution_time_ms"] == pytest.approx(123.4)
        assert record["evaluation_score"] == pytest.approx(0.92)

    def test_insert_performance_defaults(self, db: Database) -> None:
        record_id = db.insert_performance_record(execution_time_ms=1.0)
        record = db.get_performance_record(record_id)
        assert record["execution_time_ms"] == pytest.approx(1.0)
        assert record["benchmark_name"] is None

    def test_query_performance_by_benchmark(self, db: Database) -> None:
        db.insert_performance_record(benchmark_name="bench-a", execution_time_ms=1.0)
        db.insert_performance_record(benchmark_name="bench-b", execution_time_ms=2.0)
        records = db.query_performance_records(benchmark_name="bench-a")
        assert len(records) == 1
        assert records[0]["benchmark_name"] == "bench-a"

    def test_query_performance_by_container(self, db: Database) -> None:
        db.insert_performance_record(container_id="c1")
        db.insert_performance_record(container_id="c2")
        assert len(db.query_performance_records(container_id="c2")) == 1

    def test_multiple_performance_records(self, db: Database) -> None:
        for i in range(5):
            db.insert_performance_record(
                benchmark_name="bench",
                execution_time_ms=float(i),
            )
        records = db.query_performance_records(benchmark_name="bench")
        assert len(records) == 5


# ----------------------------------------------------------------------
# Error handling
# ----------------------------------------------------------------------
class TestErrorHandling:
    """Tests for invalid data and error handling."""

    def test_invalid_level_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.insert_activity_log({"level": "NOT_A_LEVEL", "event_type": "system"})

    def test_invalid_event_type_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.insert_activity_log({"level": "INFO", "event_type": "not_real"})

    def test_invalid_decision_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.insert_activity_log(
                {"level": "INFO", "event_type": "security", "decision": "MAYBE"}
            )

    def test_invalid_security_severity_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.insert_security_event(severity="NOT_A_SEVERITY")

    def test_invalid_metadata_type_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.insert_activity_log(
                {
                    "level": "INFO",
                    "event_type": "system",
                    "extra": "not-a-dict",
                }
            )

    def test_invalid_query_level_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.query_activity_logs(level="NOPE")

    def test_invalid_query_event_type_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.query_activity_logs(event_type="nope")

    def test_invalid_query_severity_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.query_security_events(severity="NOPE")

    def test_invalid_query_decision_raises(self, db: Database) -> None:
        with pytest.raises(InvalidRecordError):
            db.query_security_events(decision="NOPE")


# ----------------------------------------------------------------------
# Thread safety / concurrency
# ----------------------------------------------------------------------
class TestThreadSafety:
    """Verify the database safely handles concurrent access."""

    def test_concurrent_inserts(self, tmp_path) -> None:
        db = Database(tmp_path / "concurrent.db")
        db.initialize()
        errors: list = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(20):
                    db.insert_activity_log(
                        LogEntry(
                            level=LogLevel.INFO,
                            event_type=LogEventType.SYSTEM,
                            extra={"worker": worker_id, "index": i},
                        ),
                        message=f"worker {worker_id} msg {i}",
                    )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert db.count_activity_logs() == 80
        db.close()


# ----------------------------------------------------------------------
# Temporary database usage
# ----------------------------------------------------------------------
class TestTemporaryDatabase:
    """Verify temporary databases can be created, populated, and queried."""

    def test_temp_db_lifecycle(self, tmp_path) -> None:
        db_path = tmp_path / "temp.db"
        db = Database(db_path)
        db.initialize()

        entry = LogEntry(
            level=LogLevel.INFO,
            event_type=LogEventType.SECURITY,
            user_prompt="prompt",
            sanitized_prompt="sanitized",
            risk_score=0.7,
            decision=LogDecision.WARNING,
        )
        log_id = db.insert_log_entry(entry)

        records = db.query_activity_logs(event_type="security")
        assert len(records) == 1
        assert records[0]["id"] == log_id

        events = db.query_security_events()
        assert len(events) == 1

        db.close()
        # Reopen the same path to confirm persistence.
        db2 = Database(db_path)
        db2.initialize()
        assert db2.count_activity_logs() == 1
        assert len(db2.query_security_events()) == 1
        db2.close()
