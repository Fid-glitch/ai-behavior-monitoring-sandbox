"""
End-to-end evaluation pipeline.

Orchestrates the existing components into a single runnable flow:

    Benchmark Adapter -> Evaluator -> Evaluation Results
        -> Metrics -> Baseline Comparison -> Latency Statistics
        -> SQLite persistence -> EvaluationReport

All components are reused from Steps 4-5D. No duplicate logic is created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from database import Database
from evaluation.adapters import (
    BenchmarkDataset,
    BenchmarkMeta,
    load_benchmark,
)
from evaluation.evaluator import EvaluationResult, Evaluator, TestCase
from reports import (
    EvaluationReport,
    build_report,
    save_report_csv,
    save_report_html,
    save_report_json,
)


class PipelineError(RuntimeError):
    """Base exception for pipeline failures."""


@dataclass
class PipelineConfig:
    """
    Configuration for the evaluation pipeline.

    Attributes:
        benchmark_name: Name of the benchmark.
        output_dir: Optional directory for generated reports.
        generate_json: Whether to write a JSON report.
        generate_csv: Whether to write a CSV report.
        generate_html: Whether to write an HTML report.
        record_results: Whether to persist results to SQLite.
        mock_decision: Optional forced decision for mock mode.
    """

    benchmark_name: str
    output_dir: Optional[Union[str, Path]] = None
    generate_json: bool = True
    generate_csv: bool = True
    generate_html: bool = True
    record_results: bool = True
    mock_decision: Optional[str] = None


class EvaluationPipeline:
    """
    Orchestrates benchmark loading, evaluation, metrics, and reporting.

    Args:
        db: Optional :class:`database.Database` for SQLite persistence.
        config: Optional :class:`PipelineConfig`. A default config is used
            when omitted.
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.db = db
        self.config = config or PipelineConfig(benchmark_name="default")
        self.evaluator = Evaluator(
            db=db,
            mock_decision=self.config.mock_decision,
            record_results=self.config.record_results,
        )

    # ------------------------------------------------------------------
    # Main entrypoint
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        benchmark_name: Optional[str] = None,
        test_cases: Optional[Union[List[Dict[str, Any]], List[TestCase], Dict[str, Any]]] = None,
        benchmark: Optional[str] = None,
        path: Optional[Union[str, Path]] = None,
        format: Optional[str] = None,
        records: Optional[List[Dict[str, Any]]] = None,
        baseline_results: Optional[Sequence[EvaluationResult]] = None,
        metadata: Optional[BenchmarkMeta] = None,
        output_dir: Optional[Union[str, Path]] = None,
        generate_json: Optional[bool] = None,
        generate_csv: Optional[bool] = None,
        generate_html: Optional[bool] = None,
    ) -> EvaluationReport:
        """
        Run the full evaluation pipeline.

        Args:
            benchmark_name: Override the benchmark name.
            test_cases: Direct test cases (bypasses adapter loading).
            benchmark: Benchmark adapter name (e.g. "mock", "json").
            path: Path to a benchmark file.
            format: Format hint for the adapter.
            records: Raw records to load.
            baseline_results: Optional baseline evaluation results.
            metadata: Optional benchmark metadata.
            output_dir: Override the report output directory.
            generate_json/csv/html: Override report generation flags.

        Returns:
            An :class:`EvaluationReport` with all computed data.

        Raises:
            PipelineError: If the pipeline cannot complete.
        """
        name = benchmark_name or self.config.benchmark_name

        # 1. Load test cases (via adapter or direct)
        try:
            if test_cases is not None:
                cases = self.evaluator.load_test_cases(test_cases)
            elif records is not None or path is not None or benchmark is not None or format is not None:
                dataset = load_benchmark(
                    path=Path(path) if path else None,
                    format=format,
                    benchmark=benchmark,
                    records=records,
                )
                cases = dataset.test_cases
                if metadata is None:
                    metadata = dataset.meta
            else:
                # Default to the mock benchmark for dry-run mode.
                dataset = load_benchmark(benchmark="mock")
                cases = dataset.test_cases
                if metadata is None:
                    metadata = dataset.meta
        except Exception as exc:
            raise PipelineError(f"Failed to load benchmark: {exc}") from exc

        # 2. Evaluate all test cases
        try:
            summary = self.evaluator.evaluate(cases)
        except Exception as exc:
            raise PipelineError(f"Failed to evaluate test cases: {exc}") from exc

        # 3. Build the report (metrics, baseline, latency computed inside)
        try:
            report = build_report(
                benchmark_name=name,
                results=summary.results,
                baseline_results=baseline_results,
                metadata=metadata,
            )
        except Exception as exc:
            raise PipelineError(f"Failed to build report: {exc}") from exc

        # 4. Generate output reports
        out_dir = output_dir or self.config.output_dir
        if out_dir is not None:
            self._write_reports(
                report,
                out_dir=Path(out_dir),
                generate_json=(
                    generate_json if generate_json is not None else self.config.generate_json
                ),
                generate_csv=(
                    generate_csv if generate_csv is not None else self.config.generate_csv
                ),
                generate_html=(
                    generate_html if generate_html is not None else self.config.generate_html
                ),
            )

        return report

    # ------------------------------------------------------------------
    # Report writing
    # ------------------------------------------------------------------

    def _write_reports(
        self,
        report: EvaluationReport,
        *,
        out_dir: Path,
        generate_json: bool,
        generate_csv: bool,
        generate_html: bool,
    ) -> None:
        """Write report files to the output directory."""
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = report.benchmark_name.replace(" ", "_").replace("/", "_")
        if generate_json:
            save_report_json(report, out_dir / f"{safe_name}_report.json")
        if generate_csv:
            save_report_csv(report, out_dir / f"{safe_name}_results.csv")
        if generate_html:
            save_report_html(report, out_dir / f"{safe_name}_report.html")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def run_mock(
        self,
        *,
        benchmark_name: str = "mock",
        baseline_results: Optional[Sequence[EvaluationResult]] = None,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> EvaluationReport:
        """Run the pipeline against the built-in mock benchmark."""
        return self.run(
            benchmark_name=benchmark_name,
            benchmark="mock",
            baseline_results=baseline_results,
            output_dir=output_dir,
        )

    @property
    def is_mock_mode(self) -> bool:
        """Whether the pipeline is running in mock/dry-run mode."""
        return self.evaluator.is_mock_mode