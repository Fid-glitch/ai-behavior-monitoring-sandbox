"""
signals.py
-----------
Defines the individual risk SIGNALS that feed the RiskScorer, and a
SignalExtractor that runs every SafetyChecker component and normalizes their
outputs into one consistent structure.

Design principle: each signal is independently a number in [0, 1] representing
"how much does this piece of evidence alone suggest something is wrong,"
along with metadata for the reason_generator to explain itself later.
Combining signals into one score is scoring_formula's job, not this module's.

Signals captured, by source:
  - keyword_injection      (safety_checker.keyword_matcher)
  - jailbreak_pattern       (safety_checker.jailbreak_checker)
  - semantic_similarity     (safety_checker.similarity_checker)
  - ml_classifier           (safety_checker.injection_classifier)
  - document_structural     (safety_checker.document_scanner, only for tool/doc content)
  - action_sensitivity      (agent-action-level signal, not text-based -- see below)
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class Signal:
    name: str
    value: float          # 0-1
    weight_hint: float     # suggested relative importance, used by scoring_formula defaults
    evidence: str          # short human-readable justification
    source: str            # which checker produced this


@dataclass
class SignalBundle:
    signals: List[Signal] = field(default_factory=list)

    def add(self, name, value, weight_hint, evidence, source):
        self.signals.append(Signal(name, value, weight_hint, evidence, source))

    def as_dict(self) -> Dict[str, float]:
        return {s.name: s.value for s in self.signals}


# --- Action-level sensitivity (not derived from text scanning) -------------
# Static reference table for how dangerous a given tool/action category is
# BEFORE any injection is even considered. Feeds into the overall risk score
# independently, e.g. "delete_file" is risky even with totally clean input.
ACTION_SENSITIVITY: Dict[str, float] = {
    "read_file": 0.05,
    "list_directory": 0.05,
    "web_search": 0.05,
    "send_email": 0.4,
    "write_file": 0.35,
    "run_shell_command": 0.75,
    "execute_code": 0.7,
    "delete_file": 0.8,
    "modify_permissions": 0.85,
    "transfer_funds": 0.95,
    "make_purchase": 0.7,
    "call_external_api": 0.3,
    "access_credentials": 0.9,
    "modify_system_config": 0.85,
}
DEFAULT_ACTION_SENSITIVITY = 0.3  # unknown/unclassified actions treated as moderately risky


def action_sensitivity_signal(action_name: Optional[str]) -> Signal:
    if action_name is None:
        return Signal(
            name="action_sensitivity", value=0.0, weight_hint=0.7,
            evidence="No agent action specified (text-only scan).", source="action_sensitivity",
        )
    value = ACTION_SENSITIVITY.get(action_name, DEFAULT_ACTION_SENSITIVITY)
    known = action_name in ACTION_SENSITIVITY
    evidence = (
        f"Action '{action_name}' has baseline sensitivity {value} "
        f"({'known category' if known else 'unclassified, using default'})."
    )
    return Signal(name="action_sensitivity", value=value, weight_hint=0.7,
                  evidence=evidence, source="action_sensitivity")


class SignalExtractor:
    """Runs all text-based SafetyChecker components and assembles a SignalBundle.

    `similarity_checker` and `ml_classifier` are optional / injected, since
    they require fitted/trained state (reference corpus, trained model) that
    the caller owns -- this keeps SignalExtractor stateless and testable.
    """

    def __init__(self, similarity_checker=None, ml_classifier=None):
        self.similarity_checker = similarity_checker
        self.ml_classifier = ml_classifier

    def extract(
        self,
        text: str,
        content_source: str = "user_input",
        action_name: Optional[str] = None,
    ) -> SignalBundle:
        from safety_checker import keyword_matcher, jailbreak_checker, document_scanner

        bundle = SignalBundle()

        kw = keyword_matcher.scan(text)
        bundle.add(
            "keyword_injection", kw.score, weight_hint=0.8,
            evidence=f"{len(kw.matches)} pattern match(es) in categories: {kw.categories_hit}" if kw.matches else "no keyword matches",
            source="keyword_matcher",
        )

        jb = jailbreak_checker.scan(text)
        bundle.add(
            "jailbreak_pattern", jb.score, weight_hint=0.65,
            evidence=f"{len(jb.matches)} jailbreak pattern(s) in categories: {jb.categories_hit}" if jb.matches else "no jailbreak patterns",
            source="jailbreak_checker",
        )

        if self.similarity_checker is not None:
            sim = self.similarity_checker.check(text)
            top = sim.top_matches[0] if sim.top_matches else None
            evidence = (
                f"closest known example (sim={top.similarity}): {top.reference_text[:60]!r}"
                if top else "no reference corpus matches"
            )
            bundle.add("semantic_similarity", sim.score, weight_hint=0.55, evidence=evidence, source="similarity_checker")

        if self.ml_classifier is not None:
            pred = self.ml_classifier.predict(text)
            bundle.add(
                "ml_classifier", pred.score, weight_hint=0.75,
                evidence=f"classifier label={pred.label}, confidence={pred.confidence}",
                source="injection_classifier",
            )

        # document/tool-output content gets the structural scan too; direct
        # user chat input generally doesn't need it (no hidden HTML/zero-width
        # tricks in a chat box), but we still run it cheaply for anything
        # that isn't plain user_input, plus whenever text is long enough to
        # plausibly be a fetched document.
        if content_source != "user_input" or len(text) > 1500:
            doc = document_scanner.scan(text, source=content_source)
            bundle.add(
                "document_structural", doc.score, weight_hint=0.6,
                evidence=f"{len(doc.structural_flags)} structural flag(s): {[f.kind for f in doc.structural_flags]}",
                source="document_scanner",
            )

        bundle.signals.append(action_sensitivity_signal(action_name))

        return bundle
