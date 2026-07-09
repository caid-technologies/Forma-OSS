from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from blueprint_core.image_providers import OpenAIImageProvider, build_image_provider


class ImageProviderRoutingTests(unittest.TestCase):
    def test_openai_image_provider_does_not_inherit_llm_base_url(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-openai",
                "LLM_API_KEY": "rpa-runpod",
                "LLM_BASE_URL": "https://api.runpod.ai/v2/example/openai/v1",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, OpenAIImageProvider)
        self.assertEqual("openai", provider.provider_name)
        self.assertEqual("https://api.openai.com/v1", provider.base_url)
        self.assertEqual("sk-openai", provider.api_key)
        self.assertTrue(provider.is_configured)

    def test_explicit_openai_image_provider_requires_openai_key_family(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "openai",
                "LLM_API_KEY": "rpa-runpod",
                "LLM_BASE_URL": "https://api.runpod.ai/v2/example/openai/v1",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, OpenAIImageProvider)
        self.assertEqual("openai", provider.provider_name)
        self.assertEqual("https://api.openai.com/v1", provider.base_url)
        self.assertIsNone(provider.api_key)
        self.assertFalse(provider.is_configured)

    def test_openai_compatible_image_provider_can_use_llm_routing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "openai-compatible",
                "LLM_API_KEY": "local-compatible-key",
                "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, OpenAIImageProvider)
        self.assertEqual("openai-compatible", provider.provider_name)
        self.assertEqual("http://127.0.0.1:11434/v1", provider.base_url)
        self.assertEqual("local-compatible-key", provider.api_key)
        self.assertTrue(provider.is_configured)


if __name__ == "__main__":
    unittest.main()
