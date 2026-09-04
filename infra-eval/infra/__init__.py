"""
Infrastructure: Docker Sandbox & Runtime Environment.

This package provides an independent Docker sandbox orchestration layer
for the Secure Autonomous AI Behavior Monitoring Sandbox project. It is
decoupled from LangChain, FastAPI, the frontend, and prompt detection so
other team members can import it as a standalone module.

Public API:
    - :class:`SandboxManager`: lifecycle orchestration for sandbox containers.
    - :class:`ContainerConfig`: declarative container runtime configuration.
    - :func:`default_config`: factory for a sensible default configuration.
"""

from .container_config import (
    ContainerConfig,
    NetworkMode,
    RestartPolicy,
    default_config,
)
from .docker_utils import (
    DockerNotAvailableError,
    build_host_config,
    create_client,
    ensure_image_exists,
    ensure_network_exists,
    is_docker_available,
    parse_memory_limit,
)
from .sandbox_manager import (
    ContainerNotFoundError,
    SandboxManager,
    SandboxManagerError,
)

__all__ = [
    "ContainerConfig",
    "ContainerNotFoundError",
    "DockerNotAvailableError",
    "NetworkMode",
    "RestartPolicy",
    "SandboxManager",
    "SandboxManagerError",
    "build_host_config",
    "create_client",
    "default_config",
    "ensure_image_exists",
    "ensure_network_exists",
    "is_docker_available",
    "parse_memory_limit",
]

__version__ = "0.1.0"
