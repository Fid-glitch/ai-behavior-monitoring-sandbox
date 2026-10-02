from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional
from datetime import datetime, timezone


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GateOutcome(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


class GateType(str, Enum):
    INPUT_GATE = "input_gate"
    ACTION_GATE = "action_gate"


class RequestSource(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class SignalBreakdown(BaseModel):
    signal_type: str
    severity: RiskTier
    evidence: str


class RiskAssessment(BaseModel):
    overall_tier: RiskTier
    confidence: float
    signals: List[SignalBreakdown] = []
    summary: str


class GateDecision(BaseModel):
    gate_type: GateType
    outcome: GateOutcome
    risk_tier: RiskTier
    reasons: List[str] = []
    request_source: Optional[RequestSource] = None
    risk_score: float = 0.0  # <--- Added for Member 2 ML scores
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentDecision(BaseModel):
    """
    Aggregated, API-ready result of a single gated agent run.

    Produced by ``run_agent_with_gates`` from the existing
    :class:`GateDecision` objects (Gate 1 / Gate 2) plus the tool and LLM
    output of that run. It does not replace :class:`GateDecision`: the gate
    models stay exactly as they are, and this model only aggregates their
    results into the single object the dashboard/API contract needs.

    Value conventions (all taken from the existing enums / gate decisions):
      - ``gate``      : "input" for Gate 1, "action" for Gate 2, "no_tools"
                        when no ActionGate decision was produced
      - ``riskTier``  : ``RiskTier`` value ("low" / "medium" / "high")
      - ``decision``  : "ALLOW" / "BLOCK" / "WARNING" (``GateOutcome`` semantics)
    """

    #: Temporary placeholder — database ids arrive in a later phase.
    id: int = 0
    #: ISO-8601 (UTC) timestamp created together with the final decision.
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    #: Gate that produced the final decision ("input" / "action" / "no_tools").
    gate: str
    #: Risk tier value taken from the existing GateDecision.risk_tier.
    riskTier: str = RiskTier.LOW.value
    #: Risk score taken from the existing GateDecision.risk_score.
    riskScore: float = 0.0
    #: Final outcome for the request: "ALLOW" / "BLOCK" / "WARNING".
    decision: str
    #: Detection rule responsible for the decision, when one actually fired.
    ruleTriggered: Optional[str] = None
    #: Human-readable reason (the existing gate reasons joined with " | ").
    reason: str = ""
    #: Raw, unmodified ``GateDecision.reasons`` list for the final decision.
    reasons: List[str] = []
    #: Tool executed for this request, when a tool call actually ran.
    toolCalled: Optional[str] = None
    #: Response for the caller: LLM content, or the tool output that passed.
    agentResponse: Optional[str] = None


class RequestContext(BaseModel):
    request_id: str
    user_query: str
    gate1_decision: GateDecision
    gate2_decision: Optional[GateDecision] = None
    risk_assessment: Optional[RiskAssessment] = None
    tool_executed: Optional[str] = None
    final_outcome: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def to_log_row(request_id, user_query, gate_decision, risk_assessment=None, tool_name=None, tool_args=None, outcome="pending"):
    return {
        "request_id": request_id,
        "timestamp": gate_decision.timestamp.isoformat(),
        "user_query": user_query,
        "gate_type": gate_decision.gate_type.value,
        "gate_outcome": gate_decision.outcome.value,
        "gate_risk_tier": gate_decision.risk_tier.value,
        "gate_reasons": " | ".join(gate_decision.reasons),
        "risk_tier": risk_assessment.overall_tier.value if risk_assessment else None,
        "risk_confidence": risk_assessment.confidence if risk_assessment else None,
        "risk_summary": risk_assessment.summary if risk_assessment else None,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "final_outcome": outcome,
    }