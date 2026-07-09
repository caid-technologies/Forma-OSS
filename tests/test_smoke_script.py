from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT_DIR / "scripts" / "verify-llm-providers.py"


def load_smoke_script_module():
    spec = importlib.util.spec_from_file_location("verify_llm_providers", SMOKE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load verify-llm-providers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeScriptTests(unittest.TestCase):
    def test_parse_llm_selector_uses_core_selector_shape(self) -> None:
        module = load_smoke_script_module()

        candidate = module.parse_llm_selector("openai/gpt-5.5")

        self.assertEqual("openai", candidate.provider)
        self.assertEqual("gpt-5.5", candidate.model)
        self.assertEqual("openai/gpt-5.5", candidate.key)

    def test_dedupe_candidates_keeps_first_occurrence(self) -> None:
        module = load_smoke_script_module()
        first = module.LlmCandidate("openai", "gpt-5.5")
        duplicate = module.LlmCandidate("openai", "gpt-5.5")
        second = module.LlmCandidate("runpod", "caid-technologies/parti-base")

        self.assertEqual([first, second], module.dedupe_candidates([first, duplicate, second]))


if __name__ == "__main__":
    unittest.main()
