"""
reason_generator.py
---------------------
Turns a ScoringResult + TierMapping into a human-readable explanation for the
audit trail / monitoring dashboard. This is what a human reviewer actually
reads when deciding whether to trust a HIGH/CRITICAL flag -- a bare number is
not auditable, a clear explanation is.
"""

from dataclasses import dataclass
from typing import List

from risk_scorer.scoring_formula import ScoringResult
from risk_scorer.tier_mapper import TierMapping


@dataclass
class RiskReport:
    composite_score: float
    tier: str
    recommended_action: str
    summary: str
    top_reasons: List[str]
    full_contributions: list


def generate(scoring_result: ScoringResult, tier_mapping: TierMapping, top_n: int = 3) -> RiskReport:
    top_contributors = [c for c in scoring_result.contributions if c["effective_contribution"] > 0.01][:top_n]

    if not top_contributors:
        summary = "No significant risk signals detected. Input appears benign."
        top_reasons = []
    else:
        reason_lines = [
            f"{c['signal']} (source: {c['source']}) contributed {c['effective_contribution']} "
            f"to the risk score -- {c['evidence']}"
            for c in top_contributors
        ]
        top_reasons = reason_lines
        lead = top_contributors[0]
        summary = (
            f"Flagged as {tier_mapping.tier.value} risk (score={scoring_result.composite_score}), "
            f"driven primarily by '{lead['signal']}': {lead['evidence']}"
        )

    return RiskReport(
        composite_score=scoring_result.composite_score,
        tier=tier_mapping.tier.value,
        recommended_action=tier_mapping.recommended_action,
        summary=summary,
        top_reasons=top_reasons,
        full_contributions=scoring_result.contributions,
    )
