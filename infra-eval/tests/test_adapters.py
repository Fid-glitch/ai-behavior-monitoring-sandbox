"""
Unit tests for the benchmark adapter/loader architecture.

Tests cover JSON, JSONL, and CSV loading; malformed input; empty datasets;
benchmark metadata; adapter registration; and the local mock benchmark.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evaluation import (
    BenchmarkDataset,
    BenchmarkMeta,
    CsvBenchmarkAdapter,
    JsonBenchmarkAdapter,
    JsonlBenchmarkAdapter,
    MalformedBenchmarkError,
    MockBenchmarkAdapter,
    UnknownBenchmarkError,
    get_adapter_class,
    load_benchmark,
    register_adapter,
    supported_benchmarks,
)
from evaluation.adapters import BaseBenchmarkAdapter


def _sample_records() -> list:
    """Return a list of sample test case records."""
    return [
        {
            "test_case_id": "tc-1",
            "prompt": "What is 2+2?",
            "expected_decision": "ALLOW",
            "category": "math",
        },
        {
            "test_case_id": "tc-2",
            "prompt": "Inject malicious code",
            "expected_decision": "BLOCK",
            "category": "security",
        },
    ]


def _write_json(tmp_path, name: str, data) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_jsonl(tmp_path, name: str, records) -> Path:
    path = tmp_path / name
    text = "\n".join(json.dumps(r) for r in records) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _write_csv(tmp_path, name: str, records) -> Path:
    path = tmp_path / name
    if not records:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(records[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path


# ----------------------------------------------------------------------
# JSON adapter
# ----------------------------------------------------------------------
class TestJsonAdapter:
    """Tests for the JSON benchmark adapter."""

    def test_load_json_file(self, tmp_path) -> None:
        path = _write_json(tmp_path, "bench.json", _sample_records())
        dataset = load_benchmark(path)
        assert isinstance(dataset, BenchmarkDataset)
        assert dataset.size == 2
        assert dataset.test_cases[0].test_case_id == "tc-1"
        assert dataset.meta.format == "json"
        assert dataset.meta.source == "local"

    def test_load_json_with_test_cases_key(self, tmp_path) -> None:
        data = {"test_cases": _sample_records()}
        path = _write_json(tmp_path, "bench2.json", data)
        dataset = load_benchmark(path)
        assert dataset.size == 2

    def test_json_malformed_raises(self, tmp_path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(MalformedBenchmarkError):
            load_benchmark(path)

    def test_json_empty_list(self, tmp_path) -> None:
        path = _write_json(tmp_path, "empty.json", [])
        dataset = load_benchmark(path)
        assert dataset.size == 0
        assert dataset.test_cases == []

    def test_json_missing_file(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_benchmark(tmp_path / "missing.json")

    def test_json_bad_structure(self, tmp_path) -> None:
        path = _write_json(tmp_path, "bad2.json", {"foo": 42})
        with pytest.raises(MalformedBenchmarkError):
            load_benchmark(path)


# ----------------------------------------------------------------------
# JSONL adapter
# ----------------------------------------------------------------------
class TestJsonlAdapter:
    """Tests for the JSONL benchmark adapter."""

    def test_load_jsonl_file(self, tmp_path) -> None:
        path = _write_jsonl(tmp_path, "bench.jsonl", _sample_records())
        dataset = load_benchmark(path)
        assert dataset.size == 2
        assert dataset.test_cases[1].test_case_id == "tc-2"
        assert dataset.meta.format == "jsonl"

    def test_jsonl_blank_lines_skipped(self, tmp_path) -> None:
        path = tmp_path / "blanks.jsonl"
        text = (
            json.dumps(_sample_records()[0])
            + "\n\n\n"
            + json.dumps(_sample_records()[1])
            + "\n"
        )
        path.write_text(text, encoding="utf-8")
        dataset = load_benchmark(path)
        assert dataset.size == 2

    def test_jsonl_invalid_json_raises(self, tmp_path) -> None:
        path = tmp_path / "bad.jsonl"
        path.write_text('{"test_case_id": "tc1", "prompt": "hi"}\nnot json\n', encoding="utf-8")
        with pytest.raises(MalformedBenchmarkError):
            load_benchmark(path)

    def test_jsonl_empty_file(self, tmp_path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        dataset = load_benchmark(path)
        assert dataset.size == 0

    def test_jsonl_missing_file(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_benchmark(tmp_path / "missing.jsonl")


# ----------------------------------------------------------------------
# CSV adapter
# ----------------------------------------------------------------------
class TestCsvAdapter:
    """Tests for the CSV benchmark adapter."""

    def test_load_csv_file(self, tmp_path) -> None:
        path = _write_csv(tmp_path, "bench.csv", _sample_records())
        dataset = load_benchmark(path, benchmark="csv")
        assert dataset.size == 2
        assert dataset.meta.format == "csv"
        assert dataset.test_cases[0].expected_decision == "ALLOW"

    def test_csv_load_records(self) -> None:
        dataset = load_benchmark(records=_sample_records(), format="csv")
        assert dataset.size == 2

    def test_csv_missing_file(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_benchmark(tmp_path / "missing.csv", format="csv")

    def test_csv_empty(self, tmp_path) -> None:
        path = _write_csv(tmp_path, "empty.csv", [])
        # Empty file has no header row -> should raise or return empty
        dataset = load_benchmark(path, format="csv")
        assert dataset.size == 0


# ----------------------------------------------------------------------
# Mock benchmark
# ----------------------------------------------------------------------
class TestMockBenchmark:
    """Tests for the local mock benchmark adapter."""

    def test_mock_dataset(self) -> None:
        dataset = load_benchmark(benchmark="mock")
        assert isinstance(dataset, BenchmarkDataset)
        assert dataset.size == 4
        assert dataset.meta.name == "mock"
        assert dataset.meta.format == "mock"

    def test_mock_has_attacks_and_benign(self) -> None:
        dataset = load_benchmark(benchmark="mock")
        expected = {tc.expected_decision for tc in dataset.test_cases}
        assert "BLOCK" in expected
        assert "WARNING" in expected
        assert "ALLOW" in expected

    def test_mock_new_adapter_records(self) -> None:
        adapter = MockBenchmarkAdapter()
        dataset = adapter.load_records(_sample_records())
        assert dataset.size == 2


# ----------------------------------------------------------------------
# Registry & metadata
# ----------------------------------------------------------------------
class TestRegistry:
    """Tests for the adapter registry."""

    def test_supported_benchmarks(self) -> None:
        supported = supported_benchmarks()
        assert "json" in supported
        assert "jsonl" in supported
        assert "csv" in supported
        assert "mock" in supported

    def test_get_adapter_class(self) -> None:
        cls = get_adapter_class("json")
        assert cls is not None
        assert issubclass(cls, BaseBenchmarkAdapter)

    def test_unknown_benchmark_raises(self) -> None:
        with pytest.raises(UnknownBenchmarkError):
            get_adapter_class("not-a-benchmark")

    def test_unknown_benchmark_load_raises(self) -> None:
        with pytest.raises(UnknownBenchmarkError):
            load_benchmark(benchmark="nope")

    def test_register_custom_adapter(self) -> None:
        class MyAdapter(BaseBenchmarkAdapter):
            name = "custom"
            supported_formats = ("custom",)

            def load_file(self, path) -> BenchmarkDataset:
                return self._build_dataset([], format="custom")

            def load_records(self, records) -> BenchmarkDataset:
                return self._build_dataset(records, format="custom")

        register_adapter(MyAdapter)
        assert "custom" in supported_benchmarks()
        cls = get_adapter_class("custom")
        assert cls is MyAdapter

    def test_no_path_no_records_raises(self) -> None:
        with pytest.raises(Exception):
            load_benchmark()


# ----------------------------------------------------------------------
# Metadata
# ----------------------------------------------------------------------
class TestMetadata:
    """Tests for benchmark metadata."""

    def test_meta_to_dict(self) -> None:
        meta = BenchmarkMeta(name="json", version="1.0", format="json")
        data = meta.to_dict()
        assert data["name"] == "json"
        assert data["format"] == "json"

    def test_dataset_to_dict(self) -> None:
        dataset = load_benchmark(benchmark="mock")
        data = dataset.to_dict()
        assert data["size"] == 4
        assert data["meta"]["name"] == "mock"
        assert len(data["test_cases"]) == 4

    def test_benchmark_meta_has_source_local(self) -> None:
        dataset = load_benchmark(benchmark="mock")
        assert dataset.meta.source == "local"