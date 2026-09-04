"""
Shared data contracts used across the pipeline (SafetyChecker, RiskScorer,
Gate 1 / InputGate, Gate 2 / ActionGate, ActivityLog, Dashboard).

Defining these here — and importing them everywhere else — means every
module agrees on the same field names and types, so teammates can build
RiskScorer, the gates, and the orchestrator in parallel without their
outputs/inputs drifting out of sync.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskTier(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RequestSource(str, Enum):
    LIVE = "live"          # real user via the UI
    TEST = "test"          # dataset-driven Evaluation Harness


class GateType(str, Enum):
    INPUT_GATE = "Gate1_InputGate"
    ACTION_GATE = "Gate2_ActionGate"


class GateOutcome(str, Enum):
    ALLOWED = "allowed"
    FLAGGED = "flagged"     # allowed, but logged with a warning (Medium tier)
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# RiskAssessment — produced by RiskScorer, consumed by Gate 1 and Gate 2
# ---------------------------------------------------------------------------

class SignalBreakdown(BaseModel):
    """Individual detector confidence scores that fed into the aggregate score."""
    direct_injection: float = Field(0.0, ge=0.0, le=1.0)
    semantic_jailbreak: float = Field(0.0, ge=0.0, le=1.0)
    similarity_to_known_attack: float = Field(0.0, ge=0.0, le=1.0)
    document_scan: float = Field(0.0, ge=0.0, le=1.0)
    intent_context_adjustment: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Dampening factor when the request looks explanatory/educational rather than a direct command."
    )


class RiskAssessment(BaseModel):
    """
    Standard output of RiskScorer.evaluate(...).
    This is what SafetyChecker findings get turned into, and what both
    gates read to make their allow/flag/block decision.
    """
    score: float = Field(..., ge=0.0, le=100.0, description="Aggregated risk score, 0-100.")
    tier: RiskTier
    reason: str = Field(..., description="Human-readable explanation, e.g. 'Matched direct injection pattern (92% confidence).'")
    signals: SignalBreakdown
    detector_version: str = Field(default="v1", description="Version tag for the detector/model that produced this, for audit purposes.")

    @classmethod
    def tier_from_score(cls, score: float) -> RiskTier:
        if score >= 75:
            return RiskTier.HIGH
        if score >= 40:
            return RiskTier.MEDIUM
        return RiskTier.LOW


# ---------------------------------------------------------------------------
# GateDecision — produced by Gate 1 and Gate 2, consumed by ActivityLog / Dashboard
# ---------------------------------------------------------------------------

class GateDecision(BaseModel):
    """
    Standard output of both InputGate.decide(...) and ActionGate.decide(...).
    ActivityLog.record(...) should accept this directly.
    """
    gate: GateType
    outcome: GateOutcome
    risk: RiskAssessment
    source: RequestSource
    session_id: str = Field(..., description="Groups related requests/actions together for a single user session.")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Populated only for Gate 2 (Action Gate) decisions
    tool_name: Optional[str] = Field(None, description="Name of the tool the agent attempted to call, if applicable.")
    tool_input: Optional[dict] = Field(None, description="Arguments the agent attempted to pass to the tool, if applicable.")
    intent_match: Optional[bool] = Field(
        None, description="Whether the proposed action matched the user's original parsed intent (Gate 2 only)."
    )

    # User-facing vs. dashboard-facing messages (see explainability discussion:
    # short/generic reason to the user, full technical reason on the dashboard)
    user_message: Optional[str] = Field(
        None, description="Short, non-technical message shown to the end user if flagged/blocked."
    )

    def to_log_row(self) -> dict:
        """Flattened dict, convenient for ActivityLog's SQLite insert function."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "gate": self.gate.value,
            "outcome": self.outcome.value,
            "source": self.source.value,
            "score": self.risk.score,
            "tier": self.risk.tier.value,
            "reason": self.risk.reason,
            "tool_name": self.tool_name,
            "intent_match": self.intent_match,
        }


# ---------------------------------------------------------------------------
# Example usage (not executed on import — for reference only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    example_risk = RiskAssessment(
        score=82.5,
        tier=RiskTier.HIGH,
        reason="Matched direct injection pattern 'ignore previous instructions' (92% confidence).",
        signals=SignalBreakdown(
            direct_injection=0.92,
            semantic_jailbreak=0.10,
            similarity_to_known_attack=0.75,
            document_scan=0.0,
            intent_context_adjustment=0.05,
        ),
    )

    example_decision = GateDecision(
        gate=GateType.INPUT_GATE,
        outcome=GateOutcome.BLOCKED,
        risk=example_risk,
        source=RequestSource.LIVE,
        session_id="sess_001",
        user_message="Your request was blocked because it looked like an attempt to override system instructions.",
    )

    print(example_decision.model_dump_json(indent=2))