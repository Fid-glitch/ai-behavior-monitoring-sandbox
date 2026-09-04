# Implementation TODO

## Step 2 — Docker Sandbox Infrastructure Module

- [x] 1. Create `infra/container_config.py` — Pydantic ContainerConfig model + default_config factory
- [x] 2. Create `infra/docker_utils.py` — Docker SDK helpers, resource parsing, availability
- [x] 3. Create `infra/sandbox_manager.py` — SandboxManager with lifecycle methods
- [x] 4. Update `infra/__init__.py` — export public API
- [x] 5. Update `infra/sandbox.py` — thin re-export alias
- [x] 6. Harden `Dockerfile` — HEALTHCHECK, ENTRYPOINT, non-root, TZ
- [x] 7. Align `docker-compose.yml` — env vars, healthcheck, resource limits, security
- [x] 8. Create `tests/test_container_config.py` — config defaults + validation tests
- [x] 9. Rewrite `tests/test_infra.py` — SandboxManager + docker_utils tests (mocked)
- [x] 10. Update `README.md` — Infrastructure module docs + file explanations
- [x] 11. Verify: run tests (pytest) — all 40 tests pass, exit code 0

## Step 3 — Activity Logging System

- [x] 1. Create `logging_system/log_models.py` — LogEntry model, LogDecision/LogLevel/LogEventType enums, factory methods
- [x] 2. Create `logging_system/log_formatter.py` — JSONFormatter + thread-safe CSVExporter
- [x] 3. Create `logging_system/logger_config.py` — LoggingConfig + setup_logging + rotating file handler
- [x] 4. Create `logging_system/activity_logger.py` — ActivityLogger class + reusable log_* functions + timed decorator
- [x] 5. Update `logging_system/__init__.py` — export public API + __version__
- [x] 6. Update `logging_system/logger.py` — backward-compatible re-export alias
- [x] 7. Create `tests/test_logging_system.py` — 26 tests (creation, JSON, CSV, exception, rotation, thread safety)
- [x] 8. Update `README.md` — Activity Logging System documentation
- [x] 9. Verify: run tests (pytest) — all 66 tests pass, ruff clean
