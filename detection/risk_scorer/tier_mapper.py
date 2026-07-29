"""
tier_mapper.py
---------------
Maps a composite 0-1 risk score into a discrete, actionable tier. Discrete
tiers are what the sandbox's permission/audit layer actually branches on --
"0.6273" isn't actionable by itself, but "HIGH -> require human confirmation
before executing" is.

Thresholds are intentionally centralized here (not scattered across the
codebase) so they can be tuned in one place as you get real evaluation data.
"""

from dataclasses import dataclass
from enum import Enum


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class TierMapping:
    tier: RiskTier
    recommended_action: str
    threshold_range: str


# (upper_bound_exclusive_for_this_tier, tier, recommended_action)
# score < 0.25         -> LOW
# 0.25 <= score < 0.5   -> MEDIUM
# 0.5  <= score < 0.75  -> HIGH
# score >= 0.75         -> CRITICAL
TIER_THRESHOLDS = [
    (0.25, RiskTier.LOW, "Allow. Log for audit trail only."),
    (0.5, RiskTier.MEDIUM, "Allow, but flag in monitoring dashboard for review."),
    (0.75, RiskTier.HIGH, "Pause and require explicit human confirmation before proceeding."),
    (1.01, RiskTier.CRITICAL, "Block action immediately. Escalate to human operator."),
]


def map_score_to_tier(score: float) -> TierMapping:
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"score must be in [0, 1], got {score}")

    lower = 0.0
    for upper, tier, action in TIER_THRESHOLDS:
        if score < upper:
            return TierMapping(
                tier=tier,
                recommended_action=action,
                threshold_range=f"[{lower}, {upper if upper <= 1.0 else 1.0})",
            )
        lower = upper
    # unreachable given the 1.01 sentinel above, but keep a safe fallback
    return TierMapping(tier=RiskTier.CRITICAL, recommended_action="Block action immediately.", threshold_range="[0.75, 1.0]")
