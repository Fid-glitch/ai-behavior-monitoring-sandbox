"""
Container configuration module.

Defines the ``ContainerConfig`` model used to describe how a sandbox
container should be created and run. This module is intentionally
independent of other project modules so it can be imported by other
team members without coupling to the rest of the codebase.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class RestartPolicy(str, Enum):
    """Supported Docker restart policies."""

    NO = "no"
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    UNLESS_STOPPED = "unless-stopped"


class NetworkMode(str, Enum):
    """Supported Docker network modes."""

    BRIDGE = "bridge"
    HOST = "host"
    NONE = "none"


class ContainerConfig(BaseModel):
    """
    Configuration for a sandbox container.

    Attributes:
        image: Docker image to run (e.g. ``"python:3.11-slim"``).
        name: Optional container name.
        command: Override the default command of the image.
        environment: Mapping of environment variables to set.
        volumes: List of volume bindings in ``host:container`` form.
        network: Docker network name or mode to attach.
        network_mode: High level network mode (bridge/host/none).
        cpu_limit: CPU limit as a float (number of CPUs).
        memory_limit: Memory limit as a string (e.g. ``"512m"``).
        restart_policy: Restart policy for the container.
        working_dir: Working directory inside the container.
        user: User/UID to run the container as.
        security_opt: List of Docker security options.
        cap_drop: Linux capabilities to drop.
        pull_policy: Whether to always pull the image.
        labels: Metadata labels to attach.
        timeout_seconds: Default command execution timeout.
    """

    image: str = "python:3.11-slim-bookworm"
    name: Optional[str] = None
    command: Optional[List[str]] = None
    environment: Dict[str, str] = Field(default_factory=dict)
    volumes: List[str] = Field(default_factory=list)
    network: str = "sandbox-net"
    network_mode: NetworkMode = NetworkMode.BRIDGE
    cpu_limit: float = Field(default=1.0, gt=0.0, le=64.0)
    memory_limit: str = "512m"
    restart_policy: RestartPolicy = RestartPolicy.UNLESS_STOPPED
    working_dir: str = "/app"
    user: str = "sandbox"
    security_opt: List[str] = Field(
        default_factory=lambda: ["no-new-privileges:true"]
    )
    cap_drop: List[str] = Field(default_factory=lambda: ["ALL"])
    pull_policy: str = "missing"
    labels: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=1)

    @field_validator("memory_limit")
    @classmethod
    def _validate_memory_limit(cls, value: str) -> str:
        """Validate that the memory limit uses a supported suffix."""
        if len(value) < 2 or value[-1] not in "kmgKMGs":
            raise ValueError(
                "memory_limit must be a size with a suffix, e.g. '512m', '1g'"
            )
        if not value[:-1].isdigit():
            raise ValueError("memory_limit must be a number followed by a suffix")
        return value.lower()

    @field_validator("volumes")
    @classmethod
    def _validate_volumes(cls, value: List[str]) -> List[str]:
        """Ensure each volume is in ``host:container`` form."""
        for vol in value:
            if ":" not in vol:
                raise ValueError(f"Volume '{vol}' must be in 'host:container' form")
        return value

    @model_validator(mode="after")
    def _validate_network_mode(self) -> "ContainerConfig":
        """Ensure an explicit network name is not set when using host/none mode."""
        if self.network_mode in (NetworkMode.HOST, NetworkMode.NONE) and self.network:
            raise ValueError(
                f"Cannot set network '{self.network}' with mode '{self.network_mode.value}'"
            )
        return self

    def to_docker_host_config(self) -> Dict[str, Any]:
        """
        Return a dict suitable for the Docker SDK ``host_config`` parameter.

        Returns:
            Dictionary with CPU, memory, restart, and security settings.
        """
        return {
            "CpuQuota": int(self.cpu_limit * 100000),
            "CpuPeriod": 100000,
            "MemLimit": self.memory_limit,
            "RestartPolicy": {"Name": self.restart_policy.value},
            "SecurityOpt": self.security_opt,
            "CapDrop": self.cap_drop,
        }

    def to_docker_create_kwargs(self) -> Dict[str, Any]:
        """
        Return a dict suitable for the Docker SDK ``containers.create`` call.

        Returns:
            Keyword arguments for ``client.containers.create``.
        """
        return {
            "image": self.image,
            "name": self.name,
            "command": self.command,
            "environment": self.environment,
            "volumes": self.volumes,
            "network": self.network,
            "working_dir": self.working_dir,
            "user": self.user,
            "labels": self.labels,
        }


def default_config(**overrides: Any) -> ContainerConfig:
    """
    Build a :class:`ContainerConfig` with sensible sandbox defaults.

    Args:
        **overrides: Field values to override on the default configuration.

    Returns:
        A configured :class:`ContainerConfig` instance.
    """
    defaults: Dict[str, Any] = {
        "image": "python:3.11-slim-bookworm",
        "name": "infra-eval-sandbox",
        "environment": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": "/app",
        },
        "volumes": [
            "/app/data:/app/data",
            "/app/logs:/app/logs",
        ],
        "network": "sandbox-net",
        "cpu_limit": 1.0,
        "memory_limit": "512m",
        "restart_policy": RestartPolicy.UNLESS_STOPPED,
        "working_dir": "/app",
        "user": "sandbox",
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "labels": {
            "app": "infra-eval",
            "component": "sandbox",
            "managed-by": "sandbox-manager",
        },
        "timeout_seconds": 300,
    }
    defaults.update(overrides)
    return ContainerConfig(**defaults)
