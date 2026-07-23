from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from blueprint_core.image_providers import GeneratedImage, GMIImageProvider, HuggingFaceImageProvider, OpenAIImageProvider, TogetherImageProvider, build_image_provider


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

    def test_gmi_native_gpt_image_uses_documented_fields(self) -> None:
        calls = []
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "gmi",
                "GMI_API_KEY": "gmi-secret",
                "GMI_IMAGE_MODEL": "gpt-image-2",
                "GMI_IMAGE_SIZE": "1536x1024",
                "GMI_IMAGE_QUALITY": "high",
                "GMI_IMAGE_OUTPUT_FORMAT": "jpeg",
                "GMI_IMAGE_OUTPUT_COMPRESSION": "82",
                "GMI_IMAGE_BACKGROUND": "opaque",
                "GMI_IMAGE_MODERATION": "low",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, GMIImageProvider)

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

        self.assertEqual("gmi", image.provider)
        self.assertEqual("gpt-image-2", image.model)
        self.assertEqual(
            {
                "model": "gpt-image-2",
                "prompt": "render a hardware enclosure",
                "size": "1536x1024",
                "quality": "high",
                "output_format": "jpeg",
                "background": "opaque",
                "moderation": "low",
                "n": 1,
                "output_compression": 82,
            },
            calls[0]["payload"],
        )

    def test_direct_image_model_test_bypasses_project_sequence(self) -> None:
        with patch.dict(
            os.environ,
            {"IMAGE_PROVIDER": "gmi", "GMI_API_KEY": "gmi-secret", "GMI_IMAGE_MODEL": "gpt-image-2"},
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, GMIImageProvider)
            expected = GeneratedImage(
                data_url="data:image/png;base64,ZmFrZQ==",
                provider="gmi",
                model="gpt-image-2",
                size="1024x1024",
                prompt="test prompt",
            )
            with patch.object(provider, "_generate_image_from_prompt", return_value=expected) as generate:
                result = provider.generate_test_image("test prompt")

        self.assertIs(expected, result)
        generate.assert_called_once_with(
            "test prompt",
            view_id="image-model-test",
            label="Image model test",
            reference_view_id=None,
        )

    def test_gmi_gemini_image_uses_request_queue_and_model_specific_fields(self) -> None:
        calls = []
        responses = [
            {"request_id": "request-123", "status": "queued"},
            {
                "request_id": "request-123",
                "status": "success",
                "outcome": {"media_urls": [{"id": "0", "url": "https://storage.example/gmi-image.png"}]},
            },
        ]
        with patch.dict(
            os.environ,
            {
                "IMAGE_PROVIDER": "gmi",
                "GMI_API_KEY": "gmi-secret",
                "GMI_IMAGE_MODEL": "gemini-3.1-flash-image-preview",
                "GMI_IMAGE_RESOLUTION": "2K",
                "GMI_IMAGE_ASPECT_RATIO": "16:9",
                "GMI_IMAGE_OUTPUT_FORMAT": "jpeg",
            },
            clear=True,
        ):
            provider = build_image_provider(force_enabled=True)
            assert isinstance(provider, GMIImageProvider)

            def fake_queue_request(*, method: str, request_id=None, payload=None):
                calls.append({"method": method, "request_id": request_id, "payload": payload})
                return responses.pop(0)

            with patch.object(provider, "_request_queue_json", side_effect=fake_queue_request), patch(
                "blueprint_core.image_providers.time.sleep"
            ):
                image = provider._generate_image_from_prompt(
                    "render a hardware enclosure",
                    view_id="case",
                    label="Case",
                    reference_view_id=None,
                )

        self.assertEqual("https://storage.example/gmi-image.png", image.data_url)
        self.assertEqual("2K 16:9", image.size)
        self.assertEqual(
            {
                "method": "POST",
                "request_id": None,
                "payload": {
                    "model": "gemini-3.1-flash-image-preview",
                    "payload": {
                        "prompt": "render a hardware enclosure",
                        "image_size": "2K",
                        "aspect_ratio": "16:9",
                        "image_output_format": "jpeg",
                    },
                },
            },
            calls[0],
        )
        self.assertEqual({"method": "GET", "request_id": "request-123", "payload": None}, calls[1])

    def test_gmi_queue_payloads_match_documented_model_schemas(self) -> None:
        cases = [
            (
                {
                    "GMI_IMAGE_MODEL": "gpt-image-1.5",
                    "GMI_IMAGE_SIZE": "1536x1024",
                    "GMI_IMAGE_QUALITY": "high",
                    "GMI_IMAGE_OUTPUT_FORMAT": "webp",
                    "GMI_IMAGE_OUTPUT_COMPRESSION": "75",
                    "GMI_IMAGE_BACKGROUND": "transparent",
                },
                {
                    "prompt": "render a hardware enclosure",
                    "size": "1536x1024",
                    "quality": "high",
                    "output_format": "webp",
                    "background": "transparent",
                    "n": 1,
                    "output_compression": 75,
                },
            ),
            (
                {
                    "GMI_IMAGE_MODEL": "flux-kontext-pro",
                    "GMI_IMAGE_ASPECT_RATIO": "7:3",
                    "GMI_IMAGE_SEED": "123",
                    "GMI_IMAGE_PROMPT_UPSAMPLING": "true",
                    "GMI_IMAGE_SAFETY_TOLERANCE": "5",
                    "GMI_IMAGE_OUTPUT_FORMAT": "jpeg",
                },
                {
                    "prompt": "render a hardware enclosure",
                    "aspect_ratio": "7:3",
                    "seed": 123,
                    "prompt_upsampling": True,
                    "safety_tolerance": 5,
                    "output_format": "jpeg",
                },
            ),
            (
                {
                    "GMI_IMAGE_MODEL": "seedream-5.0-lite",
                    "GMI_IMAGE_SIZE": "3K",
                    "GMI_IMAGE_OUTPUT_FORMAT": "png",
                    "GMI_IMAGE_SEQUENTIAL_GENERATION": "auto",
                    "GMI_IMAGE_WATERMARK": "true",
                },
                {
                    "prompt": "render a hardware enclosure",
                    "size": "3K",
                    "output_format": "png",
                    "max_images": 1,
                    "sequential_image_generation": "auto",
                    "watermark": True,
                },
            ),
            (
                {"GMI_IMAGE_MODEL": "seedream-5.0-pro"},
                {
                    "prompt": "render a hardware enclosure",
                    "size": "2048x2048",
                    "output_format": "jpeg",
                    "max_images": 1,
                    "sequential_image_generation": "disabled",
                    "watermark": False,
                },
            ),
            (
                {"GMI_IMAGE_MODEL": "wan2.7-image"},
                {"text": "render a hardware enclosure", "size": "2K", "n": 1},
            ),
            (
                {"GMI_IMAGE_MODEL": "wan2.7-image-pro", "GMI_IMAGE_RESOLUTION": "4K"},
                {"text": "render a hardware enclosure", "size": "4K", "n": 1},
            ),
        ]

        for model_env, expected_payload in cases:
            with self.subTest(model=model_env["GMI_IMAGE_MODEL"]), patch.dict(
                os.environ,
                {"IMAGE_PROVIDER": "gmi", "GMI_API_KEY": "gmi-secret", **model_env},
                clear=True,
            ):
                provider = build_image_provider(force_enabled=True)
                assert isinstance(provider, GMIImageProvider)
                self.assertEqual(expected_payload, provider._queue_payload("render a hardware enclosure"))

                if provider.model_name == "flux-kontext-pro":
                    self.assertEqual(2000, provider.prompt_max_chars)
                if provider.model_name == "seedream-5.0-lite":
                    self.assertEqual("3K", provider.size)
                if provider.model_name == "seedream-5.0-pro":
                    self.assertEqual("2048x2048", provider.size)
                    self.assertEqual("jpeg", provider.output_format)

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
