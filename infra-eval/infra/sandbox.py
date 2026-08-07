"""
Backward-compatible alias for the sandbox infrastructure.

This module re-exports the canonical :class:`SandboxManager` and related
symbols from :mod:`infra.sandbox_manager` so existing imports such as
``from infra.sandbox import SandboxManager`` keep working. New code should
import from :mod:`infra.sandbox_manager` directly.
"""

from __future__ import annotations

from .container_config import ContainerConfig, default_config
from .docker_utils import DockerNotAvailableError
from .sandbox_manager import (
    ContainerNotFoundError,
    SandboxManager,
    SandboxManagerError,
)

__all__ = [
    "ContainerConfig",
    "ContainerNotFoundError",
    "DockerNotAvailableError",
    "SandboxManager",
    "SandboxManagerError",
    "default_config",
]
