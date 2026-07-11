from __future__ import annotations

import os
import json
import unittest
from contextlib import contextmanager
from typing import Iterator

from blueprint_core.llm import LLMProviderConfigError, build_llm_provider, resolve_llm_runtime_config
from blueprint_core.models import ProjectOverview
from blueprint_core.selectors import parse_llm_selector, split_llm_selector


LLM_ENV_KEYS = {
    "ALLOWED_LLM_MODELS",
    "ALLOWED_LLM_PROVIDERS",
    "ALLOWED_OPENAI_MODELS",
    "ALLOWED_RUNPOD_MODELS",
    "BASETEN_ALLOWED_MODELS",
    "BASETEN_API_KEY",
    "BASETEN_BASE_URL",
    "BASETEN_MODEL",
    "GEMINI_ALLOWED_MODELS",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GMI_ALLOWED_MODELS",
    "GMI_API_KEY",
    "GMI_BASE_URL",
    "GMI_CLOUD_API_KEY",
    "GMI_CLOUD_BASE_URL",
    "GMI_CLOUD_FALLBACK_MODEL",
    "GMI_CLOUD_MODEL",
    "GMI_CLOUD_RESPONSE_FORMAT",
    "GMI_CLOUD_TEMPERATURE",
    "GMI_CLOUD_TIMEOUT_SECONDS",
    "GMI_CLOUD_VALIDATE_MODELS",
    "GMI_FALLBACK_MODEL",
    "GMI_MODEL",
    "GMI_RESPONSE_FORMAT",
    "GMI_TEMPERATURE",
    "GMI_TIMEOUT_SECONDS",
    "GMI_VALIDATE_MODELS",
    "GMICLOUD_API_KEY",
    "GMICLOUD_BASE_URL",
    "GMICLOUD_FALLBACK_MODEL",
    "GMICLOUD_MODEL",
    "GMICLOUD_RESPONSE_FORMAT",
    "GMICLOUD_TEMPERATURE",
    "GMICLOUD_TIMEOUT_SECONDS",
    "GMICLOUD_VALIDATE_MODELS",
    "GOOGLE_API_KEY",
    "HF_ALLOWED_MODELS",
    "HF_API_TOKEN",
    "HF_BASE_URL",
    "HF_MODEL",
    "HF_TOKEN",
    "HUGGINGFACE_ALLOWED_MODELS",
    "HUGGINGFACE_API_KEY",
    "HUGGINGFACE_BASE_URL",
    "HUGGINGFACE_HUB_TOKEN",
    "HUGGINGFACE_MODEL",
    "LLM_ALLOWED_MODELS",
    "LLM_ALLOWED_PROVIDERS",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_FALLBACK_MODEL",
    "LLM_MAX_TOKENS",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "LLM_RESPONSE_FORMAT",
    "NIM_API_KEY",
    "NVIDIA_ALLOWED_MODELS",
    "NVIDIA_API_KEY",
    "NVIDIA_BASE_URL",
    "NVIDIA_MODEL",
    "OPENAI_ALLOWED_MODELS",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_FALLBACK_MODEL",
    "OPENAI_MAX_TOKENS",
    "OPENAI_MODEL",
    "OPENAI_RESPONSE_FORMAT",
    "OPENAI_VALIDATE_MODELS",
    "RUNPOD_ALLOWED_MODELS",
    "RUNPOD_API_KEY",
    "RUNPOD_BASE_URL",
    "RUNPOD_ENDPOINT_ID",
    "RUNPOD_ENDPOINT_URL",
    "RUNPOD_ENDPOINTS_BY_MODEL",
    "RUNPOD_FALLBACK_MODEL",
    "RUNPOD_MAX_TOKENS",
    "RUNPOD_MODEL",
    "RUNPOD_MODEL_ENDPOINTS",
    "RUNPOD_OPENAI_BASE_URL",
    "RUNPOD_OPENAI_FALLBACK_MODEL",
    "RUNPOD_OPENAI_MODEL",
    "RUNPOD_RESPONSE_FORMAT",
    "RUNPOD_SERVERLESS_MODEL",
    "RUNPOD_TEMPERATURE",
    "RUNPOD_VALIDATE_MODELS",
    "STRICT_GMI",
    "STRICT_GMI_CLOUD",
    "STRICT_GMICLOUD",
    "STRICT_LLM",
}


@contextmanager
def isolated_llm_env(**overrides: str) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in LLM_ENV_KEYS}
    try:
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        yield
    finally:
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)
            if old_values[key] is not None:
                os.environ[key] = old_values[key] or ""


class LLMRuntimeTests(unittest.TestCase):
    def test_parse_provider_model_selector(self) -> None:
        selector = parse_llm_selector("runpod/caid-technologies/parti-base")

        self.assertIsNotNone(selector)
        assert selector is not None
        self.assertEqual("runpod", selector.provider)
        self.assertEqual("caid-technologies/parti-base", selector.model)
        self.assertEqual("runpod/caid-technologies/parti-base", selector.key)
        hf_selector = parse_llm_selector("huggingface/Qwen/Qwen2.5-Coder-3B-Instruct:nscale")
        self.assertIsNotNone(hf_selector)
        assert hf_selector is not None
        self.assertEqual("huggingface", hf_selector.provider)
        self.assertEqual("Qwen/Qwen2.5-Coder-3B-Instruct:nscale", hf_selector.model)
        self.assertEqual(("openai", "gpt-5.5"), split_llm_selector("openai/gpt-5.5"))
        self.assertEqual((None, None), split_llm_selector(None))

    def test_invalid_selector_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_llm_selector("gpt-5.5")

    def test_runtime_allows_configured_openai_model_override(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="simulation",
            LLM_ALLOWED_PROVIDERS="simulation,openai,runpod",
            OPENAI_ALLOWED_MODELS="gpt-5.5",
        ):
            runtime = resolve_llm_runtime_config("openai", "gpt-5.5")

        self.assertEqual("openai", runtime.provider)
        self.assertEqual("gpt-5.5", runtime.model)
        self.assertTrue(runtime.model_overridden)
        self.assertEqual(["gpt-5.5"], runtime.allowed_models)

    def test_runtime_rejects_disallowed_model_override(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="simulation",
            LLM_ALLOWED_PROVIDERS="simulation,openai",
            OPENAI_ALLOWED_MODELS="gpt-5.5",
        ):
            with self.assertRaises(LLMProviderConfigError):
                resolve_llm_runtime_config("openai", "gpt-4o-mini")

    def test_runpod_serverless_model_endpoint_map_extends_allowed_models(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="runpod-serverless",
            LLM_ALLOWED_PROVIDERS="runpod-serverless,simulation",
            RUNPOD_API_KEY="rpa_test",
            RUNPOD_MODEL_ENDPOINTS='{"caid-technologies/parti-base": "endpoint-test"}',
        ):
            runtime = resolve_llm_runtime_config("runpod-serverless", "caid-technologies/parti-base")

        self.assertEqual("runpod-serverless", runtime.provider)
        self.assertEqual("caid-technologies/parti-base", runtime.model)
        self.assertIn("caid-technologies/parti-base", runtime.allowed_models or [])

    def test_runpod_queue_base_url_autodetects_serverless_provider(self) -> None:
        with isolated_llm_env(
            RUNPOD_API_KEY="rpa_test",
            RUNPOD_BASE_URL="https://api.runpod.ai/v2/endpoint-test",
            RUNPOD_OPENAI_MODEL="caid-technologies/parti-base",
        ):
            runtime = resolve_llm_runtime_config()
            provider = build_llm_provider(runtime_config=runtime)

        self.assertEqual("runpod-serverless", runtime.provider)
        self.assertEqual("caid-technologies/parti-base", runtime.model)
        self.assertEqual("https://api.runpod.ai/v2/endpoint-test", provider.endpoint_base_url)
        self.assertTrue(provider.is_configured)

    def test_runpod_queue_url_is_not_reported_as_configured_openai_runpod(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="runpod-serverless",
            LLM_ALLOWED_PROVIDERS="openai,runpod,runpod-serverless,simulation",
            RUNPOD_API_KEY="rpa_test",
            RUNPOD_OPENAI_BASE_URL="https://api.runpod.ai/v2/endpoint-test",
            RUNPOD_ENDPOINT_ID="endpoint-test",
            RUNPOD_MODEL="caid-technologies/parti-base",
        ):
            runtime = resolve_llm_runtime_config()

        self.assertEqual("runpod-serverless", runtime.provider)
        self.assertIn("runpod-serverless", runtime.configured_providers or [])
        self.assertNotIn("runpod", runtime.configured_providers or [])
        self.assertIn("runpod", runtime.allowed_providers or [])

    def test_explicit_runpod_rejects_queue_endpoint_base_url(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="runpod",
            LLM_ALLOWED_PROVIDERS="runpod,simulation",
            RUNPOD_API_KEY="rpa_test",
            RUNPOD_BASE_URL="https://api.runpod.ai/v2/endpoint-test",
            RUNPOD_OPENAI_MODEL="caid-technologies/parti-base",
        ):
            runtime = resolve_llm_runtime_config()
            provider = build_llm_provider(runtime_config=runtime)
            validation = provider.validate_configured_model(raise_on_strict=False)

            with self.assertRaises(LLMProviderConfigError):
                provider.validate_configured_model()

        self.assertEqual("runpod", runtime.provider)
        self.assertEqual("runpod", provider.provider_name)
        self.assertFalse(validation.live_generation_enabled)
        self.assertIn("LLM_PROVIDER=runpod-serverless", validation.validation_error or "")

    def test_huggingface_runtime_uses_qwen_default(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="huggingface",
            LLM_ALLOWED_PROVIDERS="huggingface,simulation",
            HF_TOKEN="hf_test",
        ):
            runtime = resolve_llm_runtime_config()

        self.assertEqual("huggingface", runtime.provider)
        self.assertEqual("Qwen/Qwen2.5-Coder-3B-Instruct:nscale", runtime.model)
        self.assertIn("Qwen/Qwen2.5-Coder-3B-Instruct:nscale", runtime.allowed_models or [])

    def test_huggingface_provider_uses_router_defaults(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="huggingface",
            LLM_ALLOWED_PROVIDERS="huggingface,simulation",
            HF_TOKEN="hf_test",
            HUGGINGFACE_MODEL="Qwen/Qwen2.5-Coder-3B-Instruct:nscale",
            LLM_BASE_URL="https://api.runpod.ai/v2/not-huggingface/openai/v1",
            LLM_API_KEY="sk_not_huggingface",
        ):
            runtime = resolve_llm_runtime_config()
            provider = build_llm_provider(runtime_config=runtime)

        self.assertEqual("huggingface", provider.provider_name)
        self.assertEqual("Qwen/Qwen2.5-Coder-3B-Instruct:nscale", provider.requested_model)
        self.assertEqual("https://router.huggingface.co/v1", provider.base_url)
        self.assertTrue(provider.is_configured)

    def test_nvidia_runtime_allows_qwen_coder_32b_instruct(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="nvidia",
            LLM_ALLOWED_PROVIDERS="nvidia,simulation",
            NVIDIA_API_KEY="nvapi_test",
            NVIDIA_ALLOWED_MODELS="qwen/qwen2.5-coder-32b-instruct,meta/llama-3.1-8b-instruct",
        ):
            runtime = resolve_llm_runtime_config("nvidia", "qwen/qwen2.5-coder-32b-instruct")
            provider = build_llm_provider(runtime_config=runtime)

        self.assertEqual("nvidia", runtime.provider)
        self.assertEqual("qwen/qwen2.5-coder-32b-instruct", runtime.model)
        self.assertIn("qwen/qwen2.5-coder-32b-instruct", runtime.allowed_models or [])
        self.assertEqual("qwen/qwen2.5-coder-32b-instruct", provider.requested_model)
        self.assertEqual("https://integrate.api.nvidia.com/v1", provider.base_url)
        self.assertTrue(provider.is_configured)

    def test_gmi_runtime_uses_fable_default_and_aliases(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="gemicloud",
            LLM_ALLOWED_PROVIDERS="gmi,simulation",
            LLM_BASE_URL="https://api.runpod.ai/v2/not-gmi/openai/v1",
            LLM_TEMPERATURE="0.9",
            GMI_API_KEY="gmi_test",
            GMI_ALLOWED_MODELS="fable",
        ):
            runtime = resolve_llm_runtime_config("gmi", "gmi/fable")
            provider = build_llm_provider(runtime_config=runtime)

        self.assertEqual("gmi", runtime.provider)
        self.assertEqual("anthropic/claude-fable-5", runtime.model)
        self.assertEqual(["anthropic/claude-fable-5"], runtime.allowed_models)
        self.assertEqual("gmi", provider.provider_name)
        self.assertEqual("anthropic/claude-fable-5", provider.requested_model)
        self.assertEqual("https://api.gmi-serving.com/v1", provider.base_url)
        self.assertIsNone(provider.temperature)
        self.assertTrue(provider.is_configured)

    def test_openai_provider_uses_max_completion_tokens(self) -> None:
        with isolated_llm_env(
            LLM_PROVIDER="openai",
            LLM_ALLOWED_PROVIDERS="openai,simulation",
            OPENAI_API_KEY="sk_test",
            OPENAI_MODEL="gpt-5.5",
            OPENAI_MAX_TOKENS="123",
            OPENAI_RESPONSE_FORMAT="json_object",
            OPENAI_VALIDATE_MODELS="false",
        ):
            runtime = resolve_llm_runtime_config("openai", "gpt-5.5")
            provider = build_llm_provider(runtime_config=runtime)

        payloads = []

        def fake_request(path, method="GET", payload=None):
            payloads.append(payload or {})
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "Test Project",
                                    "description": "A test project.",
                                    "difficulty": "Beginner",
                                    "estimated_cost": 1.0,
                                    "category": "IoT",
                                }
                            )
                        }
                    }
                ]
            }

        provider._request_json = fake_request
        provider.generate_structured("Return a project overview.", ProjectOverview)

        self.assertEqual(123, payloads[0]["max_completion_tokens"])
        self.assertNotIn("max_tokens", payloads[0])


if __name__ == "__main__":
    unittest.main()
