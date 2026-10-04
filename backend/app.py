"""
FastAPI application for the Secure Autonomous AI Behavior Monitoring Sandbox.

Exposes the ASGI ``app`` object that the frontend reaches through its ``/api``
base path. Implemented so far:

- ``GET /health`` - liveness probe.
- ``POST /api/analyze`` - runs the existing gated agent for one user prompt and
  returns the resulting ``AgentDecision`` as JSON (the agent also persists it
  to SQLite as part of the call).

- ``GET /api/history`` - returns past decisions formatted for the timeline.
- ``GET /api/stats`` - aggregates counts for the session stats panel.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Agent import path
# ---------------------------------------------------------------------------
# ``agent/orchestrator/agent.py`` adds the ``agent/`` and ``infra-eval/``
# directories to ``sys.path`` itself, but it can only do that once it has been
# imported, so ``agent/`` is added here to make ``orchestrator`` and
# ``providers`` importable. No other path manipulation is duplicated.
_AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from orchestrator.agent import build_email_agent, run_agent_with_gates  # noqa: E402
from providers.groq_provider import GroqProvider  # noqa: E402

# Importing the agent module above also puts ``infra-eval/`` on ``sys.path``,
# which is what makes the existing SQLite layer importable here without
# duplicating any path handling.
from config.settings import settings  # noqa: E402  (same DATABASE_URL the agent writes to)
from database import Database, DatabaseError  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Build the tool-bound LLM once, when the application starts.

    ``GroqProvider`` reads ``GROQ_API_KEY``; when the key or the agent
    dependencies are missing, startup fails loudly instead of silently falling
    back to a fake model. Binding the tools here means every request reuses one
    LLM object instead of creating a provider per call.

    Yields:
        Control back to the ASGI server for the lifetime of the application.
    """
    provider = GroqProvider()
    application.state.llm_with_tools = build_email_agent(provider)
    yield


#: ASGI application object served by ``uvicorn`` (e.g. ``uvicorn app:app``).
app = FastAPI(
    title="Secure Autonomous AI Behavior Monitoring Sandbox API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    """Return a simple liveness payload."""
    return {"status": "ok"}


class AnalyzeRequest(BaseModel):
    """
    Request body for ``POST /api/analyze``.

    Mirrors the frontend contract exactly (``frontend/src/services/api.js``).
    ``fileName`` and ``fileText`` are accepted for frontend compatibility; the
    file content is deliberately not appended to the prompt yet.
    """

    prompt: str
    fileName: Optional[str] = None
    fileText: Optional[str] = None


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest, request: Request) -> dict:
    """
    Run one user prompt through the existing gated agent.

    The prompt is validated, handed to ``run_agent_with_gates`` (Gate 1, LLM and
    tool execution, Gate 2, and the SQLite persistence of the resulting
    ``AgentDecision``) and the structured decision is returned.

    A Gate 1 / Gate 2 ``BLOCK`` is a normal analysis result and is deliberately
    answered with ``200 OK`` plus the decision - it is not mapped to an HTTP
    error.

    Args:
        payload: Validated request body (``prompt``, ``fileName``, ``fileText``).
        request: Current request, used to reach the startup-created LLM.

    Returns:
        The ``AgentDecision`` as JSON with the camelCase fields the frontend
        expects (``id``, ``timestamp``, ``gate``, ``riskTier``, ``riskScore``,
        ``decision``, ``ruleTriggered``, ``reason``, ``agentResponse``,
        ``toolCalled``; ``reasons`` is included as part of the model and ignored
        by the frontend).

    Raises:
        HTTPException: 400 when the prompt is empty after stripping, 500 when
            the agent is not initialised or the agent run fails.
    """
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    llm_with_tools = getattr(request.app.state, "llm_with_tools", None)
    if llm_with_tools is None:
        raise HTTPException(
            status_code=500,
            detail="Agent is not initialised; check the server startup logs.",
        )

    try:
        decision = run_agent_with_gates(llm_with_tools, prompt)
        result = decision.model_dump()
    except Exception as exc:
        # Keep stack traces, API keys and other internals out of the response;
        # the full traceback is written to the server log instead.
        logger.exception("Agent run failed for prompt of length %s", len(prompt))
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed ({type(exc).__name__}).",
        ) from exc

    return result


# ---------------------------------------------------------------------------
# SQLite history access (existing infra-eval layer, read-only here)
# ---------------------------------------------------------------------------
#: Shared Database instance. ``Database`` is thread-safe and reuses its
#: connection, and it is created from the very same ``DATABASE_URL`` the agent
#: persistence helper uses - no separate database configuration is introduced.
_database: Optional[Database] = None


def _get_database() -> Database:
    """
    Return the shared :class:`database.Database` instance.

    The instance is created from the configured ``DATABASE_URL`` on first use
    and its schema is created with the database layer's own ``initialize()`` -
    the same idempotent mechanism the agent's persistence path already uses.
    A database file that exists before any decision has been persisted (for
    example one left behind by an earlier run) would otherwise have no
    ``activity_logs`` table yet, and the read endpoints would fail instead of
    reporting an empty history and zeroed counters.

    Returns:
        The shared Database, created and initialised on first use.

    Raises:
        DatabaseError: If the database cannot be opened or its schema cannot be
            created; callers translate this into an HTTP 500.
    """
    global _database
    if _database is None:
        database = Database(str(settings.DATABASE_URL))
        database.initialize()
        _database = database
    return _database


def _history_event_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert one ``activity_logs`` row into the frontend's event shape.

    Most fields come from dedicated columns; ``gate``, ``riskTier`` and
    ``ruleTriggered`` only exist in the ``metadata`` JSON written by the agent's
    persistence helper. Missing or malformed metadata yields ``None`` rather
    than an invented value, so a single bad historical row cannot break the
    whole response.

    Args:
        row: Row dictionary returned by ``Database.query_activity_logs``.

    Returns:
        A dict with the camelCase fields the frontend expects.
    """
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "id": row.get("id"),
        "timestamp": row.get("timestamp"),
        "gate": metadata.get("gate"),
        "riskTier": metadata.get("risk_tier"),
        "riskScore": row.get("risk_score"),
        "decision": row.get("decision"),
        "ruleTriggered": metadata.get("rule_triggered"),
        "reason": row.get("message"),
        "agentResponse": row.get("ai_response"),
        "toolCalled": row.get("tool_used"),
    }


@app.get("/api/history")
def history(limit: int = Query(default=50, ge=1, le=100)) -> dict:
    """
    Return the most recent persisted agent decisions, newest first.

    Args:
        limit: Maximum number of records to return (1-100, default 50).

    Returns:
        ``{"events": [...]}`` where every event carries the camelCase fields the
        frontend expects. The ordering returned by the database layer (newest
        first) is preserved.

    Raises:
        HTTPException: 500 when the stored history cannot be read.
    """
    try:
        rows = _get_database().query_activity_logs(limit=limit)
    except DatabaseError as exc:
        # Internal database details stay in the server log.
        logger.exception("Failed to read agent decision history")
        raise HTTPException(
            status_code=500,
            detail="Failed to read the decision history.",
        ) from exc

    return {"events": [_history_event_from_row(row) for row in rows]}


@app.get("/api/stats")
def stats() -> dict:
    """
    Return session aggregated metrics for the frontend stats panel.

    Counts total processed requests, allowed runs, flagged requests, and blocked
    requests from the persistent SQLite activity log. Decisions stored in the
    database use uppercase ("ALLOW", "BLOCK", "WARNING") per Member 4's
    ``LogDecision`` enum. A decision is counted as flagged if the recorded
    decision is "WARNING" or its metadata indicates a "medium" risk tier.

    Returns:
        A dictionary containing:
          - ``totalRequests``: Total number of logged requests.
          - ``allowed``: Count of requests allowed through all gates.
          - ``flagged``: Count of requests flagged with warnings / medium risk.
          - ``blocked``: Count of requests blocked by security gates.

    Raises:
        HTTPException: 500 when the database cannot be queried.
    """
    try:
        db = _get_database()
        total_requests = db.count_activity_logs()
        # Retrieve all logged requests to derive accurate decision-level metrics.
        # activity_logs table is queried via the existing Database abstraction.
        rows = db.query_activity_logs(limit=max(total_requests, 1)) if total_requests > 0 else []
    except DatabaseError as exc:
        logger.exception("Failed to query activity logs for statistics")
        raise HTTPException(
            status_code=500,
            detail="Failed to compute session statistics.",
        ) from exc

    allowed = 0
    flagged = 0
    blocked = 0

    for row in rows:
        decision_val = str(row.get("decision") or "").upper()
        meta = row.get("metadata")
        risk_tier_val = ""
        if isinstance(meta, dict):
            risk_tier_val = str(meta.get("risk_tier") or "").upper()
        elif isinstance(meta, str):
            try:
                import json

                parsed_meta = json.loads(meta)
                if isinstance(parsed_meta, dict):
                    risk_tier_val = str(parsed_meta.get("risk_tier") or "").upper()
            except Exception:
                pass

        if decision_val == "BLOCK":
            blocked += 1
        elif decision_val == "WARNING" or risk_tier_val == "MEDIUM":
            flagged += 1
        elif decision_val == "ALLOW":
            allowed += 1

    return {
        "totalRequests": total_requests,
        "allowed": allowed,
        "flagged": flagged,
        "blocked": blocked,
    }
