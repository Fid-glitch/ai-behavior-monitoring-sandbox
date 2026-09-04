"""
Application settings module.

This module centralises all application configuration loaded
from environment variables and .env files using Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Project metadata
    PROJECT_NAME: str = "Secure Autonomous AI Behavior Monitoring Sandbox"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "sqlite:///./data/sandbox.db"
    DATABASE_ECHO: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: Optional[str] = None

    # Docker Sandbox
    DOCKER_NETWORK: str = "sandbox-net"
    SANDBOX_TIMEOUT_SECONDS: int = 300
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_LIMIT: float = 1.0

    # Monitoring
    METRICS_INTERVAL_SECONDS: int = 10
    HEALTH_CHECK_INTERVAL_SECONDS: int = 30

    # Evaluation
    EVALUATION_TIMEOUT_SECONDS: int = 600
    BENCHMARK_ITERATIONS: int = 3

    # Report
    REPORT_OUTPUT_DIR: str = "./reports/output"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

