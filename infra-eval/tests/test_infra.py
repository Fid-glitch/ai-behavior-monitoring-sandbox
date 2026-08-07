"""
Unit tests for the Docker sandbox infrastructure.

Tests cover the :mod:`infra.docker_utils` helpers and the
:class:`infra.sandbox_manager.SandboxManager` lifecycle methods.
The Docker SDK is mocked so no real Docker daemon is required.
"""

from __future__ import annotations

import pytest
from docker.errors import DockerException, NotFound

from infra.container_config import ContainerConfig, default_config
from infra.docker_utils import (
    DockerNotAvailableError,
    create_client,
    is_docker_available,
    parse_memory_limit,
)
from infra.sandbox_manager import (
    ContainerNotFoundError,
    SandboxManager,
    SandboxManagerError,
)


# ----------------------------------------------------------------------
# docker_utils tests
# ----------------------------------------------------------------------
class TestParseMemoryLimit:
    """Tests for :func:`parse_memory_limit`."""

    def test_bytes(self) -> None:
        assert parse_memory_limit("512b") == 512

    def test_kilobytes(self) -> None:
        assert parse_memory_limit("1k") == 1024

    def test_megabytes(self) -> None:
        assert parse_memory_limit("512m") == 512 * 1024 * 1024

    def test_gigabytes_case_insensitive(self) -> None:
        assert parse_memory_limit("2G") == 2 * 1024 * 1024 * 1024

    def test_invalid_suffix(self) -> None:
        with pytest.raises(ValueError):
            parse_memory_limit("512x")

    def test_empty(self) -> None:
        with pytest.raises(ValueError):
            parse_memory_limit("")


class TestDockerUtils:
    """Tests for Docker client helpers."""

    def test_is_docker_available_returns_true(self, mocker) -> None:
        client = mocker.Mock()
        client.ping.return_value = None
        assert is_docker_available(client) is True

    def test_is_docker_available_returns_false(self, mocker) -> None:
        client = mocker.Mock()
        client.ping.side_effect = DockerException("daemon down")
        assert is_docker_available(client) is False

    def test_create_client_raises_on_failure(self, mocker) -> None:
        mocker.patch(
            "infra.docker_utils.docker.from_env",
            side_effect=DockerException("no daemon"),
        )
        with pytest.raises(DockerNotAvailableError):
            create_client()


# ----------------------------------------------------------------------
# SandboxManager tests
# ----------------------------------------------------------------------
@pytest.fixture
def manager(mocker) -> SandboxManager:
    """Build a SandboxManager with a mocked Docker client."""
    client = mocker.Mock()
    # A fake container object returned by client.containers.get/create.
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


class TestStartContainer:
    """Tests for :meth:`SandboxManager.start_container`."""

    def test_start_container_returns_id(self, manager: SandboxManager, mocker) -> None:
        result = manager.start_container()
        assert result == "abc123"
        manager.client.containers.create.assert_called_once()

    def test_start_container_failure_raises(self, manager: SandboxManager, mocker) -> None:
        manager.client.containers.create.side_effect = DockerException("create failed")
        with pytest.raises(SandboxManagerError):
            manager.start_container()


class TestStopContainer:
    """Tests for :meth:`SandboxManager.stop_container`."""

    def test_stop_running_container(self, manager: SandboxManager) -> None:
        assert manager.stop_container("abc123") is True
        container = manager.client.containers.get.return_value
        container.stop.assert_called_once_with(timeout=10)

    def test_stop_missing_container(self, manager: SandboxManager) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with pytest.raises(ContainerNotFoundError):
            manager.stop_container("nope")


class TestRemoveContainer:
    """Tests for :meth:`SandboxManager.remove_container`."""

    def test_remove_container(self, manager: SandboxManager) -> None:
        assert manager.remove_container("abc123") is True
        container = manager.client.containers.get.return_value
        container.remove.assert_called_once_with(force=True, v=False)

    def test_remove_missing_container(self, manager: SandboxManager) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with pytest.raises(ContainerNotFoundError):
            manager.remove_container("nope")


class TestRestartContainer:
    """Tests for :meth:`SandboxManager.restart_container`."""

    def test_restart_container(self, manager: SandboxManager) -> None:
        assert manager.restart_container("abc123") is True
        container = manager.client.containers.get.return_value
        container.restart.assert_called_once_with(timeout=10)

    def test_restart_missing_container(self, manager: SandboxManager) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with pytest.raises(ContainerNotFoundError):
            manager.restart_container("nope")


class TestGetContainerStatus:
    """Tests for :meth:`SandboxManager.get_container_status`."""

    def test_status_dict(self, manager: SandboxManager) -> None:
        status = manager.get_container_status("abc123")
        assert status["id"] == "abc123"
        assert status["status"] == "running"
        assert status["image"] == "python:3.11-slim-bookworm"

    def test_status_missing_container(self, manager: SandboxManager) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with pytest.raises(ContainerNotFoundError):
            manager.get_container_status("nope")


class TestExecuteCommand:
    """Tests for :meth:`SandboxManager.execute_command`."""

    def test_execute_command_success(self, manager: SandboxManager) -> None:
        result = manager.execute_command("abc123", ["echo", "hi"])
        assert result["exit_code"] == 0
        assert result["output"] == "hello world"

    def test_execute_command_missing_container(self, manager: SandboxManager) -> None:
        manager.client.containers.get.side_effect = NotFound("missing")
        with pytest.raises(ContainerNotFoundError):
            manager.execute_command("nope", ["ls"])


class TestSandboxManagerConfig:
    """Tests for SandboxManager construction and config handling."""

    def test_default_config_is_used(self, mocker) -> None:
        client = mocker.Mock()
        manager = SandboxManager(client=client)
        assert isinstance(manager.config, ContainerConfig)

    def test_custom_config_is_used(self, mocker) -> None:
        client = mocker.Mock()
        cfg = default_config(name="my-custom")
        manager = SandboxManager(config=cfg, client=client)
        assert manager.config.name == "my-custom"
