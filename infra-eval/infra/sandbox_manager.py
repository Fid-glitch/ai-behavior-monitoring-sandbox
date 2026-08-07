"""
Sandbox manager module.

Provides the :class:`SandboxManager`, a high-level orchestrator for the
Docker sandbox lifecycle. It is built on the official Docker Python SDK and
is fully independent of the rest of the project so it can be imported by
other team members without coupling to LangChain, FastAPI, or detection code.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import docker
from docker.errors import (
    ContainerError,
    DockerException,
    NotFound,
)

from .container_config import ContainerConfig, default_config
from .docker_utils import (
    DockerNotAvailableError,
    build_host_config,
    create_client,
    ensure_image_exists,
    ensure_network_exists,
)

logger = logging.getLogger(__name__)


class SandboxManagerError(RuntimeError):
    """Base exception for sandbox manager failures."""


class ContainerNotFoundError(SandboxManagerError):
    """Raised when the target container does not exist."""


class SandboxManager:
    """
    Orchestrates the lifecycle of Docker sandbox containers.

    Args:
        config: Container configuration to use. Defaults to a sensible
            sandbox configuration when omitted.
        client: Optional pre-created Docker client. A client is created
            from the local environment when omitted.
    """

    def __init__(
        self,
        config: Optional[ContainerConfig] = None,
        client: Optional[docker.DockerClient] = None,
    ) -> None:
        self.config = config or default_config()
        self.client = client or create_client()
        self.network_name: str = self.config.network

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------
    def start_container(
        self,
        config: Optional[ContainerConfig] = None,
        pull_image: bool = True,
    ) -> str:
        """
        Create and start a sandbox container.

        Args:
            config: Optional configuration override for this launch.
            pull_image: Whether to pull the image if not present locally.

        Returns:
            The container ID of the started container.

        Raises:
            SandboxManagerError: If the container cannot be started.
        """
        cfg = config or self.config
        try:
            if pull_image:
                ensure_image_exists(self.client, cfg)

            ensure_network_exists(self.client, self.network_name)

            host_config = build_host_config(cfg)
            create_kwargs = cfg.to_docker_create_kwargs()

            logger.info("Creating sandbox container from image '%s'", cfg.image)
            container = self.client.containers.create(
                host_config=host_config,
                **create_kwargs,
            )
            try:
                logger.info(
                    "Starting sandbox container '%s' (%s)",
                    cfg.name,
                    container.id,
                )
                container.start()
            except Exception:
                logger.exception(
                    "Start failed for container '%s'; removing it to avoid an orphan",
                    container.id,
                )
                try:
                    container.remove(force=True)
                except DockerException as cleanup_exc:
                    logger.error(
                        "Failed to remove orphaned container '%s': %s",
                        container.id,
                        cleanup_exc,
                    )
                raise
            logger.info("Sandbox container '%s' started", container.id)
            return container.id
        except (DockerException, DockerNotAvailableError, OSError) as exc:
            logger.error("Failed to start sandbox container: %s", exc)
            raise SandboxManagerError(f"Failed to start container: {exc}") from exc

    def stop_container(
        self,
        container_id: str,
        timeout: int = 10,
    ) -> bool:
        """
        Stop a running sandbox container.

        Args:
            container_id: ID or name of the container to stop.
            timeout: Seconds to wait for graceful shutdown.

        Returns:
            ``True`` if the container was stopped.

        Raises:
            ContainerNotFoundError: If the container does not exist.
            SandboxManagerError: On any other failure.
        """
        try:
            container = self.client.containers.get(container_id)
            logger.info("Stopping sandbox container '%s'", container_id)
            container.stop(timeout=timeout)
            logger.info("Sandbox container '%s' stopped", container_id)
            return True
        except NotFound as exc:
            logger.warning("Container '%s' not found", container_id)
            raise ContainerNotFoundError(f"Container '{container_id}' not found") from exc
        except DockerException as exc:
            logger.error("Failed to stop container '%s': %s", container_id, exc)
            raise SandboxManagerError(f"Failed to stop container: {exc}") from exc

    def remove_container(
        self,
        container_id: str,
        force: bool = True,
        remove_volumes: bool = False,
    ) -> bool:
        """
        Remove a sandbox container.

        Args:
            container_id: ID or name of the container to remove.
            force: Force removal even if running.
            remove_volumes: Also remove anonymous volumes.

        Returns:
            ``True`` if the container was removed.

        Raises:
            ContainerNotFoundError: If the container does not exist.
            SandboxManagerError: On any other failure.
        """
        try:
            container = self.client.containers.get(container_id)
            logger.info("Removing sandbox container '%s'", container_id)
            container.remove(force=force, v=remove_volumes)
            logger.info("Sandbox container '%s' removed", container_id)
            return True
        except NotFound as exc:
            logger.warning("Container '%s' not found", container_id)
            raise ContainerNotFoundError(f"Container '{container_id}' not found") from exc
        except DockerException as exc:
            logger.error("Failed to remove container '%s': %s", container_id, exc)
            raise SandboxManagerError(f"Failed to remove container: {exc}") from exc

    def restart_container(
        self,
        container_id: str,
        timeout: int = 10,
    ) -> bool:
        """
        Restart a sandbox container.

        Args:
            container_id: ID or name of the container to restart.
            timeout: Seconds to wait before force-restarting.

        Returns:
            ``True`` if the container was restarted.

        Raises:
            ContainerNotFoundError: If the container does not exist.
            SandboxManagerError: On any other failure.
        """
        try:
            container = self.client.containers.get(container_id)
            logger.info("Restarting sandbox container '%s'", container_id)
            container.restart(timeout=timeout)
            logger.info("Sandbox container '%s' restarted", container_id)
            return True
        except NotFound as exc:
            logger.warning("Container '%s' not found", container_id)
            raise ContainerNotFoundError(f"Container '{container_id}' not found") from exc
        except DockerException as exc:
            logger.error("Failed to restart container '%s': %s", container_id, exc)
            raise SandboxManagerError(f"Failed to restart container: {exc}") from exc

    def get_container_status(
        self,
        container_id: str,
    ) -> Dict[str, Any]:
        """
        Retrieve the current status of a sandbox container.

        Args:
            container_id: ID or name of the container to inspect.

        Returns:
            A dictionary with status, state, and resource settings.

        Raises:
            ContainerNotFoundError: If the container does not exist.
            SandboxManagerError: On any other failure.
        """
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            status = {
                "id": container.id,
                "name": container.name,
                "status": container.status,
                "state": container.attrs.get("State", {}),
                "image": container.attrs.get("Config", {}).get("Image", ""),
                "restarting": container.attrs.get("RestartCount", 0),
            }
            logger.info(
                "Retrieved status for container '%s': %s",
                container_id,
                status["status"],
            )
            return status
        except NotFound as exc:
            logger.warning("Container '%s' not found", container_id)
            raise ContainerNotFoundError(f"Container '{container_id}' not found") from exc
        except DockerException as exc:
            logger.error("Failed to get status for '%s': %s", container_id, exc)
            raise SandboxManagerError(f"Failed to get container status: {exc}") from exc

    def execute_command(
        self,
        container_id: str,
        command: List[str],
        detach: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a command inside a sandbox container.

        Args:
            container_id: ID or name of the target container.
            command: Command (and arguments) to execute.
            detach: Run the command in the background.

        Returns:
            A dictionary containing ``exit_code``, ``output``, and ``error``.

        Raises:
            ContainerNotFoundError: If the container does not exist.
            SandboxManagerError: On any other failure.
        """
        try:
            container = self.client.containers.get(container_id)
            logger.info(
                "Executing command %s in container '%s' (detach=%s)",
                command,
                container_id,
                detach,
            )
            result = container.exec_run(
                cmd=command,
                detach=detach,
                stdout=True,
                stderr=True,
            )
            exit_code = result.exit_code
            output = result.output
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            payload = {
                "exit_code": exit_code,
                "output": output,
                "detached": detach,
            }
            logger.info(
                "Command in container '%s' finished with exit code %s",
                container_id,
                exit_code,
            )
            return payload
        except NotFound as exc:
            logger.warning("Container '%s' not found", container_id)
            raise ContainerNotFoundError(f"Container '{container_id}' not found") from exc
        except (ContainerError, DockerException) as exc:
            logger.error("Failed to execute command in '%s': %s", container_id, exc)
            raise SandboxManagerError(f"Failed to execute command: {exc}") from exc

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def list_containers(self, all: bool = True) -> List[Dict[str, Any]]:
        """
        List sandbox containers managed by this module.

        Args:
            all: Include stopped containers when ``True``.

        Returns:
            A list of dictionaries with container ID, name, and status.
        """
        containers = self.client.containers.list(
            all=all,
            filters={"label": "managed-by=sandbox-manager"},
        )
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
            }
            for c in containers
        ]

    def close(self) -> None:
        """Close the underlying Docker client connection."""
        try:
            self.client.close()
        except Exception:
            logger.debug("Docker client already closed", exc_info=True)
