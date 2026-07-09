from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blueprint_core.openai_streams import OpenAICompatibleChatConfig, OpenAIStreamConfig, OpenAITextStreamChunk
from blueprint_core.providers import (
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderRequest,
    model_name_for_provider,
    normalize_provider_name,
)


class FakeOpenAIStreamer:
    configs: list[OpenAIStreamConfig] = []

    def __init__(self, config: OpenAIStreamConfig) -> None:
        self.config = config
        self.configs.append(config)

    def stream_text(self):
        yield OpenAITextStreamChunk(
            sequence=1,
            content=f"openai:{self.config.model}:{self.config.prompt}",
            done=False,
            response_event_type="response.output_text.delta",
            response_id="resp_unit",
        )
        yield OpenAITextStreamChunk(
            sequence=2,
            content="",
            done=True,
            response_event_type="response.completed",
            response_id="resp_unit",
        )


class FakeCompatibleStreamer:
    configs: list[OpenAICompatibleChatConfig] = []

    def __init__(self, config: OpenAICompatibleChatConfig) -> None:
        self.config = config
        self.configs.append(config)

    def stream_text(self):
        yield OpenAITextStreamChunk(
            sequence=1,
            content=f"{self.config.provider_name}:{self.config.model}:{self.config.prompt}",
            done=False,
            response_event_type="chat.completion.message",
            response_id="chat_unit",
        )
        yield OpenAITextStreamChunk(
            sequence=2,
            content="",
            done=True,
            response_event_type="chat.completion.stop",
            response_id="chat_unit",
        )


class ProviderRegistryTests(unittest.TestCase):
    def test_provider_aliases_and_model_prefixes_are_normalized(self) -> None:
        self.assertEqual("baseten", normalize_provider_name("base10"))
        self.assertEqual("gmi", normalize_provider_name("gemicloud"))
        self.assertEqual("zai-org/GLM-5.2", model_name_for_provider("baseten", "baseten/zai-org/GLM-5.2"))
        self.assertEqual("anthropic/claude-fable-5", model_name_for_provider("gmi", "gemicloud/fable"))
        self.assertEqual("gpt-5.5", model_name_for_provider("openai", "openai/gpt-5.5"))

    def test_registry_streams_openai_without_provider_branching(self) -> None:
        FakeOpenAIStreamer.configs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ProviderRegistry.default(
                env_file=Path(temp_dir) / ".env",
                openai_config=OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback"),
                openai_streamer_factory=FakeOpenAIStreamer,
                openai_compatible_streamer_factory=FakeCompatibleStreamer,
            )

            prepared = registry.prepare(
                ProviderRequest(
                    provider="openai",
                    model="openai/gpt-test",
                    prompt="blue monitor",
                    max_output_tokens=123,
                )
            )
            events = tuple(registry.stream_text(prepared))

            self.assertEqual("openai", prepared.provider)
            self.assertEqual("gpt-test", prepared.model_name)
            self.assertEqual("responses", prepared.endpoint_path)
            self.assertEqual(123, FakeOpenAIStreamer.configs[0].max_output_tokens)
            self.assertEqual("openai:gpt-test:blue monitor", events[0].content)

    def test_registry_streams_baseten_as_chat_completion_provider(self) -> None:
        FakeCompatibleStreamer.configs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "BASETEN_API_KEY=test-baseten-key\n"
                "BASETEN_BASE_URL=https://inference.baseten.co/v1\n",
                encoding="utf-8",
            )
            registry = ProviderRegistry.default(
                env_file=env_file,
                openai_config=OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback"),
                openai_streamer_factory=FakeOpenAIStreamer,
                openai_compatible_streamer_factory=FakeCompatibleStreamer,
            )

            prepared = registry.prepare(
                ProviderRequest(
                    provider="base10",
                    model="baseten/zai-org/GLM-5.2",
                    prompt="review prompt metadata",
                    max_output_tokens=456,
                )
            )
            events = tuple(registry.stream_text(prepared))

            self.assertEqual("baseten", prepared.provider)
            self.assertEqual("zai-org/GLM-5.2", prepared.model_name)
            self.assertEqual("chat/completions", prepared.endpoint_path)
            self.assertEqual(456, FakeCompatibleStreamer.configs[0].max_output_tokens)
            self.assertEqual("baseten:zai-org/GLM-5.2:review prompt metadata", events[0].content)

    def test_registry_streams_gmi_fable_as_chat_completion_provider(self) -> None:
        FakeCompatibleStreamer.configs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "GMI_API_KEY=test-gmi-key\n"
                "GMI_BASE_URL=https://api.gmi-serving.com/v1\n"
                "LLM_TEMPERATURE=0.9\n",
                encoding="utf-8",
            )
            registry = ProviderRegistry.default(
                env_file=env_file,
                openai_config=OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback"),
                openai_streamer_factory=FakeOpenAIStreamer,
                openai_compatible_streamer_factory=FakeCompatibleStreamer,
            )

            prepared = registry.prepare(
                ProviderRequest(
                    provider="gemicloud",
                    model="gemicloud/fable",
                    prompt="review prompt metadata",
                    max_output_tokens=789,
                )
            )
            events = tuple(registry.stream_text(prepared))

            self.assertEqual("gmi", prepared.provider)
            self.assertEqual("anthropic/claude-fable-5", prepared.model_name)
            self.assertEqual("chat/completions", prepared.endpoint_path)
            self.assertEqual(789, FakeCompatibleStreamer.configs[0].max_output_tokens)
            self.assertIsNone(FakeCompatibleStreamer.configs[0].temperature)
            self.assertEqual("gmi:anthropic/claude-fable-5:review prompt metadata", events[0].content)

    def test_registry_does_not_fallback_for_unsupported_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ProviderRegistry.default(
                env_file=Path(temp_dir) / ".env",
                openai_config=OpenAIStreamConfig(api_key="test-key", model="gpt-test", prompt="fallback"),
            )

            with self.assertRaises(ProviderConfigurationError):
                registry.prepare(ProviderRequest(provider="runpod", model="caid-technologies/parti-base", prompt="blue"))


if __name__ == "__main__":
    unittest.main()
