"""
Unit tests for the evaluation report data and JSON report generation.

Tests cover report creation, JSON serialization, metrics inclusion,
baseline comparison inclusion, latency inclusion, empty results, and
failed evaluations.
"""

from __future__ import annotations

import json

import pytest

from evaluation import (
    BenchmarkMeta,
    EvaluationResult,
)
from reports import (
    EvaluationReport,
    build_report,
    report_to_json,
    save_report_json,
)


def _result(
    test_case_id: str,
    expected: str,
    actual: str,
    execution_time_ms: float = 5.0,
    error: str | None = None,
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
        error=error,
    )


def _sample_results() -> list:
    """Return a list of sample evaluation results."""
    return [
        _result("attack-1", "BLOCK", "BLOCK", execution_time_ms=10.0),
        _result("attack-2", "BLOCK", "ALLOW", execution_time_ms=20.0),
        _result("benign-1", "ALLOW", "ALLOW", execution_time_ms=30.0),
    ]


def _baseline_results() -> list:
    """Return a list of baseline (unprotected) results."""
    return [
        _result("attack-1", "BLOCK", "ALLOW", execution_time_ms=5.0),
        _result("attack-2", "BLOCK", "ALLOW", execution_time_ms=5.0),
        _result("benign-1", "ALLOW", "ALLOW", execution_time_ms=5.0),
    ]


# ----------------------------------------------------------------------
# Report creation
# ----------------------------------------------------------------------
class TestReportCreation:
    """Tests for building evaluation reports."""

    def test_build_report_basic(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        assert isinstance(report, EvaluationReport)
        assert report.benchmark_name == "mock"
        assert report.summary is not None
        assert report.summary.total == 3
        assert report.summary.passed == 2
        assert report.summary.failed == 1

    def test_build_report_with_metadata(self) -> None:
        meta = BenchmarkMeta(name="mock", version="1.0", format="mock")
        report = build_report(
            benchmark_name="mock",
            results=_sample_results(),
            metadata=meta,
        )
        assert report.metadata is not None
        assert report.metadata.name == "mock"

    def test_build_report_with_timestamp(self) -> None:
        report = build_report(
            benchmark_name="mock",
            results=_sample_results(),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert report.timestamp == "2026-01-01T00:00:00+00:00"

    def test_build_report_with_baseline(self) -> None:
        report = build_report(
            benchmark_name="mock",
            results=_sample_results(),
            baseline_results=_baseline_results(),
        )
        assert report.baseline_metrics is not None
        assert report.comparison is not None
        assert report.comparison.baseline_metrics is not None
        assert report.comparison.monitored_metrics is not None


# ----------------------------------------------------------------------
# JSON serialization
# ----------------------------------------------------------------------
class TestJsonSerialization:
    """Tests for JSON report serialization."""

    def test_to_json_valid(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        text = report.to_json()
        data = json.loads(text)
        assert data["benchmark_name"] == "mock"
        assert data["total_test_cases"] == 3
        assert data["passed"] == 2
        assert data["failed"] == 1

    def test_report_to_json_function(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        text = report_to_json(report)
        data = json.loads(text)
        assert data["benchmark_name"] == "mock"

    def test_save_report_json(self, tmp_path) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        path = tmp_path / "report.json"
        save_report_json(report, path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["benchmark_name"] == "mock"


# ----------------------------------------------------------------------
# Metrics inclusion
# ----------------------------------------------------------------------
class TestMetricsInclusion:
    """Tests for detection metrics in the report."""

    def test_metrics_included(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert data["detection_metrics"] is not None
        assert data["detection_metrics"]["total_attacks"] == 2
        assert data["detection_metrics"]["attacks_detected"] == 1
        assert data["detection_metrics"]["attacks_missed"] == 1
        assert data["detection_metrics"]["benign_allowed"] == 1

    def test_monitored_metrics_included(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert data["monitored"] is not None
        assert data["monitored"]["detection_rate"] == 0.5


# ----------------------------------------------------------------------
# Baseline comparison inclusion
# ----------------------------------------------------------------------
class TestBaselineInclusion:
    """Tests for baseline comparison in the report."""

    def test_baseline_included(self) -> None:
        report = build_report(
            benchmark_name="mock",
            results=_sample_results(),
            baseline_results=_baseline_results(),
        )
        data = report.to_dict()
        assert data["baseline"] is not None
        assert data["baseline"]["attacks_detected"] == 0
        assert data["comparison"] is not None
        assert data["comparison"]["improvements"]["attacks_detected"] == 1.0

    def test_no_baseline_when_not_supplied(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert data["baseline"] is None
        assert data["comparison"] is None


# ----------------------------------------------------------------------
# Latency inclusion
# ----------------------------------------------------------------------
class TestLatencyInclusion:
    """Tests for latency statistics in the report."""

    def test_latency_included(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert data["latency"] is not None
        assert data["latency"]["samples"] == 3
        assert data["latency"]["average_ms"] == 20.0
        assert data["latency"]["min_ms"] == 10.0
        assert data["latency"]["max_ms"] == 30.0


# ----------------------------------------------------------------------
# Empty results
# ----------------------------------------------------------------------
class TestEmptyResults:
    """Tests for reports with no results."""

    def test_empty_results(self) -> None:
        report = build_report(benchmark_name="mock", results=[])
        data = report.to_dict()
        assert data["total_test_cases"] == 0
        assert data["passed"] == 0
        assert data["failed"] == 0
        assert data["detection_metrics"] is not None
        assert data["latency"] is not None
        assert data["latency"]["samples"] == 0
        assert data["results"] == []


# ----------------------------------------------------------------------
# Failed evaluations
# ----------------------------------------------------------------------
class TestFailedEvaluations:
    """Tests for reports with failed evaluations."""

    def test_errors_collected(self) -> None:
        results = [
            _result("tc1", "ALLOW", "ALLOW"),
            _result("tc2", "BLOCK", "ALLOW", error="simulated failure"),
        ]
        report = build_report(benchmark_name="mock", results=results)
        data = report.to_dict()
        assert data["failed"] == 1
        assert "simulated failure" in data["errors"]

    def test_no_errors_when_all_pass(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert data["errors"] == []

    def test_results_included(self) -> None:
        report = build_report(benchmark_name="mock", results=_sample_results())
        data = report.to_dict()
        assert len(data["results"]) == 3
        assert data["results"][0]["test_case_id"] == "attack-1"