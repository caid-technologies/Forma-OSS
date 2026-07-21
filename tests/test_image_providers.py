from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from blueprint_core.image_providers import GMIImageProvider, HuggingFaceImageProvider, OpenAIImageProvider, TogetherImageProvider, build_image_provider


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

    def test_gmi_image_provider_routes_from_image_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "gmi",
                "GMI_API_KEY": "gmi-secret",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, GMIImageProvider)
        self.assertEqual("gmi", provider.provider_name)
        self.assertEqual("https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests/v1", provider.base_url)
        self.assertEqual("gmi-secret", provider.api_key)
        self.assertEqual("gpt-image-2", provider.model_name)
        self.assertEqual("1024x1024", provider.size)
        self.assertEqual("medium", provider.quality)
        self.assertEqual("png", provider.output_format)
        self.assertTrue(provider.is_configured)

    def test_gmi_image_provider_auto_routes_from_api_key_only(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GMI_API_KEY": "gmi-secret",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, GMIImageProvider)
        self.assertEqual("gmi", provider.provider_name)
        self.assertEqual("gpt-image-2", provider.model_name)
        self.assertTrue(provider.is_configured)

    def test_together_image_provider_routes_from_image_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "together-ai",
                "TOGETHER_API_KEY": "together-secret",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, TogetherImageProvider)
        self.assertEqual("together", provider.provider_name)
        self.assertEqual("https://api.together.ai/v1", provider.base_url)
        self.assertEqual("together-secret", provider.api_key)
        self.assertEqual("openai/gpt-image-2", provider.model_name)
        self.assertEqual("1024x1024", provider.size)
        self.assertEqual(0, provider.num_inference_steps)
        self.assertEqual("Forma-OSS/1.0", provider._headers()["User-Agent"])
        self.assertEqual("application/json", provider._headers()["Accept"])
        self.assertTrue(provider.is_configured)

    def test_together_image_provider_auto_routes_from_api_key_only(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TOGETHER_API_KEY": "together-secret",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, TogetherImageProvider)
        self.assertEqual("together", provider.provider_name)
        self.assertEqual("openai/gpt-image-2", provider.model_name)
        self.assertTrue(provider.is_configured)

    def test_together_default_gpt_image_generation_uses_minimal_payload(self) -> None:
        calls = []
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "together",
                "TOGETHER_API_KEY": "together-secret",
                "TOGETHER_IMAGE_SIZE": "768x512",
                "TOGETHER_IMAGE_STEPS": "8",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, TogetherImageProvider)

            def fake_request(path: str, method: str = "GET", payload=None):
                calls.append({"path": path, "method": method, "payload": payload})
                return {"data": [{"b64_json": "ZmFrZS1pbWFnZQ=="}]}

            with patch.object(provider, "_request_json", side_effect=fake_request):
                image = provider._generate_image_from_prompt(
                    "render a hardware enclosure",
                    view_id="case",
                    label="Case",
                    reference_view_id=None,
                )

        self.assertEqual("together", image.provider)
        self.assertEqual("openai/gpt-image-2", image.model)
        self.assertTrue(image.data_url.startswith("data:image/png;base64,"))
        self.assertEqual(
            {
                "model": "openai/gpt-image-2",
                "prompt": "render a hardware enclosure",
            },
            calls[0]["payload"],
        )

    def test_together_image_generation_sends_dimensions_and_steps(self) -> None:
        calls = []
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "together",
                "TOGETHER_API_KEY": "together-secret",
                "TOGETHER_IMAGE_MODEL": "black-forest-labs/FLUX.1.1-pro",
                "TOGETHER_IMAGE_SIZE": "768x512",
                "TOGETHER_IMAGE_STEPS": "8",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, TogetherImageProvider)

            def fake_request(path: str, method: str = "GET", payload=None):
                calls.append({"path": path, "method": method, "payload": payload})
                return {"data": [{"b64_json": "ZmFrZS1pbWFnZQ=="}]}

            with patch.object(provider, "_request_json", side_effect=fake_request):
                image = provider._generate_image_from_prompt(
                    "render a hardware enclosure",
                    view_id="case",
                    label="Case",
                    reference_view_id=None,
                )

        self.assertEqual("together", image.provider)
        self.assertEqual("black-forest-labs/FLUX.1.1-pro", image.model)
        self.assertTrue(image.data_url.startswith("data:image/png;base64,"))
        self.assertEqual("images/generations", calls[0]["path"])
        self.assertEqual("POST", calls[0]["method"])
        self.assertEqual(
            {
                "model": "black-forest-labs/FLUX.1.1-pro",
                "prompt": "render a hardware enclosure",
                "n": 1,
                "response_format": "base64",
                "output_format": "png",
                "width": 768,
                "height": 512,
                "steps": 8,
            },
            calls[0]["payload"],
        )

    def test_huggingface_image_provider_routes_from_image_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "huggingface",
                "HF_TOKEN": "hf_scoped",
                "HUGGINGFACE_IMAGE_MODEL": "black-forest-labs/FLUX.1-schnell",
                "HUGGINGFACE_IMAGE_INFERENCE_PROVIDER": "fal-ai",
                "HUGGINGFACE_IMAGE_MODEL_LICENSE": "apache-2.0",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, HuggingFaceImageProvider)
        self.assertEqual("huggingface", provider.provider_name)
        self.assertEqual("black-forest-labs/FLUX.1-schnell", provider.model_name)
        self.assertEqual("fal-ai", provider.inference_provider)
        self.assertEqual("apache-2.0", provider.model_license)
        self.assertEqual(6000, provider.prompt_max_chars)
        self.assertEqual(4000, provider.prompt_target_chars)
        self.assertTrue(provider.is_configured)

    def test_huggingface_gated_image_models_are_disabled_by_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "hf",
                "HF_TOKEN": "hf_scoped",
                "HUGGINGFACE_IMAGE_MODEL": "black-forest-labs/FLUX.1-dev",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)

        self.assertIsInstance(provider, HuggingFaceImageProvider)
        self.assertFalse(provider.is_configured)
        self.assertIn("gated", provider.get_debug_config()["reason"].lower())

    def test_huggingface_image_generation_records_policy_metadata(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls = []

            def text_to_image(self, prompt: str, model: str, **parameters):
                self.calls.append({"prompt": prompt, "model": model, "parameters": parameters})
                return b"fake-image-bytes"

        fake_client = FakeClient()
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "huggingface",
                "HF_TOKEN": "hf_scoped",
                "HUGGINGFACE_IMAGE_MODEL": "Qwen/Qwen-Image",
                "HUGGINGFACE_IMAGE_INFERENCE_PROVIDER": "fal-ai",
                "HUGGINGFACE_IMAGE_MODEL_REVISION": "abc123",
                "HUGGINGFACE_IMAGE_MODEL_LICENSE": "apache-2.0",
                "HUGGINGFACE_IMAGE_SIZE": "768x512",
                "HUGGINGFACE_IMAGE_STEPS": "12",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, HuggingFaceImageProvider)
            with patch.object(provider, "_client", return_value=fake_client):
                image = provider._generate_image_from_prompt(
                    "render a hardware enclosure",
                    view_id="case",
                    label="Case",
                    reference_view_id=None,
                )

        self.assertEqual("huggingface", image.provider)
        self.assertEqual("Qwen/Qwen-Image", image.model)
        self.assertEqual("abc123", image.model_revision)
        self.assertEqual("fal-ai", image.inference_provider)
        self.assertEqual("apache-2.0", image.model_license)
        self.assertTrue(image.data_url.startswith("data:image/png;base64,"))
        self.assertEqual(768, fake_client.calls[0]["parameters"]["width"])
        self.assertEqual(512, fake_client.calls[0]["parameters"]["height"])
        self.assertEqual(12, fake_client.calls[0]["parameters"]["num_inference_steps"])

    def test_huggingface_image_generation_accepts_pillow_images(self) -> None:
        from PIL import Image

        class FakeClient:
            def text_to_image(self, prompt: str, model: str, **parameters):
                return Image.new("RGB", (16, 12), color=(25, 140, 210))

        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "huggingface",
                "HF_TOKEN": "hf_scoped",
                "HUGGINGFACE_IMAGE_MODEL": "black-forest-labs/FLUX.1-schnell",
                "HUGGINGFACE_IMAGE_INFERENCE_PROVIDER": "fal-ai",
                "HUGGINGFACE_IMAGE_SIZE": "16x12",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, HuggingFaceImageProvider)
            with patch.object(provider, "_client", return_value=FakeClient()):
                image = provider._generate_image_from_prompt(
                    "render a hardware enclosure",
                    view_id="case",
                    label="Case",
                    reference_view_id=None,
                )

        self.assertEqual("huggingface", image.provider)
        self.assertEqual("black-forest-labs/FLUX.1-schnell", image.model)
        self.assertTrue(image.data_url.startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
