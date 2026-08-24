"""
Unit tests for the end-to-end evaluation pipeline.

Tests cover pipeline initialization, mock benchmark -> evaluator,
evaluator -> metrics, metrics -> report, SQLite persistence, report
generation (JSON/CSV/HTML), empty benchmarks, and error handling.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from database import Database
from evaluation import (
    EvaluationPipeline,
    EvaluationResult,
    PipelineConfig,
    PipelineError,
)
from reports import EvaluationReport


def _baseline_results() -> list:
    """Return a list of baseline (unprotected) results."""
    return [
        EvaluationResult(
            test_case_id="b1",
            expected_decision="BLOCK",
            actual_decision="ALLOW",
            succeeded=False,
            execution_time_ms=5.0,
            latency_ms=5.0,
        ),
        EvaluationResult(
            test_case_id="b2",
            expected_decision="ALLOW",
            actual_decision="ALLOW",
            succeeded=True,
            execution_time_ms=5.0,
            latency_ms=5.0,
        ),
    ]


# ----------------------------------------------------------------------
# Pipeline initialization
# ----------------------------------------------------------------------
class TestPipelineInit:
    """Tests for pipeline construction."""

    def test_pipeline_created_no_db(self) -> None:
        pipeline = EvaluationPipeline(config=PipelineConfig(benchmark_name="test"))
        assert pipeline.db is None
        assert pipeline.evaluator is not None
        assert pipeline.is_mock_mode is True

    def test_pipeline_created_with_db(self, tmp_path) -> None:
        db = Database(tmp_path / "pipe.db")
        pipeline = EvaluationPipeline(db=db)
        assert pipeline.db is not None
        db.close()

    def test_pipeline_default_config(self) -> None:
        pipeline = EvaluationPipeline()
        assert pipeline.config.benchmark_name == "default"
        assert pipeline.config.generate_json is True
        assert pipeline.config.generate_csv is True
        assert pipeline.config.generate_html is True

    def test_pipeline_custom_config(self) -> None:
        config = PipelineConfig(
            benchmark_name="my-bench",
            output_dir="out",
            generate_json=False,
            generate_csv=False,
            generate_html=False,
        )
        pipeline = EvaluationPipeline(config=config)
        assert pipeline.config.benchmark_name == "my-bench"
        assert pipeline.config.generate_json is False


# ----------------------------------------------------------------------
# Mock benchmark -> evaluator
# ----------------------------------------------------------------------
class TestMockBenchmarkFlow:
    """Tests for running the pipeline against the mock benchmark."""

    def test_mock_benchmark_run(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run_mock(benchmark_name="mock")
        assert isinstance(report, EvaluationReport)
        assert report.benchmark_name == "mock"
        assert report.summary is not None
        assert report.summary.total > 0

    def test_mock_benchmark_all_pass(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run_mock()
        assert report.summary.passed == report.summary.total

    def test_mock_run_with_baseline(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run(
            benchmark="mock",
            benchmark_name="mock-bench",
            baseline_results=_baseline_results(),
        )
        assert report.baseline_metrics is not None
        assert report.comparison is not None


# ----------------------------------------------------------------------
# Evaluator -> metrics
# ----------------------------------------------------------------------
class TestEvaluatorToMetrics:
    """Test that evaluation results flow into metrics."""

    def test_metrics_computed(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run(
            test_cases=[
                {"test_case_id": "a1", "prompt": "attack", "expected_decision": "BLOCK"},
                {"test_case_id": "b1", "prompt": "benign", "expected_decision": "ALLOW"},
            ],
            benchmark_name="direct",
        )
        assert report.metrics is not None
        assert report.metrics.total_attacks == 1
        assert report.metrics.total_benign == 1


# ----------------------------------------------------------------------
# Metrics -> report
# ----------------------------------------------------------------------
class TestMetricsToReport:
    """Test report creation from metrics."""

    def test_report_has_all_sections(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run_mock()
        data = report.to_dict()
        assert data["detection_metrics"] is not None
        assert data["latency"] is not None
        assert data["total_test_cases"] == report.summary.total


# ----------------------------------------------------------------------
# SQLite persistence
# ----------------------------------------------------------------------
class TestSqlitePersistence:
    """Test SQLite persistence through the pipeline."""

    def test_results_persisted(self, tmp_path) -> None:
        db = Database(tmp_path / "pipe.db")
        db.initialize()
        pipeline = EvaluationPipeline(db=db)
        pipeline.run_mock()
        records = db.query_performance_records(benchmark_name="mock-evaluation")
        assert len(records) > 0
        db.close()


# ----------------------------------------------------------------------
# Report generation
# ----------------------------------------------------------------------
class TestReportGeneration:
    """Test JSON/CSV/HTML report generation."""

    def test_json_report(self, tmp_path) -> None:
        out = tmp_path / "reports"
        pipeline = EvaluationPipeline(
            config=PipelineConfig(benchmark_name="mock", output_dir=out)
        )
        pipeline.run_mock()
        json_files = list(out.glob("*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["benchmark_name"] == "mock"

    def test_csv_report(self, tmp_path) -> None:
        out = tmp_path / "reports"
        pipeline = EvaluationPipeline(
            config=PipelineConfig(benchmark_name="mock", output_dir=out)
        )
        pipeline.run_mock()
        csv_files = list(out.glob("*.csv"))
        assert len(csv_files) == 1
        reader = csv.DictReader(io.StringIO(csv_files[0].read_text(encoding="utf-8")))
        rows = list(reader)
        assert len(rows) > 0

    def test_html_report(self, tmp_path) -> None:
        out = tmp_path / "reports"
        pipeline = EvaluationPipeline(
            config=PipelineConfig(benchmark_name="mock", output_dir=out)
        )
        pipeline.run_mock()
        html_files = list(out.glob("*.html"))
        assert len(html_files) == 1
        content = html_files[0].read_text(encoding="utf-8")
        assert "<html>" in content

    def test_no_reports_when_disabled(self, tmp_path) -> None:
        out = tmp_path / "reports"
        pipeline = EvaluationPipeline(
            config=PipelineConfig(
                benchmark_name="mock",
                output_dir=out,
                generate_json=False,
                generate_csv=False,
                generate_html=False,
            )
        )
        pipeline.run_mock()
        assert list(out.iterdir()) == []


# ----------------------------------------------------------------------
# Empty benchmark
# ----------------------------------------------------------------------
class TestEmptyBenchmark:
    """Test pipeline behavior with empty test cases."""

    def test_empty_benchmark(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run(
            benchmark_name="empty",
            test_cases=[],
        )
        assert report.summary.total == 0
        assert report.summary.passed == 0
        assert report.summary.failed == 0


# ----------------------------------------------------------------------
# Pipeline error handling
# ----------------------------------------------------------------------
class TestPipelineErrors:
    """Test pipeline error handling."""

    def test_invalid_benchmark_raises(self) -> None:
        pipeline = EvaluationPipeline()
        with pytest.raises(PipelineError):
            pipeline.run(benchmark="nonexistent")

    def test_invalid_test_cases_raise(self) -> None:
        pipeline = EvaluationPipeline()
        with pytest.raises(PipelineError):
            pipeline.run(test_cases=[{"missing_id": "bad"}])


# ----------------------------------------------------------------------
# Baseline results
# ----------------------------------------------------------------------
class TestBaselineResults:
    """Test baseline results flow through the pipeline."""

    def test_baseline_comparison(self) -> None:
        pipeline = EvaluationPipeline()
        report = pipeline.run(
            benchmark="mock",
            benchmark_name="mock",
            baseline_results=_baseline_results(),
        )
        assert report.comparison is not None
        assert report.comparison.baseline_metrics is not None
        assert report.comparison.monitored_metrics is not None