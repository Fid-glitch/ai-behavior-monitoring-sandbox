# Evaluation & Benchmark Testing Framework

from __future__ import annotations

from .adapters import (
    BenchmarkAdapterError,
    BenchmarkDataset,
    BenchmarkMeta,
    BaseBenchmarkAdapter,
    CsvBenchmarkAdapter,
    JsonBenchmarkAdapter,
    JsonlBenchmarkAdapter,
    MalformedBenchmarkError,
    MockBenchmarkAdapter,
    UnknownBenchmarkError,
    UnsupportedFormatError,
    get_adapter_class,
    load_benchmark,
    register_adapter,
    supported_benchmarks,
)
from .evaluator import (
    EvaluationError,
    EvaluationResult,
    EvaluationSummary,
    Evaluator,
    InvalidTestCaseError,
    MalformedTestSuiteError,
    TestCase,
)
from .metrics import (
    BaselineComparison,
    DetectionMetrics,
    LatencyStats,
    compare_baseline,
    compute_latency_stats,
    compute_metrics,
)
from .pipeline import (
    EvaluationPipeline,
    PipelineConfig,
    PipelineError,
)

__all__ = [
    "BaseBenchmarkAdapter",
    "BaselineComparison",
    "BenchmarkAdapterError",
    "BenchmarkDataset",
    "BenchmarkMeta",
    "CsvBenchmarkAdapter",
    "DetectionMetrics",
    "EvaluationError",
    "EvaluationPipeline",
    "EvaluationResult",
    "EvaluationSummary",
    "Evaluator",
    "InvalidTestCaseError",
    "JsonBenchmarkAdapter",
    "JsonlBenchmarkAdapter",
    "LatencyStats",
    "MalformedBenchmarkError",
    "MalformedTestSuiteError",
    "MockBenchmarkAdapter",
    "PipelineConfig",
    "PipelineError",
    "TestCase",
    "UnknownBenchmarkError",
    "UnsupportedFormatError",
    "compare_baseline",
    "compute_latency_stats",
    "compute_metrics",
    "get_adapter_class",
    "load_benchmark",
    "register_adapter",
    "supported_benchmarks",
]