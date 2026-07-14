"""Regression tests for parti-base pipeline routing.

parti-base is fine-tuned to emit its full-record training schema regardless of
the schema in the prompt. If a parti-base selector is not routed to the
dedicated adapter, the generic pipeline's first structured call fails with
pydantic missing-field errors for ProjectOverview (title, description,
difficulty, category). The original gate only matched the exact pair
("runpod", "caid-technologies/parti-base"), so runpod-serverless runs and
unnamespaced/tagged model ids fell into the generic pipeline and crashed.
"""
from __future__ import annotations

import unittest

from blueprint_core.agents.orchestrator import (
    HardwarePipelineOrchestrator,
    PARTI_BASE_MODEL_ID,
    _is_parti_base_selector,
)
from blueprint_core.llm import LLMProviderValidation


def _validation(provider: str, model: str) -> LLMProviderValidation:
    return LLMProviderValidation(
        provider=provider,
        requested_model=model,
        actual_model=model,
        requested_model_available=True,
        strict_mode=True,
        fallback_active=False,
    )


class PartiBaseSelectorTests(unittest.TestCase):
    def test_matches_original_runpod_selector(self):
        self.assertTrue(_is_parti_base_selector("runpod", PARTI_BASE_MODEL_ID))

    def test_matches_runpod_serverless_provider(self):
        # The bug: runpod-serverless + parti-base fell into the generic
        # pipeline and died on the ProjectOverview intent-parser call.
        self.assertTrue(_is_parti_base_selector("runpod-serverless", PARTI_BASE_MODEL_ID))

    def test_matches_unnamespaced_model_id(self):
        self.assertTrue(_is_parti_base_selector("runpod", "parti-base"))
        self.assertTrue(_is_parti_base_selector("runpod-serverless", "parti-base"))

    def test_matches_tagged_and_cased_variants(self):
        self.assertTrue(_is_parti_base_selector("runpod", "caid-technologies/parti-base:latest"))
        self.assertTrue(_is_parti_base_selector("RunPod", "Caid-Technologies/Parti-Base"))
        self.assertTrue(_is_parti_base_selector("runpod-serverless", " parti-base "))

    def test_rejects_non_runpod_providers(self):
        self.assertFalse(_is_parti_base_selector("openai", PARTI_BASE_MODEL_ID))
        self.assertFalse(_is_parti_base_selector("openai-compatible", PARTI_BASE_MODEL_ID))
        self.assertFalse(_is_parti_base_selector("gemini", "parti-base"))

    def test_rejects_other_models(self):
        self.assertFalse(_is_parti_base_selector("runpod", "gpt-5.5"))
        self.assertFalse(_is_parti_base_selector("runpod-serverless", "runpod-default"))
        # Different basename means a different (possibly incompatible) adapter.
        self.assertFalse(_is_parti_base_selector("runpod", "caid-technologies/parti-base-v2"))

    def test_rejects_empty_values(self):
        self.assertFalse(_is_parti_base_selector("", PARTI_BASE_MODEL_ID))
        self.assertFalse(_is_parti_base_selector("runpod", ""))
        self.assertFalse(_is_parti_base_selector(None, None))


class _StubPartiProvider:
    provider_name = "runpod-serverless"
    model_name = PARTI_BASE_MODEL_ID
    is_configured = True

    def __init__(self, provider: str, model: str):
        self.provider_name = provider
        self.model_name = model
        self._validation = _validation(provider, model)

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        return self._validation

    def generate_structured(self, *args, **kwargs):
        raise AssertionError(
            "generate_structured must not be called: parti-base runs must be "
            "routed to the dedicated adapter, not the generic structured pipeline."
        )


class PartiBaseOrchestratorRoutingTests(unittest.TestCase):
    def _routed_orchestrator(self, provider: str, model: str):
        orchestrator = HardwarePipelineOrchestrator.__new__(HardwarePipelineOrchestrator)
        orchestrator.use_simulation = False
        orchestrator.llm_provider = _StubPartiProvider(provider, model)
        orchestrator.model_name = model
        orchestrator._active_generation_metadata = {}
        return orchestrator

    def _assert_routes_to_parti_adapter(self, provider: str, model: str):
        orchestrator = self._routed_orchestrator(provider, model)
        sentinel = object()
        calls = []

        def fake_adapter(user_prompt, *, model_validation, image_bytes=None, image_mime_type=None):
            calls.append((user_prompt, model_validation.provider, model_validation.actual_model))
            return sentinel

        orchestrator._generate_parti_base_project = fake_adapter
        result = orchestrator.generate_project("a small temperature logger")
        self.assertIs(result, sentinel)
        self.assertEqual(calls, [("a small temperature logger", provider, model)])

    def test_runpod_serverless_routes_to_parti_adapter(self):
        self._assert_routes_to_parti_adapter("runpod-serverless", PARTI_BASE_MODEL_ID)

    def test_runpod_openai_compatible_routes_to_parti_adapter(self):
        self._assert_routes_to_parti_adapter("runpod", PARTI_BASE_MODEL_ID)

    def test_unnamespaced_model_routes_to_parti_adapter(self):
        self._assert_routes_to_parti_adapter("runpod-serverless", "parti-base")


if __name__ == "__main__":
    unittest.main()
