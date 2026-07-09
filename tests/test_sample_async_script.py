from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import threading
import time
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
ASYNC_SAMPLE_SCRIPT = ROOT_DIR / "sample_async.py"


def load_async_sample_module():
    spec = importlib.util.spec_from_file_location("blueprint_sample_async", ASYNC_SAMPLE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load sample_async.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AsyncSampleScriptTests(unittest.TestCase):
    def test_async_runner_returns_results_in_candidate_order(self) -> None:
        module = load_async_sample_module()
        candidates = [
            module.LLMSelector("openai", "gpt-5.5"),
            module.LLMSelector("runpod", "caid-technologies/parti-base"),
        ]

        def runner(candidate):
            return {"llm": candidate.key, "status": "pass"}

        results = asyncio.run(
            module.run_candidates_async(
                candidates,
                prompt="same prompt",
                timeout_seconds=None,
                config_only=False,
                concurrency=2,
                sync_runner=runner,
            )
        )

        self.assertEqual([candidate.key for candidate in candidates], [result["llm"] for result in results])
        self.assertEqual([0, 1], [result["candidate_index"] for result in results])

    def test_async_runner_runs_selected_models_concurrently(self) -> None:
        module = load_async_sample_module()
        candidates = [
            module.LLMSelector("provider", "model-a"),
            module.LLMSelector("provider", "model-b"),
        ]
        started = threading.Event()
        active_count = 0
        max_active = 0
        lock = threading.Lock()

        def runner(candidate):
            nonlocal active_count, max_active
            with lock:
                active_count += 1
                max_active = max(max_active, active_count)
                if active_count == 2:
                    started.set()
            started.wait(timeout=1.0)
            time.sleep(0.05)
            with lock:
                active_count -= 1
            return {"llm": candidate.key, "status": "pass"}

        results = asyncio.run(
            module.run_candidates_async(
                candidates,
                prompt="same prompt",
                timeout_seconds=None,
                config_only=False,
                concurrency=2,
                sync_runner=runner,
            )
        )

        self.assertEqual(2, len(results))
        self.assertEqual(2, max_active)


if __name__ == "__main__":
    unittest.main()
