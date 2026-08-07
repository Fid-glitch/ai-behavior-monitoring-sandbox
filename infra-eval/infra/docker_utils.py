"""
Docker utility helpers.

Low-level helpers around the official Docker Python SDK. These functions
abstract client creation, resource parsing, and precondition checks so the
:mod:`infra.sandbox_manager` module can stay focused on orchestration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from .container_config import ContainerConfig

logger = logging.getLogger(__name__)


class DockerNotAvailableError(RuntimeError):
    """Raised when the Docker daemon is unreachable or the SDK is missing."""


def create_client(
    base_url: Optional[str] = None,
    timeout_seconds: int = 60,
) -> docker.DockerClient:
    """
    Create and return a Docker SDK client.

    Args:
        base_url: Optional Docker daemon URL. Defaults to the local socket.
        timeout_seconds: Client request timeout in seconds.

    Returns:
        A configured ``docker.DockerClient``.

    Raises:
        DockerNotAvailableError: If the client cannot be created.
    """
    try:
        client = docker.from_env(env={"DOCKER_HOST": base_url} if base_url else None)
        client.api.timeout = timeout_seconds
        return client
    except (DockerException, OSError, ValueError) as exc:
        logger.error("Failed to create Docker client: %s", exc)
        raise DockerNotAvailableError(f"Could not initialise Docker client: {exc}") from exc


def is_docker_available(client: Optional[docker.DockerClient] = None) -> bool:
    """
    Check whether the Docker daemon is reachable.

    Args:
        client: Optional existing client. A new one is created if omitted.

    Returns:
        ``True`` if Docker responds to a ping, ``False`` otherwise.
    """
    close_after = False
    try:
        if client is None:
            client = create_client()
            close_after = True
        client.ping()
        return True
    except (DockerException, DockerNotAvailableError):
        return False
    finally:
        if close_after:
            try:
                client.close()
            except Exception:
                logger.debug("Failed to close Docker client", exc_info=True)


def parse_memory_limit(memory_limit: str) -> int:
    """
    Convert a memory limit string into bytes.

    Supports suffixes ``b``, ``k``, ``m``, ``g`` (case-insensitive).

    Args:
        memory_limit: Memory value such as ``"512m"`` or ``"1g"``.

    Returns:
        The equivalent number of bytes.

    Raises:
        ValueError: If the value cannot be parsed.
    """
    units = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
    value = memory_limit.strip().lower()
    if len(value) < 2:
        raise ValueError(f"Invalid memory limit: {memory_limit!r}")
    suffix = value[-1]
    if suffix not in units:
        raise ValueError(f"Unsupported memory suffix in: {memory_limit!r}")
    if not value[:-1].isdigit():
        raise ValueError(f"Invalid memory limit: {memory_limit!r}")
    return int(value[:-1]) * units[suffix]


def ensure_image_exists(
    client: docker.DockerClient,
    config: ContainerConfig,
    force_pull: bool = False,
) -> str:
    """
    Ensure the configured image is present locally, pulling it if needed.

    Args:
        client: Docker client to use.
        config: Container configuration describing the image.
        force_pull: Always pull even if the image is already present.

    Returns:
        The image tag that was ensured.

    Raises:
        DockerException: If the image cannot be pulled.
    """
    try:
        client.images.get(config.image)
    except ImageNotFound:
        logger.info("Image '%s' not found locally, pulling...", config.image)
    except DockerException as exc:
        logger.error("Failed to inspect image '%s': %s", config.image, exc)
        raise
    else:
        if not force_pull:
            logger.debug("Image '%s' already present", config.image)
            return config.image

    logger.info("Pulling image '%s'", config.image)
    client.images.pull(config.image)
    logger.info("Image '%s' pulled successfully", config.image)
    return config.image


def ensure_network_exists(
    client: docker.DockerClient,
    network: str,
    driver: str = "bridge",
) -> str:
    """
    Ensure a named Docker network exists, creating it if necessary.

    Args:
        client: Docker client to use.
        network: Name of the network.
        driver: Network driver to use when creating.

    Returns:
        The network name.

    Raises:
        DockerException: If the network cannot be created.
    """
    try:
        client.networks.get(network)
    except NotFound:
        pass
    else:
        logger.debug("Network '%s' already exists", network)
        return network

    logger.info("Creating network '%s' with driver '%s'", network, driver)
    client.networks.create(network, driver=driver)
    logger.info("Network '%s' created", network)
    return network


def build_host_config(config: ContainerConfig) -> Dict[str, Any]:
    """
    Build a Docker ``host_config`` dict from a :class:`ContainerConfig`.

    Args:
        config: The container configuration.

    Returns:
        A dictionary suitable for the ``host_config`` parameter.
    """
    return config.to_docker_host_config()
