from __future__ import annotations

import asyncio
import io
import importlib.util
import pathlib
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout

from blueprint_core.providers import ProviderEvent, ProviderRequest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE_SCRIPT = ROOT_DIR / "examples" / "async_glm_openai_prompt.py"


def load_example_module():
    spec = importlib.util.spec_from_file_location("async_glm_openai_prompt", EXAMPLE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load async_glm_openai_prompt.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakePrepared:
    def __init__(self, request: ProviderRequest) -> None:
        self.request = request


class FakeRegistry:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.active_count = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def prepare(self, request: ProviderRequest) -> FakePrepared:
        return FakePrepared(request)

    def stream_text(self, prepared: FakePrepared):
        with self.lock:
            self.active_count += 1
            self.max_active = max(self.max_active, self.active_count)
            if self.active_count == 2:
                self.started.set()
        self.started.wait(timeout=1.0)
        time.sleep(0.05)
        with self.lock:
            self.active_count -= 1
        yield ProviderEvent(
            sequence=1,
            content=f"{prepared.request.provider}:{prepared.request.model}",
            done=False,
            event_type="unit.delta",
        )
        yield ProviderEvent(
            sequence=2,
            content="",
            done=True,
            event_type="unit.completed",
        )


class AsyncGlmOpenAIExampleTests(unittest.TestCase):
    def test_default_candidates_are_glm_and_openai(self) -> None:
        module = load_example_module()

        candidates = module.default_candidates()

        self.assertEqual("baseten", candidates[0].provider)
        self.assertEqual("zai-org/GLM-5.2", candidates[0].model)
        self.assertEqual("openai", candidates[1].provider)
        self.assertEqual("gpt-5.5", candidates[1].model)

    def test_models_run_concurrently_and_keep_result_order(self) -> None:
        module = load_example_module()
        registry = FakeRegistry()
        candidates = module.default_candidates()

        results = asyncio.run(
            module.run_models_async(
                candidates=candidates,
                registry=registry,
                prompt="unit prompt",
                instructions="unit instructions",
                emit_output=False,
            )
        )

        self.assertEqual([candidate.llm_id for candidate in candidates], [result.llm_id for result in results])
        self.assertEqual(2, registry.max_active)
        self.assertTrue(all(result.passed for result in results))

    def test_stdout_lines_include_current_model(self) -> None:
        module = load_example_module()
        result = module.ModelRunResult(
            candidate_index=0,
            provider="baseten",
            model="zai-org/GLM-5.2",
            status="pass",
            text="first line\nsecond line",
            event_count=2,
            duration_seconds=1.2,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            module.print_result(result)

        output = buffer.getvalue()
        self.assertIn("[async-glm-openai] PASS baseten/zai-org/GLM-5.2", output)
        self.assertIn("[async-glm-openai:stdout model=baseten/zai-org/GLM-5.2] first line", output)
        self.assertIn("[async-glm-openai:stdout model=baseten/zai-org/GLM-5.2] second line", output)


if __name__ == "__main__":
    unittest.main()
