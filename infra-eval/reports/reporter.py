"""
Report generation module.

Provides structured evaluation report data and JSON serialization.
Combines existing evaluation models (EvaluationSummary, DetectionMetrics,
BaselineComparison, LatencyStats) with benchmark metadata and individual
evaluation results into a single JSON-serializable report.

All data is derived from actual supplied evaluation results — nothing is
hardcoded or fabricated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from evaluation.adapters import BenchmarkMeta
from evaluation.evaluator import EvaluationResult, EvaluationSummary
from evaluation.metrics import (
    BaselineComparison,
    DetectionMetrics,
    LatencyStats,
    compare_baseline,
    compute_latency_stats,
    compute_metrics,
)


@dataclass
class EvaluationReport:
    """
    Structured evaluation report combining all evaluation data.

    Attributes:
        benchmark_name: Name of the benchmark.
        timestamp: ISO-8601 timestamp of report creation.
        summary: Evaluation summary (total/passed/failed).
        metrics: Detection metrics for the monitored run.
        baseline_metrics: Optional detection metrics for the baseline run.
        comparison: Optional baseline comparison.
        latency: Latency statistics.
        results: Individual evaluation results.
        errors: List of error messages from failed evaluations.
        metadata: Optional benchmark metadata.
    """

    benchmark_name: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    summary: Optional[EvaluationSummary] = None
    metrics: Optional[DetectionMetrics] = None
    baseline_metrics: Optional[DetectionMetrics] = None
    comparison: Optional[BaselineComparison] = None
    latency: Optional[LatencyStats] = None
    results: List[EvaluationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Optional[BenchmarkMeta] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary of the report."""
        return {
            "benchmark_name": self.benchmark_name,
            "timestamp": self.timestamp,
            "total_test_cases": self.summary.total if self.summary else len(self.results),
            "passed": self.summary.passed if self.summary else 0,
            "failed": self.summary.failed if self.summary else 0,
            "detection_metrics": (
                self.metrics.to_dict() if self.metrics else None
            ),
            "baseline": (
                self.baseline_metrics.to_dict() if self.baseline_metrics else None
            ),
            "monitored": (
                self.metrics.to_dict() if self.metrics else None
            ),
            "comparison": (
                self.comparison.to_dict() if self.comparison else None
            ),
            "latency": (
                self.latency.to_dict() if self.latency else None
            ),
            "errors": self.errors,
            "metadata": (
                self.metadata.to_dict() if self.metadata else None
            ),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """Return the report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


def build_report(
    *,
    benchmark_name: str,
    results: Sequence[EvaluationResult],
    baseline_results: Optional[Sequence[EvaluationResult]] = None,
    metadata: Optional[BenchmarkMeta] = None,
    timestamp: Optional[str] = None,
) -> EvaluationReport:
    """
    Build a structured evaluation report from supplied results.

    Args:
        benchmark_name: Name of the benchmark.
        results: Evaluation results for the monitored/protected run.
        baseline_results: Optional results for the baseline (unprotected) run.
        metadata: Optional benchmark metadata.
        timestamp: Optional ISO timestamp (defaults to now).

    Returns:
        An :class:`EvaluationReport` with all computed metrics.
    """
    result_list = list(results)
    summary = EvaluationSummary()
    for r in result_list:
        summary.add_result(r)

    metrics = compute_metrics(result_list)
    latency = compute_latency_stats(result_list)

    errors = [
        r.error
        for r in result_list
        if r.error is not None
    ]

    baseline_metrics: Optional[DetectionMetrics] = None
    comparison: Optional[BaselineComparison] = None
    if baseline_results is not None:
        baseline_list = list(baseline_results)
        baseline_metrics = compute_metrics(baseline_list)
        comparison = compare_baseline(baseline_list, result_list)

    return EvaluationReport(
        benchmark_name=benchmark_name,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        summary=summary,
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        comparison=comparison,
        latency=latency,
        results=result_list,
        errors=errors,
        metadata=metadata,
    )


def report_to_json(report: EvaluationReport, indent: int = 2) -> str:
    """
    Serialize an :class:`EvaluationReport` to a JSON string.

    Args:
        report: The report to serialize.
        indent: JSON indentation level.

    Returns:
        A JSON string representation of the report.
    """
    return report.to_json(indent=indent)


def save_report_json(report: EvaluationReport, path: Any) -> None:
    """
    Save an :class:`EvaluationReport` to a JSON file.

    Args:
        report: The report to save.
        path: Destination file path.
    """
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.to_json(), encoding="utf-8")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

#: Columns exported for each evaluation result in CSV format.
CSV_COLUMNS = [
    "test_case_id",
    "expected_decision",
    "actual_decision",
    "succeeded",
    "risk_score",
    "execution_time_ms",
    "latency_ms",
    "category",
    "error",
]


def report_to_csv(report: EvaluationReport) -> str:
    """
    Serialize an :class:`EvaluationReport`'s results to a CSV string.

    Args:
        report: The report to serialize.

    Returns:
        A CSV string with a header row and one row per evaluation result.
    """
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for result in report.results:
        writer.writerow({
            "test_case_id": result.test_case_id,
            "expected_decision": result.expected_decision,
            "actual_decision": result.actual_decision,
            "succeeded": result.succeeded,
            "risk_score": result.risk_score,
            "execution_time_ms": result.execution_time_ms,
            "latency_ms": result.latency_ms,
            "category": result.category,
            "error": result.error,
        })
    return buffer.getvalue()


def save_report_csv(report: EvaluationReport, path: Any) -> None:
    """
    Save an :class:`EvaluationReport`'s results to a CSV file.

    Args:
        report: The report to save.
        path: Destination file path.
    """
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report_to_csv(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------

def _html_escape(value: Any) -> str:
    """Escape a value for safe inclusion in HTML."""
    import html

    if value is None:
        return ""
    return html.escape(str(value))


def report_to_html(report: EvaluationReport) -> str:
    """
    Serialize an :class:`EvaluationReport` to a human-readable HTML string.

    Uses only the Python standard library (no heavy dependencies).

    Args:
        report: The report to serialize.

    Returns:
        An HTML string with benchmark summary, metrics, baseline comparison,
        latency statistics, and individual results.
    """
    data = report.to_dict()
    metrics = data.get("detection_metrics") or {}
    baseline = data.get("baseline") or {}
    monitored = data.get("monitored") or {}
    comparison = data.get("comparison") or {}
    improvements = comparison.get("improvements") or {}
    latency = data.get("latency") or {}

    rows = []
    for result in report.results:
        rows.append(
            "<tr>"
            f"<td>{_html_escape(result.test_case_id)}</td>"
            f"<td>{_html_escape(result.expected_decision)}</td>"
            f"<td>{_html_escape(result.actual_decision)}</td>"
            f"<td>{'✅' if result.succeeded else '❌'}</td>"
            f"<td>{_html_escape(result.risk_score)}</td>"
            f"<td>{_html_escape(result.execution_time_ms)}</td>"
            f"<td>{_html_escape(result.latency_ms)}</td>"
            f"<td>{_html_escape(result.category)}</td>"
            f"<td>{_html_escape(result.error)}</td>"
            "</tr>"
        )
    results_html = "\n".join(rows) if rows else "<tr><td colspan='9'>No results</td></tr>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Evaluation Report: {_html_escape(report.benchmark_name)}</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
h1, h2 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
th {{ background: #f0f0f0; }}
.summary {{ display: flex; gap: 2em; margin-bottom: 1em; }}
.summary div {{ background: #f8f8f8; padding: 1em; border-radius: 4px; }}
</style>
</head>
<body>
<h1>Evaluation Report: {_html_escape(report.benchmark_name)}</h1>
<p><strong>Timestamp:</strong> {_html_escape(report.timestamp)}</p>

<h2>Summary</h2>
<div class="summary">
<div><strong>Total:</strong> {data.get('total_test_cases', 0)}</div>
<div><strong>Passed:</strong> {data.get('passed', 0)}</div>
<div><strong>Failed:</strong> {data.get('failed', 0)}</div>
</div>

<h2>Detection Metrics</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Attacks</td><td>{_html_escape(metrics.get('total_attacks'))}</td></tr>
<tr><td>Total Benign</td><td>{_html_escape(metrics.get('total_benign'))}</td></tr>
<tr><td>Attacks Detected</td><td>{_html_escape(metrics.get('attacks_detected'))}</td></tr>
<tr><td>Attacks Missed</td><td>{_html_escape(metrics.get('attacks_missed'))}</td></tr>
<tr><td>Benign Allowed</td><td>{_html_escape(metrics.get('benign_allowed'))}</td></tr>
<tr><td>Benign Blocked</td><td>{_html_escape(metrics.get('benign_blocked'))}</td></tr>
<tr><td>Detection Rate</td><td>{_html_escape(metrics.get('detection_rate'))}</td></tr>
<tr><td>False Positive Rate</td><td>{_html_escape(metrics.get('false_positive_rate'))}</td></tr>
<tr><td>False Negative Rate</td><td>{_html_escape(metrics.get('false_negative_rate'))}</td></tr>
<tr><td>Accuracy</td><td>{_html_escape(metrics.get('accuracy'))}</td></tr>
</table>

<h2>Baseline Comparison</h2>
<table>
<tr><th>Metric</th><th>Baseline</th><th>Monitored</th><th>Delta</th></tr>
<tr><td>Detection Rate</td><td>{_html_escape(baseline.get('detection_rate'))}</td><td>{_html_escape(monitored.get('detection_rate'))}</td><td>{_html_escape(improvements.get('detection_rate'))}</td></tr>
<tr><td>False Positive Rate</td><td>{_html_escape(baseline.get('false_positive_rate'))}</td><td>{_html_escape(monitored.get('false_positive_rate'))}</td><td>{_html_escape(improvements.get('false_positive_rate'))}</td></tr>
<tr><td>False Negative Rate</td><td>{_html_escape(baseline.get('false_negative_rate'))}</td><td>{_html_escape(monitored.get('false_negative_rate'))}</td><td>{_html_escape(improvements.get('false_negative_rate'))}</td></tr>
<tr><td>Accuracy</td><td>{_html_escape(baseline.get('accuracy'))}</td><td>{_html_escape(monitored.get('accuracy'))}</td><td>{_html_escape(improvements.get('accuracy'))}</td></tr>
</table>

<h2>Latency Statistics</h2>
<table>
<tr><th>Statistic</th><th>Value</th></tr>
<tr><td>Samples</td><td>{_html_escape(latency.get('samples'))}</td></tr>
<tr><td>Average (ms)</td><td>{_html_escape(latency.get('average_ms'))}</td></tr>
<tr><td>Min (ms)</td><td>{_html_escape(latency.get('min_ms'))}</td></tr>
<tr><td>Max (ms)</td><td>{_html_escape(latency.get('max_ms'))}</td></tr>
<tr><td>Median (ms)</td><td>{_html_escape(latency.get('median_ms'))}</td></tr>
<tr><td>p95 (ms)</td><td>{_html_escape(latency.get('p95_ms'))}</td></tr>
</table>

<h2>Individual Results</h2>
<table>
<tr><th>ID</th><th>Expected</th><th>Actual</th><th>Pass</th><th>Risk</th><th>Time (ms)</th><th>Latency (ms)</th><th>Category</th><th>Error</th></tr>
{results_html}
</table>
</body>
</html>
"""


def save_report_html(report: EvaluationReport, path: Any) -> None:
    """
    Save an :class:`EvaluationReport` to an HTML file.

    Args:
        report: The report to save.
        path: Destination file path.
    """
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report_to_html(report), encoding="utf-8")
