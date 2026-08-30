# gates/input_gate.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas import GateDecision, GateOutcome, RiskTier, GateType
import re

class InputGate:
    """Gate 1: Pre-LLM input validation and prompt injection detection."""
    
    INJECTION_PATTERNS = [
        r"ignore.*instruction",
        r"forget.*previous",
        r"new task|new goal",
        r"bypass|override",
        r"disregard.*prompt",
        r"system.*prompt",
    ]
    
    def evaluate(self, user_input: str) -> GateDecision:
        """
        Evaluate user input for prompt injection attempts.
        
        Args:
            user_input: The user's query/request to check
        
        Returns:
            GateDecision: ALLOW if safe, BLOCK if injection detected
        """
        risk_tier = RiskTier.LOW
        reasons = []
        
        # Check for injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, user_input, re.IGNORECASE):
                risk_tier = RiskTier.HIGH
                reasons.append(f"Injection pattern detected: {pattern}")
                break  # Stop after first match
        
        outcome = GateOutcome.BLOCK if risk_tier == RiskTier.HIGH else GateOutcome.ALLOW
        
        return GateDecision(
            gate_type=GateType.INPUT_GATE,
            outcome=outcome,
            risk_tier=risk_tier,
            reasons=reasons,
            request_source=None  # Will be set by orchestrator if needed
        )