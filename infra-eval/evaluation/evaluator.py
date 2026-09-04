"""
Evaluation core module.

Provides a clean, dependency-free evaluator that runs structured local test
cases in a **mock / dry-run** mode. The mock mode requires no API keys,
internet access, Docker, AgentDojo, or ToolEmu.

Each evaluation result is stored in the existing SQLite database
(:class:`database.Database` from Step 4) using the ``performance_records``
table.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from database import Database
from logging_system import LogDecision


class EvaluationError(RuntimeError):
    """Base exception for evaluation-core failures."""


class InvalidTestCaseError(EvaluationError):
    """Raised when a test case is malformed or missing required fields."""


class MalformedTestSuiteError(EvaluationError):
    """Raised when the test suite (file/list) cannot be parsed."""


@dataclass
class TestCase:
    """A single structured local test case."""

    test_case_id: str
    prompt: str
    expected_decision: str = LogDecision.ALLOW.value
    category: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        """Build a TestCase from a dictionary."""
        if not isinstance(data, dict):
            raise InvalidTestCaseError(
                f"Test case must be a dictionary, got {type(data).__name__}"
            )
        test_case_id = data.get("test_case_id") or data.get("id")
        if not test_case_id:
            raise InvalidTestCaseError("Test case is missing 'test_case_id'")
        prompt = data.get("prompt") or data.get("input")
        if prompt is None:
            raise InvalidTestCaseError(
                f"Test case '{test_case_id}' is missing 'prompt' or 'input'"
            )
        expected = data.get("expected_decision") or LogDecision.ALLOW.value
        try:
            normalized = _normalize_decision(expected)
        except InvalidTestCaseError:
            raise InvalidTestCaseError(
                f"Test case '{test_case_id}' has invalid expected_decision: {expected!r}"
            )
        category = data.get("category") or "general"
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise InvalidTestCaseError(
                f"Test case '{test_case_id}' metadata must be a dictionary"
            )
        return cls(
            test_case_id=str(test_case_id),
            prompt=str(prompt),
            expected_decision=normalized,
            category=str(category),
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the test case."""
        return {
            "test_case_id": self.test_case_id,
            "prompt": self.prompt,
            "expected_decision": self.expected_decision,
            "category": self.category,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationResult:
    """The outcome of evaluating a single test case."""

    test_case_id: str
    expected_decision: str
    actual_decision: str
    risk_score: Optional[float] = None
    succeeded: bool = False
    execution_time_ms: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None
    category: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the result."""
        return {
            "test_case_id": self.test_case_id,
            "expected_decision": self.expected_decision,
            "actual_decision": self.actual_decision,
            "risk_score": self.risk_score,
            "succeeded": self.succeeded,
            "execution_time_ms": self.execution_time_ms,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "category": self.category,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationSummary:
    """Aggregate summary of a full evaluation run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    results: List[EvaluationResult] = field(default_factory=list)

    def add_result(self, result: EvaluationResult) -> None:
        """Add a single result and update counters."""
        self.total += 1
        if result.succeeded:
            self.passed += 1
        else:
            self.failed += 1
        self.results.append(result)


def _normalize_decision(decision: str) -> str:
    """Normalize a decision string to ALLOW / BLOCK / WARNING."""
    normalized = decision.upper()
    if normalized not in {d.value for d in LogDecision}:
        raise InvalidTestCaseError(f"Invalid decision: {decision!r}")
    return normalized


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _default_risk_for_decision(decision: str) -> float:
    """Return a default risk score for a decision."""
    if decision == LogDecision.BLOCK.value:
        return 0.9
    if decision == LogDecision.WARNING.value:
        return 0.5
    return 0.1


class Evaluator:
    """Mock / dry-run evaluator for structured local test cases."""

    def __init__(
        self,
        db: Optional[Database] = None,
        mock_decision: Optional[str] = None,
        record_results: bool = True,
    ) -> None:
        self.db = db
        self.record_results = record_results
        self.mock_decision = (
            _normalize_decision(mock_decision) if mock_decision else None
        )
        self._summary = EvaluationSummary()

    def load_test_cases(
        self,
        data: Union[List[Dict[str, Any]], List[TestCase], Dict[str, Any]],
    ) -> List[TestCase]:
        """Load structured local test cases."""
        items: List[Any]
        if isinstance(data, dict):
            if "test_cases" in data and isinstance(data["test_cases"], list):
                items = data["test_cases"]
            else:
                items = [data]
        elif isinstance(data, list):
            items = data
        else:
            raise MalformedTestSuiteError(
                f"Test suite must be a list or dictionary, got {type(data).__name__}"
            )

        test_cases: List[TestCase] = []
        for item in items:
            try:
                if isinstance(item, TestCase):
                    test_cases.append(item)
                else:
                    test_cases.append(TestCase.from_dict(item))
            except InvalidTestCaseError as exc:
                raise MalformedTestSuiteError(str(exc)) from exc
        return test_cases

    def evaluate(
        self,
        test_cases: Union[List[Dict[str, Any]], List[TestCase], Dict[str, Any]],
    ) -> EvaluationSummary:
        """Evaluate a set of test cases."""
        cases = self.load_test_cases(test_cases)
        summary = EvaluationSummary()
        for case in cases:
            result = self.evaluate_one(case)
            summary.add_result(result)
        self._summary = summary
        return summary

    def evaluate_one(self, test_case: TestCase) -> EvaluationResult:
        """Evaluate a single TestCase in mock/dry-run mode."""
        start = time.perf_counter()
        error: Optional[str] = None
        actual_decision: str = test_case.expected_decision
        risk_score: Optional[float] = None

        try:
            if self.mock_decision is not None:
                actual_decision = self.mock_decision
            else:
                actual_decision = test_case.expected_decision
            risk_score = _default_risk_for_decision(actual_decision)
        except Exception as exc:  # pragma: no cover
            error = str(exc)
            actual_decision = LogDecision.ALLOW.value
            risk_score = None

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        succeeded = actual_decision == test_case.expected_decision

        result = EvaluationResult(
            test_case_id=test_case.test_case_id,
            expected_decision=test_case.expected_decision,
            actual_decision=actual_decision,
            risk_score=risk_score,
            succeeded=succeeded,
            execution_time_ms=elapsed_ms,
            latency_ms=elapsed_ms,
            error=error,
            category=test_case.category,
            metadata=dict(test_case.metadata),
        )

        if self.record_results and self.db is not None:
            self._persist_result(test_case, result)

        return result

    def evaluate_case_dict(self, data: Dict[str, Any]) -> EvaluationResult:
        """Evaluate a single test case from a dictionary."""
        return self.evaluate_one(TestCase.from_dict(data))

    @property
    def is_mock_mode(self) -> bool:
        """Whether the evaluator is running in mock / dry-run mode."""
        return True

    @property
    def requires_external_services(self) -> bool:
        """Whether external services are required. Always False."""
        return False

    def _persist_result(
        self,
        test_case: TestCase,
        result: EvaluationResult,
    ) -> None:
        """Persist an evaluation result to the SQLite database."""
        if self.db is None:
            return
        metadata = {
            "test_case_id": result.test_case_id,
            "category": result.category,
            "expected_decision": result.expected_decision,
            "actual_decision": result.actual_decision,
            "succeeded": result.succeeded,
            **result.metadata,
            **test_case.metadata,
        }
        self.db.insert_performance_record(
            benchmark_name="mock-evaluation",
            execution_time_ms=result.execution_time_ms,
            latency_ms=result.latency_ms,
            result=1.0 if result.succeeded else 0.0,
            evaluation_score=result.risk_score,
            metadata=metadata,
        )

    @property
    def last_summary(self) -> EvaluationSummary:
        """Return the summary from the most recent evaluation run."""
        return self._summary

    def clear(self) -> None:
        """Reset the stored summary."""
        self._summary = EvaluationSummary()