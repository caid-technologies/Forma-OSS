from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_SCRIPT = ROOT_DIR / "sample.py"


def load_sample_module():
    spec = importlib.util.spec_from_file_location("blueprint_sample", SAMPLE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SampleScriptTests(unittest.TestCase):
    def test_parse_llm_selector(self) -> None:
        module = load_sample_module()

        candidate = module.parse_llm_selector("runpod/caid-technologies/parti-base")

        self.assertEqual("runpod", candidate.provider)
        self.assertEqual("caid-technologies/parti-base", candidate.model)
        self.assertEqual("runpod/caid-technologies/parti-base", candidate.key)

    def test_dedupe_candidates_keeps_order(self) -> None:
        module = load_sample_module()
        first = module.LLMSelector("openai", "gpt-5.5")
        duplicate = module.LLMSelector("openai", "gpt-5.5")
        second = module.LLMSelector("nvidia", "meta/llama-3.1-8b-instruct")

        self.assertEqual([first, second], module.dedupe_candidates([first, duplicate, second]))

    def test_save_report_writes_latest(self) -> None:
        module = load_sample_module()
        report = {
            "completed_at": "2026-07-07T00:00:00Z",
            "summary": {"ok": True},
            "results": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path, latest_path = module.save_report(report, output_dir=temp_dir, output_file=None)

            self.assertTrue(report_path.exists())
            self.assertTrue(latest_path.exists())
            self.assertEqual(report_path.read_text(encoding="utf-8"), latest_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
