"""
Unit tests for the :mod:`infra.container_config` module.

These tests verify the defaults, validation rules, and serialization
helpers of the :class:`ContainerConfig` model. No Docker daemon is
required to run this suite.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from infra.container_config import (
    ContainerConfig,
    NetworkMode,
    RestartPolicy,
    default_config,
)


class TestDefaultConfig:
    """Tests for the default sandbox configuration."""

    def test_default_image(self) -> None:
        """The default image should target Python 3.11 slim."""
        cfg = default_config()
        assert cfg.image == "python:3.11-slim-bookworm"

    def test_default_name(self) -> None:
        """The default container name should be set."""
        cfg = default_config()
        assert cfg.name == "infra-eval-sandbox"

    def test_default_resource_limits(self) -> None:
        """Default CPU and memory limits should be sane."""
        cfg = default_config()
        assert cfg.cpu_limit == 1.0
        assert cfg.memory_limit == "512m"

    def test_default_restart_policy(self) -> None:
        """Default restart policy should be unless-stopped."""
        cfg = default_config()
        assert cfg.restart_policy == RestartPolicy.UNLESS_STOPPED

    def test_default_network(self) -> None:
        """Default network and mode should be bridge/sandbox-net."""
        cfg = default_config()
        assert cfg.network == "sandbox-net"
        assert cfg.network_mode == NetworkMode.BRIDGE

    def test_default_security(self) -> None:
        """Default security options should drop all capabilities."""
        cfg = default_config()
        assert "no-new-privileges:true" in cfg.security_opt
        assert cfg.cap_drop == ["ALL"]

    def test_default_environment(self) -> None:
        """Default Python runtime environment should be set."""
        cfg = default_config()
        assert cfg.environment["PYTHONUNBUFFERED"] == "1"
        assert cfg.environment["PYTHONPATH"] == "/app"

    def test_overrides_are_applied(self) -> None:
        """Keyword overrides should replace defaults."""
        cfg = default_config(name="custom-sandbox", cpu_limit=2.0)
        assert cfg.name == "custom-sandbox"
        assert cfg.cpu_limit == 2.0


class TestValidation:
    """Tests for ContainerConfig field validation."""

    def test_invalid_memory_limit_no_suffix(self) -> None:
        """A memory limit without a suffix should be rejected."""
        with pytest.raises(ValidationError):
            ContainerConfig(memory_limit="512")

    def test_invalid_memory_limit_non_numeric(self) -> None:
        """A non-numeric memory limit should be rejected."""
        with pytest.raises(ValidationError):
            ContainerConfig(memory_limit="abm")

    def test_invalid_volume_format(self) -> None:
        """A volume without a colon should be rejected."""
        with pytest.raises(ValidationError):
            ContainerConfig(volumes=["/data"])

    def test_valid_volume(self) -> None:
        """A host:container volume should be accepted."""
        cfg = ContainerConfig(volumes=["/host/data:/container/data"])
        assert cfg.volumes == ["/host/data:/container/data"]

    def test_cpu_limit_must_be_positive(self) -> None:
        """A non-positive CPU limit should be rejected."""
        with pytest.raises(ValidationError):
            ContainerConfig(cpu_limit=0)

    def test_host_mode_with_network_rejected(self) -> None:
        """Host network mode with an explicit network should fail."""
        with pytest.raises(ValidationError):
            ContainerConfig(network_mode=NetworkMode.HOST, network="sandbox-net")

    def test_none_mode_with_network_rejected(self) -> None:
        """None network mode with an explicit network should fail."""
        with pytest.raises(ValidationError):
            ContainerConfig(network_mode=NetworkMode.NONE, network="sandbox-net")


class TestSerialization:
    """Tests for the Docker SDK serialization helpers."""

    def test_host_config_contains_resource_settings(self) -> None:
        """Host config should include CPU, memory, and security settings."""
        cfg = default_config()
        host = cfg.to_docker_host_config()
        assert host["CpuPeriod"] == 100000
        assert host["CpuQuota"] == 100000
        assert host["MemLimit"] == "512m"
        assert host["RestartPolicy"] == {"Name": "unless-stopped"}
        assert host["CapDrop"] == ["ALL"]

    def test_create_kwargs(self) -> None:
        """Create kwargs should include core container settings."""
        cfg = default_config()
        kwargs = cfg.to_docker_create_kwargs()
        assert kwargs["image"] == "python:3.11-slim-bookworm"
        assert kwargs["name"] == "infra-eval-sandbox"
        assert kwargs["working_dir"] == "/app"
        assert kwargs["user"] == "sandbox"
        assert kwargs["network"] == "sandbox-net"
