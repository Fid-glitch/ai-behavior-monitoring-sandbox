"""
Unit tests for the evaluation core.

Tests cover evaluator initialisation, local test-case loading, mock
evaluation, result creation, successful/failed evaluations, empty test
cases, and malformed test cases.
"""

from __future__ import annotations

import pytest

from database import Database
from evaluation import (
    EvaluationResult,
    EvaluationSummary,
    Evaluator,
    InvalidTestCaseError,
    MalformedTestSuiteError,
    TestCase,
)


# ----------------------------------------------------------------------
# Evaluator initialisation
# ----------------------------------------------------------------------
class TestEvaluatorInit:
    """Tests for evaluator construction."""

    def test_evaluator_created_without_db(self) -> None:
        evaluator = Evaluator()
        assert evaluator.db is None
        assert evaluator.is_mock_mode is True
        assert evaluator.requires_external_services is False

    def test_evaluator_created_with_db(self, tmp_path) -> None:
        db = Database(tmp_path / "eval.db")
        evaluator = Evaluator(db=db)
        assert evaluator.db is not None
        evaluator.db.close()

    def test_evaluator_with_mock_decision(self) -> None:
        evaluator = Evaluator(mock_decision="BLOCK")
        assert evaluator.mock_decision == "BLOCK"

    def test_evaluator_invalid_mock_decision_raises(self) -> None:
        with pytest.raises(InvalidTestCaseError):
            Evaluator(mock_decision="NOT_A_DECISION")

    def test_evaluator_no_recording(self) -> None:
        evaluator = Evaluator(record_results=False)
        assert evaluator.record_results is False

    def test_last_summary_starts_empty(self) -> None:
        evaluator = Evaluator()
        assert evaluator.last_summary.total == 0
        assert evaluator.last_summary.passed == 0
        assert evaluator.last_summary.failed == 0


# ----------------------------------------------------------------------
# Test case loading
# ----------------------------------------------------------------------
class TestTestCaseLoading:
    """Tests for loading structured local test cases."""

    def test_load_from_list_of_dicts(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases([
            {"test_case_id": "tc1", "prompt": "hello", "expected_decision": "ALLOW"},
            {"test_case_id": "tc2", "prompt": "drop", "expected_decision": "BLOCK"},
        ])
        assert len(cases) == 2
        assert cases[0].expected_decision == "ALLOW"

    def test_load_from_dict_with_test_cases_key(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases({"test_cases": [{"test_case_id": "tc1", "prompt": "hello"}]})
        assert len(cases) == 1

    def test_load_single_dict(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases({"test_case_id": "tc1", "prompt": "hello"})
        assert len(cases) == 1

    def test_load_from_list_of_testcase_objects(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases([
            TestCase(test_case_id="tc1", prompt="hello"),
            TestCase(test_case_id="tc2", prompt="world"),
        ])
        assert len(cases) == 2

    def test_load_uses_input_alias(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases([{"test_case_id": "tc1", "input": "hello input"}])
        assert cases[0].prompt == "hello input"

    def test_load_uses_default_decision(self) -> None:
        evaluator = Evaluator()
        cases = evaluator.load_test_cases([{"test_case_id": "tc1", "prompt": "hello"}])
        assert cases[0].expected_decision == "ALLOW"

    def test_load_missing_id_raises(self) -> None:
        evaluator = Evaluator()
        with pytest.raises(MalformedTestSuiteError):
            evaluator.load_test_cases([{"prompt": "no id"}])

    def test_load_missing_prompt_raises(self) -> None:
        evaluator = Evaluator()
        with pytest.raises(MalformedTestSuiteError):
            evaluator.load_test_cases([{"test_case_id": "tc1"}])

    def test_load_invalid_decision_raises(self) -> None:
        evaluator = Evaluator()
        with pytest.raises(MalformedTestSuiteError):
            evaluator.load_test_cases([{"test_case_id": "tc1", "prompt": "hello", "expected_decision": "MAYBE"}])

    def test_load_invalid_structure_raises(self) -> None:
        evaluator = Evaluator()
        with pytest.raises(MalformedTestSuiteError):
            evaluator.load_test_cases("not a list")


# ----------------------------------------------------------------------
# TestCase model
# ----------------------------------------------------------------------
class TestTestCaseModel:
    """Tests for the TestCase dataclass."""

    def test_from_dict(self) -> None:
        case = TestCase.from_dict({
            "test_case_id": "tc1", "prompt": "hello", "expected_decision": "WARNING",
            "category": "security", "metadata": {"key": "value"},
        })
        assert case.expected_decision == "WARNING"

    def test_from_dict_normalizes_decision(self) -> None:
        case = TestCase.from_dict({"test_case_id": "tc1", "prompt": "hello", "expected_decision": "block"})
        assert case.expected_decision == "BLOCK"

    def test_to_dict(self) -> None:
        data = TestCase(test_case_id="tc1", prompt="hello").to_dict()
        assert data["expected_decision"] == "ALLOW"

    def test_from_dict_missing_fields_raises(self) -> None:
        with pytest.raises(InvalidTestCaseError):
            TestCase.from_dict({"prompt": "hello"})
        with pytest.raises(InvalidTestCaseError):
            TestCase.from_dict({"test_case_id": "tc1"})
        with pytest.raises(InvalidTestCaseError):
            TestCase.from_dict("not a dict")


# ----------------------------------------------------------------------
# Mock evaluation
# ----------------------------------------------------------------------
class TestMockEvaluation:
    """Tests for mock/dry-run evaluation."""

    def test_successful_evaluation(self) -> None:
        evaluator = Evaluator()
        result = evaluator.evaluate_one(TestCase(test_case_id="tc1", prompt="hello", expected_decision="ALLOW"))
        assert result.succeeded is True
        assert result.actual_decision == "ALLOW"
        assert result.risk_score is not None
        assert result.execution_time_ms >= 0

    def test_failed_evaluation_with_mock_decision(self) -> None:
        evaluator = Evaluator(mock_decision="BLOCK")
        result = evaluator.evaluate_one(TestCase(test_case_id="tc1", prompt="hello", expected_decision="ALLOW"))
        assert result.succeeded is False
        assert result.actual_decision == "BLOCK"

    def test_evaluate_multiple_cases(self) -> None:
        evaluator = Evaluator()
        summary = evaluator.evaluate([
            {"test_case_id": "tc1", "prompt": "a", "expected_decision": "ALLOW"},
            {"test_case_id": "tc2", "prompt": "b", "expected_decision": "BLOCK"},
            {"test_case_id": "tc3", "prompt": "c", "expected_decision": "WARNING"},
        ])
        assert summary.total == 3
        assert summary.passed == 3
        assert summary.failed == 0

    def test_empty_test_cases(self) -> None:
        evaluator = Evaluator()
        summary = evaluator.evaluate([])
        assert summary.total == 0

    def test_evaluate_case_dict(self) -> None:
        evaluator = Evaluator()
        result = evaluator.evaluate_case_dict({"test_case_id": "tc1", "prompt": "hello"})
        assert result.succeeded is True

    def test_last_summary_updated(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate([{"test_case_id": "tc1", "prompt": "hello"}])
        assert evaluator.last_summary.total == 1

    def test_clear_resets_summary(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate([{"test_case_id": "tc1", "prompt": "hello"}])
        evaluator.clear()
        assert evaluator.last_summary.total == 0


# ----------------------------------------------------------------------
# Database persistence
# ----------------------------------------------------------------------
class TestDatabasePersistence:
    """Tests for persisting results to the SQLite database."""

    def test_results_persisted_to_db(self, tmp_path) -> None:
        db = Database(tmp_path / "eval.db")
        db.initialize()
        evaluator = Evaluator(db=db)
        evaluator.evaluate([
            {"test_case_id": "tc1", "prompt": "hello", "expected_decision": "ALLOW"},
            {"test_case_id": "tc2", "prompt": "drop", "expected_decision": "BLOCK"},
        ])
        records = db.query_performance_records(benchmark_name="mock-evaluation")
        assert len(records) == 2
        ids = [r["metadata"]["test_case_id"] for r in records]
        assert "tc1" in ids and "tc2" in ids
        db.close()

    def test_no_db_no_recording(self) -> None:
        evaluator = Evaluator(db=None)
        evaluator.evaluate([{"test_case_id": "tc1", "prompt": "hello"}])
        assert evaluator.last_summary.total == 1

    def test_record_results_false(self, tmp_path) -> None:
        db = Database(tmp_path / "eval2.db")
        db.initialize()
        evaluator = Evaluator(db=db, record_results=False)
        evaluator.evaluate([{"test_case_id": "tc1", "prompt": "hello"}])
        assert len(db.query_performance_records(benchmark_name="mock-evaluation")) == 0
        db.close()


# ----------------------------------------------------------------------
# Evaluation result / summary
# ----------------------------------------------------------------------
class TestEvaluationResultModel:
    """Tests for EvaluationResult and EvaluationSummary."""

    def test_result_to_dict(self) -> None:
        result = EvaluationResult(
            test_case_id="tc1", expected_decision="ALLOW", actual_decision="ALLOW",
            succeeded=True, execution_time_ms=1.0, latency_ms=1.0,
        )
        data = result.to_dict()
        assert data["succeeded"] is True

    def test_summary_add_result(self) -> None:
        summary = EvaluationSummary()
        summary.add_result(EvaluationResult(test_case_id="tc1", expected_decision="ALLOW", actual_decision="ALLOW", succeeded=True))
        summary.add_result(EvaluationResult(test_case_id="tc2", expected_decision="BLOCK", actual_decision="ALLOW", succeeded=False))
        assert summary.total == 2
        assert summary.passed == 1
        assert summary.failed == 1
