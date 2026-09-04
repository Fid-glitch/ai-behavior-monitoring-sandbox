"""
Unit tests for additional report formats (CSV and HTML).

Tests cover CSV generation, CSV file saving, CSV headers/content, empty
results, failed evaluations, and HTML generation.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from evaluation import EvaluationResult
from reports import (
    CSV_COLUMNS,
    build_report,
    report_to_csv,
    report_to_html,
    save_report_csv,
    save_report_html,
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


def _sample_report() -> object:
    """Build a sample report for testing."""
    return build_report(benchmark_name="mock", results=_sample_results())


# ----------------------------------------------------------------------
# CSV generation
# ----------------------------------------------------------------------
class TestCsvGeneration:
    """Tests for CSV report generation."""

    def test_csv_has_header(self) -> None:
        report = _sample_report()
        text = report_to_csv(report)
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames == CSV_COLUMNS

    def test_csv_has_all_rows(self) -> None:
        report = _sample_report()
        text = report_to_csv(report)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 3

    def test_csv_content(self) -> None:
        report = _sample_report()
        text = report_to_csv(report)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert rows[0]["test_case_id"] == "attack-1"
        assert rows[0]["expected_decision"] == "BLOCK"
        assert rows[0]["actual_decision"] == "BLOCK"
        assert rows[0]["succeeded"] == "True"
        assert rows[1]["succeeded"] == "False"

    def test_csv_empty_results(self) -> None:
        report = build_report(benchmark_name="mock", results=[])
        text = report_to_csv(report)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 0
        assert reader.fieldnames == CSV_COLUMNS

    def test_csv_failed_evaluation_error(self) -> None:
        results = [
            _result("tc1", "ALLOW", "ALLOW"),
            _result("tc2", "BLOCK", "ALLOW", error="simulated failure"),
        ]
        report = build_report(benchmark_name="mock", results=results)
        text = report_to_csv(report)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert rows[1]["error"] == "simulated failure"


# ----------------------------------------------------------------------
# CSV file saving
# ----------------------------------------------------------------------
class TestCsvFileSaving:
    """Tests for saving CSV reports to files."""

    def test_save_csv_file(self, tmp_path) -> None:
        report = _sample_report()
        path = tmp_path / "report.csv"
        save_report_csv(report, path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "test_case_id" in content
        assert "attack-1" in content

    def test_save_csv_creates_dirs(self, tmp_path) -> None:
        report = _sample_report()
        path = tmp_path / "nested" / "dir" / "report.csv"
        save_report_csv(report, path)
        assert path.exists()


# ----------------------------------------------------------------------
# HTML generation
# ----------------------------------------------------------------------
class TestHtmlGeneration:
    """Tests for HTML report generation."""

    def test_html_contains_benchmark_name(self) -> None:
        report = _sample_report()
        html = report_to_html(report)
        assert "mock" in html
        assert "<html>" in html
        assert "</html>" in html

    def test_html_contains_summary(self) -> None:
        report = _sample_report()
        html = report_to_html(report)
        assert "Total:" in html
        assert "Passed:" in html
        assert "Failed:" in html

    def test_html_contains_metrics(self) -> None:
        report = _sample_report()
        html = report_to_html(report)
        assert "Detection Metrics" in html
        assert "Detection Rate" in html
        assert "Accuracy" in html

    def test_html_contains_latency(self) -> None:
        report = _sample_report()
        html = report_to_html(report)
        assert "Latency Statistics" in html
        assert "Average (ms)" in html
        assert "p95 (ms)" in html

    def test_html_contains_results(self) -> None:
        report = _sample_report()
        html = report_to_html(report)
        assert "attack-1" in html
        assert "benign-1" in html

    def test_html_empty_results(self) -> None:
        report = build_report(benchmark_name="mock", results=[])
        html = report_to_html(report)
        assert "No results" in html

    def test_html_escapes_values(self) -> None:
        results = [
            _result("tc1", "ALLOW", "ALLOW", error="<script>alert('xss')</script>"),
        ]
        report = build_report(benchmark_name="mock", results=results)
        html = report_to_html(report)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_save_html_file(self, tmp_path) -> None:
        report = _sample_report()
        path = tmp_path / "report.html"
        save_report_html(report, path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "<html>" in content
        assert "mock" in content