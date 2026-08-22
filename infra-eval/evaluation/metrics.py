"""
Evaluation metrics, baseline comparison, and latency statistics.

Provides pure functions for computing detection metrics from
:class:`EvaluationResult` objects, comparing baseline (unprotected) results
against protected/monitored results, and calculating latency percentiles.

All calculations are derived from supplied results — nothing is hardcoded
or fabricated.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from logging_system import LogDecision

from .evaluator import EvaluationResult

#: Decisions that denote a malicious/attack test case.
ATTACK_DECISIONS = {LogDecision.BLOCK.value, LogDecision.WARNING.value}

#: Decision that denotes a benign test case.
BENIGN_DECISION = LogDecision.ALLOW.value


def _is_attack(expected_decision: str) -> bool:
    """Return True if a test case is an attack (BLOCK or WARNING expected)."""
    return expected_decision.upper() in ATTACK_DECISIONS


def _is_blocked(actual_decision: str) -> bool:
    """Return True if the actual decision blocked/rejected the request."""
    return actual_decision.upper() in ATTACK_DECISIONS


def _safe_divide(numerator: int, denominator: int) -> float:
    """Divide two integers safely, returning 0.0 for zero denominators."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


@dataclass
class DetectionMetrics:
    """
    Detection and classification metrics derived from evaluation results.

    Attributes:
        total_attacks: Total attack test cases (expected BLOCK/WARNING).
        total_benign: Total benign test cases (expected ALLOW).
        attacks_detected: Attacks correctly blocked (detected).
        attacks_missed: Attacks incorrectly allowed (false negatives).
        benign_allowed: Benign requests correctly allowed.
        benign_blocked: Benign requests incorrectly blocked (false positives).
        detection_rate: attacks_detected / total_attacks.
        false_positive_rate: benign_blocked / total_benign.
        false_negative_rate: attacks_missed / total_attacks.
        accuracy: (attacks_detected + benign_allowed) / total.
    """

    total_attacks: int = 0
    total_benign: int = 0
    attacks_detected: int = 0
    attacks_missed: int = 0
    benign_allowed: int = 0
    benign_blocked: int = 0

    @property
    def detection_rate(self) -> float:
        """Fraction of attacks that were correctly detected."""
        return _safe_divide(self.attacks_detected, self.total_attacks)

    @property
    def false_positive_rate(self) -> float:
        """Fraction of benign requests that were incorrectly blocked."""
        return _safe_divide(self.benign_blocked, self.total_benign)

    @property
    def false_negative_rate(self) -> float:
        """Fraction of attacks that were missed (allowed through)."""
        return _safe_divide(self.attacks_missed, self.total_attacks)

    @property
    def accuracy(self) -> float:
        """Overall fraction of correct decisions."""
        total = self.total_attacks + self.total_benign
        correct = self.attacks_detected + self.benign_allowed
        return _safe_divide(correct, total)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the metrics."""
        return {
            "total_attacks": self.total_attacks,
            "total_benign": self.total_benign,
            "attacks_detected": self.attacks_detected,
            "attacks_missed": self.attacks_missed,
            "benign_allowed": self.benign_allowed,
            "benign_blocked": self.benign_blocked,
            "detection_rate": self.detection_rate,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "accuracy": self.accuracy,
        }


def compute_metrics(results: Sequence[EvaluationResult]) -> DetectionMetrics:
    """
    Compute detection metrics from a sequence of evaluation results.

    Args:
        results: Sequence of :class:`EvaluationResult` objects.

    Returns:
        A :class:`DetectionMetrics` instance.
    """
    metrics = DetectionMetrics()
    for result in results:
        expected = (result.expected_decision or "").upper()
        actual = (result.actual_decision or "").upper()
        if _is_attack(expected):
            metrics.total_attacks += 1
            if _is_blocked(actual):
                metrics.attacks_detected += 1
            else:
                metrics.attacks_missed += 1
        else:
            metrics.total_benign += 1
            if _is_blocked(actual):
                metrics.benign_blocked += 1
            else:
                metrics.benign_allowed += 1
    return metrics


@dataclass
class LatencyStats:
    """
    Latency statistics derived from actual measured execution times.

    Attributes:
        samples: Number of latency samples used.
        average_ms: Mean latency in milliseconds.
        min_ms: Minimum latency in milliseconds.
        max_ms: Maximum latency in milliseconds.
        median_ms: Median latency in milliseconds (None if no samples).
        p95_ms: 95th-percentile latency in milliseconds (None if < 20 samples).
    """

    samples: int = 0
    average_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    median_ms: Optional[float] = None
    p95_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the latency stats."""
        return {
            "samples": self.samples,
            "average_ms": self.average_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
        }


def _percentile(values: Sequence[float], percentile: float) -> float:
    """
    Compute the nearest-rank percentile of a sorted sequence of values.

    Args:
        values: Sequence of numeric values.
        percentile: Percentile to compute (0.0 – 100.0).

    Returns:
        The percentile value.
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = int(rank // 1)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = rank - lower
    if upper == lower:
        return float(sorted_values[lower])
    return float(sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac)


def compute_latency_stats(results: Sequence[EvaluationResult]) -> LatencyStats:
    """
    Compute latency statistics from evaluation results.

    Uses the ``execution_time_ms`` (fallback ``latency_ms``) field of each
    :class:`EvaluationResult`.

    Args:
        results: Sequence of :class:`EvaluationResult` objects.

    Returns:
        A :class:`LatencyStats` instance.
    """
    latencies = [
        float(r.execution_time_ms if r.execution_time_ms is not None else r.latency_ms or 0.0)
        for r in results
    ]
    if not latencies:
        return LatencyStats(samples=0)
    avg = sum(latencies) / len(latencies)
    stats = LatencyStats(
        samples=len(latencies),
        average_ms=avg,
        min_ms=min(latencies),
        max_ms=max(latencies),
        median_ms=statistics.median(latencies),
        p95_ms=_percentile(latencies, 95.0),
    )
    return stats


@dataclass
class BaselineComparison:
    """
    Comparison between baseline (unprotected) and protected/monitored results.

    Attributes:
        baseline_metrics: Detection metrics for the baseline run.
        monitored_metrics: Detection metrics for the protected run.
        improvements: Dictionary of metric improvements (baseline → monitored).
    """

    baseline_metrics: Optional[DetectionMetrics] = None
    monitored_metrics: Optional[DetectionMetrics] = None
    improvements: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the comparison."""
        return {
            "baseline": (
                self.baseline_metrics.to_dict() if self.baseline_metrics else None
            ),
            "monitored": (
                self.monitored_metrics.to_dict() if self.monitored_metrics else None
            ),
            "improvements": self.improvements,
        }


def compare_baseline(
    baseline_results: Sequence[EvaluationResult],
    monitored_results: Sequence[EvaluationResult],
) -> BaselineComparison:
    """
    Compare baseline (unprotected) results against protected/monitored results.

    The differences are computed entirely from the supplied results — nothing
    is hardcoded or fabricated.

    Args:
        baseline_results: Results from the unprotected/baseline run.
        monitored_results: Results from the protected/monitored run.

    Returns:
        A :class:`BaselineComparison` with detection metrics and improvements.
    """
    baseline_metrics = compute_metrics(baseline_results)
    monitored_metrics = compute_metrics(monitored_results)

    improvements: Dict[str, float] = {
        "detection_rate": (
            monitored_metrics.detection_rate - baseline_metrics.detection_rate
        ),
        "false_positive_rate": (
            baseline_metrics.false_positive_rate - monitored_metrics.false_positive_rate
        ),
        "false_negative_rate": (
            baseline_metrics.false_negative_rate - monitored_metrics.false_negative_rate
        ),
        "accuracy": (
            monitored_metrics.accuracy - baseline_metrics.accuracy
        ),
        "attacks_detected": float(
            monitored_metrics.attacks_detected - baseline_metrics.attacks_detected
        ),
        "attacks_missed": float(
            monitored_metrics.attacks_missed - baseline_metrics.attacks_missed
        ),
        "benign_allowed": float(
            monitored_metrics.benign_allowed - baseline_metrics.benign_allowed
        ),
        "benign_blocked": float(
            monitored_metrics.benign_blocked - baseline_metrics.benign_blocked
        ),
    }

    return BaselineComparison(
        baseline_metrics=baseline_metrics,
        monitored_metrics=monitored_metrics,
        improvements=improvements,
    )