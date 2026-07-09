from __future__ import annotations

import importlib.util
import csv
import json
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
OFFLINE_BENCHMARK_SCRIPT = ROOT_DIR / "benchmarks" / "benchmark_offline.py"
MODEL_BENCHMARK_SCRIPT = ROOT_DIR / "benchmarks" / "benchmark_models.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class BenchmarkScriptTests(unittest.TestCase):
    def test_offline_sample_circuit_validates_without_critical_issues(self) -> None:
        module = load_module("blueprint_benchmark_offline", OFFLINE_BENCHMARK_SCRIPT)
        from blueprint_core.validation import validate_circuit

        components, nets = module.make_sample_circuit()
        issues = validate_circuit(components, nets)

        self.assertEqual([], [issue for issue in issues if issue.severity.upper() == "CRITICAL"])

    def test_offline_measure_operation_records_timing(self) -> None:
        module = load_module("blueprint_benchmark_offline", OFFLINE_BENCHMARK_SCRIPT)

        result = module.measure_operation("unit.noop", iterations=3, operation=lambda: None, warmup_iterations=0)

        self.assertEqual("unit.noop", result.name)
        self.assertEqual(3, result.iterations)
        self.assertGreaterEqual(result.total_seconds, 0.0)
        self.assertGreaterEqual(result.iterations_per_second, 0.0)

    def test_model_benchmark_summary_groups_by_candidate(self) -> None:
        module = load_module("blueprint_benchmark_models", MODEL_BENCHMARK_SCRIPT)
        candidate = module.LLMSelector("openai", "gpt-5.5")
        rounds = [
            {
                "round": 1,
                "measured": True,
                "results": [
                    {
                        "llm": "openai/gpt-5.5",
                        "provider": "openai",
                        "model": "gpt-5.5",
                        "status": "pass",
                        "duration_seconds": 0.25,
                    }
                ],
            }
        ]

        summary = module.summarize_candidate_runs([candidate], rounds)

        self.assertTrue(summary["ok"])
        self.assertEqual(1, summary["passed"])
        self.assertEqual(0, summary["failed"])
        self.assertEqual(0.25, summary["candidates"][0]["duration_seconds"]["mean"])

    def test_model_benchmark_job_sink_writes_jsonl_and_csv(self) -> None:
        module = load_module("blueprint_benchmark_models", MODEL_BENCHMARK_SCRIPT)
        result = {
            "llm": "openai/gpt-5.5",
            "provider": "openai",
            "model": "gpt-5.5",
            "actual_model": "gpt-5.5",
            "status": "pass",
            "duration_seconds": 0.125,
            "benchmark_duration_seconds": 0.125456,
            "configured": True,
            "validation": {"live_generation_enabled": True},
            "response": {"summary": "ok"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with module.BenchmarkJobSink(
                output_dir=temp_dir,
                run_id="unit-test",
                formats={"jsonl", "csv"},
            ) as sink:
                sink.record(result, round_index=1, measured=True)
                metadata = sink.as_report_metadata()

            jsonl_path = pathlib.Path(metadata["jsonl_path"])
            csv_path = pathlib.Path(metadata["csv_path"])
            jsonl_records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
            with csv_path.open(encoding="utf-8", newline="") as handle:
                csv_records = list(csv.DictReader(handle))

            self.assertEqual(1, metadata["count"])
            self.assertEqual("openai/gpt-5.5", jsonl_records[0]["llm"])
            self.assertEqual(0.125456, jsonl_records[0]["duration_seconds"])
            self.assertEqual("openai/gpt-5.5", csv_records[0]["llm"])
            self.assertEqual("pass", csv_records[0]["status"])


if __name__ == "__main__":
    unittest.main()
