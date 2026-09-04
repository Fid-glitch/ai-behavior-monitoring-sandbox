"""
Unit tests for evaluation metrics, baseline comparison, and latency statistics.

Tests cover detection metrics, false-positive/false-negative rates, accuracy,
attacks detected/missed, benign request handling, baseline comparison, and
latency statistics — all computed from actual supplied results.
"""

from __future__ import annotations

import pytest

from evaluation import (
    BaselineComparison,
    DetectionMetrics,
    LatencyStats,
    EvaluationResult,
    compare_baseline,
    compute_latency_stats,
    compute_metrics,
)


def _result(
    test_case_id: str,
    expected: str,
    actual: str,
    execution_time_ms: float = 5.0,
) -> EvaluationResult:
    """Build an EvaluationResult for testing."""
    return EvaluationResult(
        test_case_id=test_case_id,
        expected_decision=expected,
        actual_decision=actual,
        risk_score=0.1 if actual == "ALLOW" else 0.9,
        succeeded=expected.upper() == actual.upper(),
        execution_time_ms=execution_time_ms,
        latency_ms=execution_time_ms,
    )


# ----------------------------------------------------------------------
# DetectionMetrics
# ----------------------------------------------------------------------
class TestDetectionMetrics:
    """Tests for detection metric calculations."""

    def test_detected_attack(self) -> None:
        result = _result("tc1", "BLOCK", "BLOCK")
        metrics = compute_metrics([result])
        assert metrics.total_attacks == 1
        assert metrics.attacks_detected == 1
        assert metrics.detection_rate == 1.0

    def test_missed_attack(self) -> None:
        result = _result("tc1", "BLOCK", "ALLOW")
        metrics = compute_metrics([result])
        assert metrics.total_attacks == 1
        assert metrics.attacks_missed == 1
        assert metrics.false_negative_rate == 1.0

    def test_benign_allowed(self) -> None:
        result = _result("tc1", "ALLOW", "ALLOW")
        metrics = compute_metrics([result])
        assert metrics.total_benign == 1
        assert metrics.benign_allowed == 1
        assert metrics.false_positive_rate == 0.0

    def test_benign_blocked(self) -> None:
        result = _result("tc1", "ALLOW", "BLOCK")
        metrics = compute_metrics([result])
        assert metrics.benign_blocked == 1
        assert metrics.false_positive_rate == 1.0

    def test_accuracy_all_correct(self) -> None:
        results = [
            _result("a1", "BLOCK", "BLOCK"),
            _result("a2", "WARNING", "WARNING"),
            _result("b1", "ALLOW", "ALLOW"),
        ]
        metrics = compute_metrics(results)
        assert metrics.accuracy == 1.0

    def test_accuracy_half(self) -> None:
        results = [
            _result("a1", "BLOCK", "BLOCK"),
            _result("a2", "BLOCK", "ALLOW"),
            _result("b1", "ALLOW", "ALLOW"),
            _result("b2", "ALLOW", "BLOCK"),
        ]
        metrics = compute_metrics(results)
        assert metrics.accuracy == pytest.approx(0.5)

    def test_empty_inputs(self) -> None:
        metrics = compute_metrics([])
        assert metrics.total_attacks == 0
        assert metrics.detection_rate == 0.0
        assert metrics.false_positive_rate == 0.0
        assert metrics.false_negative_rate == 0.0
        assert metrics.accuracy == 0.0

    def test_to_dict(self) -> None:
        result = _result("tc1", "BLOCK", "BLOCK")
        data = compute_metrics([result]).to_dict()
        assert data["detection_rate"] == 1.0
        assert data["attacks_detected"] == 1
        assert "false_positive_rate" in data
        assert "accuracy" in data


# ----------------------------------------------------------------------
# LatencyStats
# ----------------------------------------------------------------------
class TestLatencyStats:
    """Tests for latency statistics."""

    def test_basic_latency_stats(self) -> None:
        results = [
            _result("tc1", "ALLOW", "ALLOW", execution_time_ms=10.0),
            _result("tc2", "ALLOW", "ALLOW", execution_time_ms=20.0),
            _result("tc3", "ALLOW", "ALLOW", execution_time_ms=30.0),
        ]
        stats = compute_latency_stats(results)
        assert stats.samples == 3
        assert stats.average_ms == pytest.approx(20.0)
        assert stats.min_ms == 10.0
        assert stats.max_ms == 30.0
        assert stats.median_ms == pytest.approx(20.0)

    def test_p95(self) -> None:
        results = [
            _result(f"tc{i}", "ALLOW", "ALLOW", execution_time_ms=float(i))
            for i in range(1, 21)
        ]
        stats = compute_latency_stats(results)
        assert stats.samples == 20
        assert stats.p95_ms is not None
        assert stats.p95_ms >= stats.average_ms

    def test_empty_inputs(self) -> None:
        stats = compute_latency_stats([])
        assert stats.samples == 0
        assert stats.average_ms == 0.0
        assert stats.median_ms is None
        assert stats.p95_ms is None

    def test_single_sample(self) -> None:
        result = _result("tc1", "ALLOW", "ALLOW", execution_time_ms=42.0)
        stats = compute_latency_stats([result])
        assert stats.average_ms == 42.0
        assert stats.min_ms == 42.0
        assert stats.max_ms == 42.0
        assert stats.median_ms == 42.0

    def test_to_dict(self) -> None:
        result = _result("tc1", "ALLOW", "ALLOW", execution_time_ms=10.0)
        data = compute_latency_stats([result]).to_dict()
        assert data["samples"] == 1
        assert data["average_ms"] == 10.0


# ----------------------------------------------------------------------
# Baseline comparison
# ----------------------------------------------------------------------
class TestBaselineComparison:
    """Tests for baseline vs protected comparison."""

    def test_improvement_detection(self) -> None:
        baseline = [
            _result("a1", "BLOCK", "ALLOW"),
            _result("a2", "BLOCK", "ALLOW"),
            _result("b1", "ALLOW", "ALLOW"),
        ]
        monitored = [
            _result("a1", "BLOCK", "BLOCK"),
            _result("a2", "BLOCK", "BLOCK"),
            _result("b1", "ALLOW", "ALLOW"),
        ]
        comparison = compare_baseline(baseline, monitored)
        assert comparison.baseline_metrics is not None
        assert comparison.monitored_metrics is not None
        assert comparison.baseline_metrics.detection_rate == 0.0
        assert comparison.monitored_metrics.detection_rate == 1.0
        assert comparison.improvements["detection_rate"] == pytest.approx(1.0)
        assert comparison.improvements["attacks_detected"] == pytest.approx(2.0)

    def test_baseline_equal(self) -> None:
        results = [
            _result("a1", "BLOCK", "BLOCK"),
            _result("b1", "ALLOW", "ALLOW"),
        ]
        comparison = compare_baseline(results, results)
        assert comparison.improvements["detection_rate"] == 0.0
        assert comparison.improvements["accuracy"] == 0.0

    def test_fp_improvement(self) -> None:
        baseline = [
            _result("b1", "ALLOW", "BLOCK"),
            _result("b2", "ALLOW", "ALLOW"),
        ]
        monitored = [
            _result("b1", "ALLOW", "ALLOW"),
            _result("b2", "ALLOW", "ALLOW"),
        ]
        comparison = compare_baseline(baseline, monitored)
        assert comparison.baseline_metrics.false_positive_rate == 0.5
        assert comparison.monitored_metrics.false_positive_rate == 0.0
        assert comparison.improvements["false_positive_rate"] == pytest.approx(0.5)

    def test_to_dict(self) -> None:
        baseline = [_result("a1", "BLOCK", "ALLOW")]
        monitored = [_result("a1", "BLOCK", "BLOCK")]
        data = compare_baseline(baseline, monitored).to_dict()
        assert data["baseline"] is not None
        assert data["monitored"] is not None
        assert data["improvements"]["detection_rate"] == pytest.approx(1.0)

    def test_real_world_scenario(self) -> None:
        """A realistic scenario with the same test cases in both runs."""
        baseline = [
            _result("attack-1", "BLOCK", "ALLOW"),
            _result("attack-2", "BLOCK", "ALLOW"),
            _result("attack-3", "WARNING", "ALLOW"),
            _result("benign-1", "ALLOW", "ALLOW"),
            _result("benign-2", "ALLOW", "ALLOW"),
            _result("benign-3", "ALLOW", "BLOCK"),
        ]
        monitored = [
            _result("attack-1", "BLOCK", "BLOCK"),
            _result("attack-2", "BLOCK", "BLOCK"),
            _result("attack-3", "WARNING", "WARNING"),
            _result("benign-1", "ALLOW", "ALLOW"),
            _result("benign-2", "ALLOW", "ALLOW"),
            _result("benign-3", "ALLOW", "ALLOW"),
        ]
        comparison = compare_baseline(baseline, monitored)
        baseline_m = comparison.baseline_metrics
        monitored_m = comparison.monitored_metrics
        assert baseline_m.attacks_detected == 0
        assert baseline_m.attacks_missed == 3
        assert baseline_m.benign_blocked == 1
        assert monitored_m.attacks_detected == 3
        assert monitored_m.attacks_missed == 0
        assert monitored_m.benign_blocked == 0
        assert comparison.improvements["attacks_detected"] == pytest.approx(3.0)
        assert comparison.improvements["attacks_missed"] == pytest.approx(-3.0)
        assert comparison.improvements["benign_blocked"] == pytest.approx(-1.0)