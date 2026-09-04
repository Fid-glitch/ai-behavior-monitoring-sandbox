"""
Secure Autonomous AI Behavior Monitoring Sandbox
Infrastructure & Evaluation Entrypoint

This is the main entrypoint for the infra-eval package. It initialises
the activity logging system, verifies Docker availability, and keeps the
process alive so the sandbox container remains running. The process
responds to SIGTERM/SIGINT for graceful shutdown.
"""

import logging
import signal
import sys
import time

from config.settings import settings
from infra import SandboxManager, is_docker_available
from logging_system import LoggingConfig, setup_logging

logger = logging.getLogger(__name__)

#: Interval (seconds) between idle-loop iterations.
IDLE_INTERVAL_SECONDS = 5.0

#: Flag set by signal handlers to request a graceful shutdown.
_shutdown_requested = False


def _handle_signal(signum: int, frame) -> None:
    """Mark that a graceful shutdown has been requested."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Received signal %s; shutting down gracefully", signum)


def _setup_signal_handlers() -> None:
    """Install SIGTERM/SIGINT handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _configure_logging() -> None:
    """Initialise the activity logging system from settings."""
    cfg = LoggingConfig(
        log_level=settings.LOG_LEVEL,
        file_enabled=bool(settings.LOG_FILE),
        file_path=settings.LOG_FILE or "logs/activity.log",
    )
    setup_logging(cfg)


def _run_idle_loop() -> None:
    """Keep the process alive until a shutdown signal is received."""
    logger.info("Entering idle loop (interval=%ss)", IDLE_INTERVAL_SECONDS)
    while not _shutdown_requested:
        time.sleep(IDLE_INTERVAL_SECONDS)
    logger.info("Shutdown requested; exiting idle loop")


def main() -> None:
    """Main entrypoint for the infra-eval application."""
    print("=" * 60)
    print("Secure Autonomous AI Behavior Monitoring Sandbox")
    print("Infrastructure & Evaluation Module")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    print(f"Environment: {settings.ENVIRONMENT}")
    print("=" * 60)

    _configure_logging()
    _setup_signal_handlers()

    logger.info("Starting infra-eval application (version=%s)", settings.VERSION)

    # Verify Docker availability so the sandbox can be orchestrated.
    if is_docker_available():
        logger.info("Docker daemon is available")
        manager = SandboxManager()
        logger.info(
            "Sandbox manager initialised (image=%s, network=%s)",
            manager.config.image,
            manager.config.network,
        )
    else:
        logger.warning("Docker daemon is not available; sandbox features disabled")

    logger.info("Application started successfully")
    _run_idle_loop()

    logger.info("Application stopped cleanly")


if __name__ == "__main__":
    main()