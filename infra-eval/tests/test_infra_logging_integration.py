"""
Integration tests verifying that :class:`SandboxManager` operations emit
structured logging events through the :mod:`logging_system` package.

These tests use a mocked Docker client (no real daemon required) and
capture log records via pytest's ``caplog`` fixture to assert that
container lifecycle events, command execution, and errors are logged
through the activity logging system.
"""

from __future__ import annotations

import logging

import pytest
from docker.errors import DockerException, NotFound

from infra.sandbox_manager import (
    ContainerNotFoundError,
    SandboxManager,
    SandboxManagerError,
)
from infra.container_config import default_config


@pytest.fixture
def manager(mocker) -> SandboxManager:
    """Build a SandboxManager with a mocked Docker client."""
    client = mocker.Mock()
    fake_container = mocker.Mock()
    fake_container.id = "abc123"
    fake_container.name = "infra-eval-sandbox"
    fake_container.status = "running"
    fake_container.attrs = {
        "State": {"Status": "running"},
        "Config": {"Image": "python:3.11-slim-bookworm"},
        "RestartCount": 0,
    }
    fake_container.exec_run.return_value = mocker.Mock(
        exit_code=0,
        output="hello world",
    )
    client.containers.create.return_value = fake_container
    client.containers.get.return_value = fake_container
    return SandboxManager(config=default_config(), client=client)


class TestContainerEventLogging:
    """Verify container lifecycle operations emit structured log events."""

    def test_start_container_logs_event(self, manager: SandboxManager, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="infra-eval"):
            container_id = manager.start_container()
        assert container_id == "abc123"
        # The structured event is emitted via the logging_system logger.
        assert any(
            "Container event: start" in r.message
            and getattr(r, "event_type", None) == "container"
            and getattr(r, "container_id", None) == "abc123"
            for r in caplog.records
        )

    def test_stop_container_logs_event(self, manager: SandboxManager, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="infra-eval"):
            assert manager.stop_container("abc123") is True
        assert any(
            "Container event: stop" in r.message
            and getattr(r, "event_type", None) == "container"
            and getattr(r, "container_id", None) == "abc123"
            for r in caplog.records
        )

    def test_restart_container_logs_event(self, manager: SandboxManager, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="infra-eval"):
            assert manager.restart_container("abc123") is True
        assert any(
            "Container event: restart" in r.message
            and getattr(r, "event_type", None) == "container"
            and getattr(r, "container_id", None) == "abc123"
            for r in caplog.records
        )

    def test_remove_container_logs_event(self, manager: SandboxManager, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="infra-eval"):
            assert manager.remove_container("abc123") is True
        assert any(
            "Container event: remove" in r.message
            and getattr(r, "event_type", None) == "container"
            and getattr(r, "container_id", None) == "abc123"
            for r in caplog.records
        )


class TestCommandExecutionLogging:
    """Verify command execution emits performance log events."""

    def test_execute_command_logs_performance(
        self, manager: SandboxManager, caplog
    ) -> None:
        with caplog.at_level(logging.INFO, logger="infra-eval"):
            result = manager.execute_command("abc123", ["echo", "hi"])
        assert result["exit_code"] == 0
        assert result["output"] == "hello world"
        assert any(
            "Performance metrics recorded" in r.message
            and getattr(r, "event_type", None) == "performance"
            and getattr(r, "container_id", None) == "abc123"
            and getattr(r, "tool_used", None) == "echo hi"
            for r in caplog.records
        )


class TestErrorLogging:
    """Verify errors are logged through the activity logging system."""

    def test_stop_missing_container_logs_error(
        self, manager: SandboxManager, caplog
    ) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with caplog.at_level(logging.ERROR, logger="infra-eval"):
            with pytest.raises(ContainerNotFoundError):
                manager.stop_container("nope")
        assert any(
            "Error:" in r.message
            and getattr(r, "event_type", None) == "error"
            and getattr(r, "container_id", None) == "nope"
            for r in caplog.records
        )

    def test_start_failure_logs_error(
        self, manager: SandboxManager, caplog
    ) -> None:
        manager.client.containers.create.side_effect = DockerException(
            "create failed"
        )
        with caplog.at_level(logging.ERROR, logger="infra-eval"):
            with pytest.raises(SandboxManagerError):
                manager.start_container()
        assert any(
            "Error:" in r.message
            and getattr(r, "event_type", None) == "error"
            for r in caplog.records
        )