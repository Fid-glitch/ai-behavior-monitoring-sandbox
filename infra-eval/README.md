# infra-eval

**Infrastructure, Docker Sandbox, Monitoring, Evaluation, and Reporting package** for the **Secure Autonomous AI Behavior Monitoring Sandbox** project.

---

## Overview

This package is maintained by **Member 4** of the B.Tech final year project team. It is the backbone for:

- **Infrastructure** – Docker sandbox orchestration and secure runtime environments.
- **Logging System** – Structured activity logging for all system events.
- **Database** – SQLite persistence layer for evaluation data and logs.
- **Monitoring** – Performance metrics collection and health checks.
- **Evaluation Framework** – Benchmark testing and risk analytics validation.
- **Report Generation** – Automated report creation from evaluation results.

---

## Project Structure

```
infra-eval/
├── infra/              # Docker sandbox & runtime management
├── logging_system/     # Structured activity logging
├── database/           # SQLite database layer
├── monitor/            # Performance & health monitoring
├── evaluation/         # Benchmark & evaluation framework
├── reports/            # Report generation
├── config/             # Configuration management (Pydantic)
├── utils/              # Shared utilities
├── tests/              # Unit & integration tests
├── docs/               # Documentation
├── main.py             # Application entrypoint
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container build instructions
├── docker-compose.yml  # Multi-service orchestration
├── .env.example        # Environment variable template
└── .gitignore          # Git ignore rules
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for sandbox features)

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd infra-eval

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment variables
cp .env.example .env

# 5. Run the application
python main.py
```

---

## Development

### Code Quality

```bash
# Format code
black .

# Lint
ruff check .

# Type check
mypy .

# Sort imports
isort .
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=.
```

---

## Docker

```bash
# Build and run
docker compose up --build

# Run in background
docker compose up -d

# Stop
docker compose down
```

---

## Infrastructure Module (Docker Sandbox)

The `infra/` package is a **self-contained, independent** Docker sandbox
management layer. It has **no** dependency on LangChain, FastAPI, the
frontend, or prompt detection — other team members can import it directly.

### Module layout

```
infra/
├── container_config.py   # Declarative container runtime configuration (Pydantic)
├── docker_utils.py       # Low-level Docker SDK helpers & preconditions
├── sandbox_manager.py    # High-level container lifecycle orchestration
├── sandbox.py            # Backward-compatible alias (re-exports)
└── __init__.py           # Public API exports + package version
```

### File responsibilities

| File | Purpose |
|------|---------|
| `infra/container_config.py` | Defines the `ContainerConfig` Pydantic model and the `default_config()` factory. Centralises image, CPU/memory limits, restart policy, network, volumes, security options, and environment variables. |
| `infra/docker_utils.py` | Wraps the official Docker SDK: client creation, availability checks, memory-limit parsing, image/network preconditions, and host-config building. |
| `infra/sandbox_manager.py` | Provides the `SandboxManager` class with `start_container`, `stop_container`, `remove_container`, `restart_container`, `get_container_status`, and `execute_command`. Includes structured logging and exception handling. |
| `infra/sandbox.py` | Compatibility alias so existing imports such as `from infra.sandbox import SandboxManager` keep working. |
| `infra/__init__.py` | Exports the public API and `__version__`. |

### Usage

```python
from infra import SandboxManager, default_config

manager = SandboxManager(config=default_config())

# Start a sandbox container
container_id = manager.start_container()

# Run a command inside it
result = manager.execute_command(container_id, ["echo", "hello"])

# Inspect status
status = manager.get_container_status(container_id)

# Stop and remove
manager.stop_container(container_id)
manager.remove_container(container_id)
```

Error handling: operations raise `SandboxManagerError` subclasses
(`ContainerNotFoundError` for missing containers). Every lifecycle event
is logged via the standard `logging` module.

### Dockerfile & docker-compose

- **`Dockerfile`** — Multi-stage build (builder → runtime). Installs
  dependencies in a builder stage, runs Python 3.11 as a non-root
  `sandbox` user, drops capabilities, sets a health check, and pins UTC.
- **`docker-compose.yml`** — Defines the `sandbox` service with CPU and
  memory limits, `unless-stopped` restart policy, named volumes for
  data/logs/reports, a read-only Docker socket mount, an isolated bridge
  network, security options, a health check, and log rotation.

### Tests

```bash
# Run the infra test suites (no real Docker daemon needed)
pytest tests/test_container_config.py tests/test_infra.py -v
```

---

## Activity Logging System

The `logging_system/` package provides a **production-ready, thread-safe
activity logging layer** for every stage of the AI behaviour monitoring
pipeline. It is a self-contained module built on the standard library
`logging` module plus Pydantic for configuration.

### Module layout

```
logging_system/
├── activity_logger.py   # Reusable logging functions + ActivityLogger class
├── logger_config.py     # LoggingConfig + setup_logging + rotating handlers
├── log_formatter.py     # JSONFormatter + thread-safe CSVExporter
├── log_models.py        # LogEntry model, enums, factory methods
├── logger.py            # Backward-compatible alias (re-exports)
└── __init__.py          # Public API exports + package version
```

### File responsibilities

| File | Purpose |
|------|---------|
| `logging_system/log_models.py` | Defines the `LogEntry` dataclass with all recorded fields, the `LogDecision` (ALLOW/BLOCK/WARNING), `LogLevel`, and `LogEventType` enums, plus factory methods `create_error_entry`, `create_security_entry`, and `create_performance_entry`. |
| `logging_system/log_formatter.py` | Provides the `JSONFormatter` (serialises log records to JSON lines) and the thread-safe `CSVExporter` (converts JSON logs to CSV, exports rows/entries, reads back). |
| `logging_system/logger_config.py` | Defines the `LoggingConfig` Pydantic model and `setup_logging()` which wires up console, file, and `RotatingFileHandler` (size-based rotation with backups) handlers. |
| `logging_system/activity_logger.py` | Provides the `ActivityLogger` class and the module-level functions `log_request`, `log_response`, `log_security_event`, `log_container_event`, `log_performance`, `log_error`, and `log_system_event`, plus a `timed` decorator. |
| `logging_system/logger.py` | Backward-compatible alias re-exporting the public API for existing imports. |
| `logging_system/__init__.py` | Exports the public API and `__version__`. |

### Recorded fields

Each structured log entry captures: `timestamp`, `user_prompt`,
`sanitized_prompt`, `ai_response`, `tool_used`, `risk_score`, `decision`,
`execution_time_ms`, `cpu_usage_percent`, `memory_usage_mb`, `container_id`,
`status`, and `error_message`.

### Usage

```python
from logging_system import (
    LogDecision,
    LoggingConfig,
    log_container_event,
    log_error,
    log_performance,
    log_request,
    log_response,
    log_security_event,
    setup_logging,
)

# Initialise once (console + rotating JSON file output)
setup_logging(
    LoggingConfig(log_level="INFO", file_enabled=True,
                  file_path="logs/activity.log")
)

# Record pipeline events
log_request("Hello", sanitized_prompt="Hello", container_id="abc123")
log_response("Response text", risk_score=0.1, decision=LogDecision.ALLOW,
             container_id="abc123")
log_security_event("Ignore prior instructions",
                   "Ignore prior instructions", 0.95, LogDecision.BLOCK)
log_container_event("start", "abc123")
log_performance(execution_time_ms=12.5, cpu_usage_percent=3.1,
                memory_usage_mb=64.0)
try:
    1 / 0
except ZeroDivisionError as exc:
    log_error(exc, container_id="abc123")
```

### CSV export

```python
from logging_system import CSVExporter

exporter = CSVExporter()
exporter.export_file("logs/activity.log", "logs/activity.csv")
```

### Tests

```bash
# Run the logging test suite (26 tests)
pytest tests/test_logging_system.py -v
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment | `development` |
| `DATABASE_URL` | SQLite connection string | `sqlite:///./data/sandbox.db` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DOCKER_NETWORK` | Docker network name | `sandbox-net` |

See `.env.example` for a full list.

---

## License

MIT — Project use only.

