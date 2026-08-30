from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional
from datetime import datetime


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
    timestamp: datetime = Field(default_factory=datetime.utcnow)


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