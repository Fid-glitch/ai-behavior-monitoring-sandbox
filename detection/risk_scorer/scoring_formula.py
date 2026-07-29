"""
scoring_formula.py
--------------------
Combines a SignalBundle into a single composite risk score in [0, 1].

Approach: weighted noisy-OR combination.
  Rationale: our signals are largely independent pieces of evidence pointing
  toward the same underlying question ("is this risky?"). A simple weighted
  AVERAGE is the wrong shape here -- it lets one strong, confident signal
  (e.g. keyword_matcher screaming "ignore all previous instructions" at 0.95)
  get diluted down by several unrelated near-zero signals. Noisy-OR instead
  treats each signal as independent evidence *for* risk and asks "what's the
  probability that NONE of these signals is right", which:
    - naturally caps at 1.0
    - lets one very strong signal dominate appropriately
    - still lets multiple weak/moderate signals stack into something risky
      even if no single one crosses an alarm threshold alone

  score = 1 - PRODUCT over signals of (1 - weight_i * value_i)

Weights are per-signal-name defaults (overridable) reflecting how much we
trust each detector's independent judgment. These should be tuned once you
have real precision/recall numbers from scripts/train_classifier.py and a
labeled validation set -- treat the numbers below as reasonable starting
points, not final.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List

from risk_scorer.signals import SignalBundle, Signal


DEFAULT_WEIGHTS: Dict[str, float] = {
    "keyword_injection": 0.85,
    "jailbreak_pattern": 0.75,
    "semantic_similarity": 0.6,
    "ml_classifier": 0.9,        # highest trust once properly trained/validated
    "document_structural": 0.7,
    "action_sensitivity": 0.8,
}


@dataclass
class ScoringResult:
    composite_score: float
    contributions: List[Dict]   # per-signal contribution breakdown, for reason_generator


def compute_risk_score(bundle: SignalBundle, weights: Optional[Dict[str, float]] = None) -> ScoringResult:
    weights = weights or DEFAULT_WEIGHTS
    prob_no_risk = 1.0
    contributions = []

    for signal in bundle.signals:
        w = weights.get(signal.name, 0.5)  # unknown signal names get a conservative mid weight
        effective = min(max(w * signal.value, 0.0), 1.0)
        prob_no_risk *= (1 - effective)
        contributions.append({
            "signal": signal.name,
            "raw_value": signal.value,
            "weight": w,
            "effective_contribution": round(effective, 4),
            "evidence": signal.evidence,
            "source": signal.source,
        })

    composite = round(1 - prob_no_risk, 4)
    # sort contributions by impact, most important first -- makes
    # reason_generator's job trivial
    contributions.sort(key=lambda c: c["effective_contribution"], reverse=True)

    return ScoringResult(composite_score=composite, contributions=contributions)
