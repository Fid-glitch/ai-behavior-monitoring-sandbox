"""
Configuration loader module.

Provides utility functions to load, validate, and manage
configuration for different environments (development, staging, production).
"""

from pathlib import Path
from typing import Dict, Any, Optional
import os

from .settings import settings


def get_config() -> Dict[str, Any]:
    """Return the current active configuration as a dictionary."""
    return settings.model_dump()


def get_data_dir() -> Path:
    """Return the path to the data directory, creating it if necessary."""
    data_dir = Path.cwd() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir() -> Path:
    """Return the path to the log directory, creating it if necessary."""
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def is_development() -> bool:
    """Check if the current environment is development."""
    return settings.ENVIRONMENT.lower() == "development"


def is_production() -> bool:
    """Check if the current environment is production."""
    return settings.ENVIRONMENT.lower() == "production"


def validate_config() -> bool:
    """
    Validate critical configuration values.

    Returns:
        True if configuration is valid, raises ValueError otherwise.
    """
    required_vars = [
        "DATABASE_URL",
    ]
    missing = [var for var in required_vars if not getattr(settings, var, None)]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")

    if settings.SANDBOX_TIMEOUT_SECONDS < 1:
        raise ValueError("SANDBOX_TIMEOUT_SECONDS must be >= 1")

    if settings.EVALUATION_TIMEOUT_SECONDS < 1:
        raise ValueError("EVALUATION_TIMEOUT_SECONDS must be >= 1")

    return True

