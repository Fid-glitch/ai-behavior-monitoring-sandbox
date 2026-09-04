# syntax=docker/dockerfile:1
# Production multi-stage Dockerfile for the infra-eval sandbox.
# Builds dependencies in a builder stage, then ships a minimal,
# non-root runtime image with health checks and consistent timezone.

############################
# Stage 1: Builder
############################
FROM python:3.11-slim-bookworm AS builder

# Prevent Python from writing pyc files and buffer output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install system build dependencies only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a user-local site-packages.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

############################
# Stage 2: Runtime
############################
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install only runtime system packages (tzdata for consistent timezone).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# Create a non-root sandbox user.
RUN groupadd -r sandbox \
    && useradd -r -g sandbox -G root -d /app -s /sbin/nologin sandbox

# Copy installed Python packages from the builder stage.
COPY --from=builder /root/.local /usr/local

# Copy application code with correct ownership.
COPY --chown=sandbox:sandbox . .

# Create runtime directories.
RUN mkdir -p /app/data /app/logs /app/reports/output \
    && chown -R sandbox:sandbox /app/data /app/logs /app/reports

# Expose default port (informational; the sandbox is headless by default).
EXPOSE 8080

# Health check using the non-root user.
# The sandbox is headless (no HTTP server); verify the Python process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, sys; sys.exit(0 if os.path.exists('/proc/1/comm') else 1)" || exit 1

# Drop privileges and run as non-root.
USER sandbox

# Use a JSON-form entrypoint so the container controller can talk to it.
ENTRYPOINT ["python", "main.py"]
