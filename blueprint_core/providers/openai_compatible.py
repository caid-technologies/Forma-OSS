from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, Protocol

from blueprint_core.openai_streams import (
    DEFAULT_BASETEN_BASE_URL,
    DEFAULT_BASETEN_STREAM_MODEL,
    DEFAULT_GMI_BASE_URL,
    DEFAULT_GMI_STREAM_MODEL,
    OpenAICompatibleChatCompletionsStreamer,
    OpenAICompatibleChatConfig,
    OpenAITextStreamChunk,
    first_env,
    merged_env,
)
from blueprint_core.providers.models import (
    ModelSpec,
    PreparedProviderRequest,
    ProviderAuth,
    ProviderCapabilities,
    ProviderEvent,
    ProviderRequest,
    ProviderSpec,
)
from blueprint_core.providers.registry_utils import model_name_for_provider, normalize_provider_name


class OpenAICompatibleStreamerProtocol(Protocol):
    def stream_text(self) -> Iterable[OpenAITextStreamChunk]:
        ...


OpenAICompatibleStreamerFactory = Callable[[OpenAICompatibleChatConfig], OpenAICompatibleStreamerProtocol]


class OpenAICompatibleChatProviderClient:
    def __init__(
        self,
        *,
        provider_name: str,
        display_name: str,
        env_file: Path,
        default_model: str,
        default_base_url: str,
        api_key_env_names: tuple[str, ...],
        base_url_env_names: tuple[str, ...],
        model_env_names: tuple[str, ...],
        streamer_factory: OpenAICompatibleStreamerFactory | None = None,
    ) -> None:
        self._provider_name = normalize_provider_name(provider_name)
        self.display_name = display_name
        self.env_file = env_file
        self.default_model = default_model
        self.default_base_url = default_base_url
        self.api_key_env_names = api_key_env_names
        self.base_url_env_names = base_url_env_names
        self.model_env_names = model_env_names
        self.streamer_factory = streamer_factory or OpenAICompatibleChatCompletionsStreamer

    @classmethod
    def baseten(
        cls,
        *,
        env_file: Path,
        streamer_factory: OpenAICompatibleStreamerFactory | None = None,
    ) -> "OpenAICompatibleChatProviderClient":
        return cls(
            provider_name="baseten",
            display_name="Baseten",
            env_file=env_file,
            default_model=DEFAULT_BASETEN_STREAM_MODEL,
            default_base_url=DEFAULT_BASETEN_BASE_URL,
            api_key_env_names=("BASETEN_API_KEY", "LLM_API_KEY"),
            base_url_env_names=("BASETEN_BASE_URL", "LLM_BASE_URL"),
            model_env_names=("BASETEN_STREAM_MODEL", "BASETEN_MODEL", "LLM_MODEL"),
            streamer_factory=streamer_factory,
        )

    @classmethod
    def gmi(
        cls,
        *,
        env_file: Path,
        streamer_factory: OpenAICompatibleStreamerFactory | None = None,
    ) -> "OpenAICompatibleChatProviderClient":
        return cls(
            provider_name="gmi",
            display_name="GMI Cloud",
            env_file=env_file,
            default_model=DEFAULT_GMI_STREAM_MODEL,
            default_base_url=DEFAULT_GMI_BASE_URL,
            api_key_env_names=("GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY", "LLM_API_KEY"),
            base_url_env_names=("GMI_BASE_URL", "GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL"),
            model_env_names=("GMI_STREAM_MODEL", "GMI_MODEL", "GMI_CLOUD_MODEL", "GMICLOUD_MODEL", "LLM_MODEL"),
            streamer_factory=streamer_factory,
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def spec(self) -> ProviderSpec:
        env = merged_env(self.env_file)
        api_key_source = next((name for name in self.api_key_env_names if first_env(env, name)), self.api_key_env_names[0])
        api_key = first_env(env, *self.api_key_env_names) or ""
        base_url = first_env(env, *self.base_url_env_names) or self.default_base_url
        model = first_env(env, *self.model_env_names) or self.default_model
        return ProviderSpec(
            name=self.provider_name,
            display_name=self.display_name,
            base_url=base_url.rstrip("/"),
            default_model=model,
            auth=ProviderAuth(api_key=api_key, source_name=api_key_source),
            capabilities=ProviderCapabilities(
                supports_text=True,
                supports_streaming=True,
                supports_chat_completions=True,
                supports_structured_output=True,
            ),
        )

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        spec = self.spec()
        timeout_seconds = request.timeout_seconds or spec.timeout_seconds
        model = model_name_for_provider(self.provider_name, request.model or spec.default_model)
        return PreparedProviderRequest(
            spec=replace(spec, timeout_seconds=timeout_seconds),
            model=ModelSpec(
                provider=self.provider_name,
                model=model,
                supports_text=True,
                supports_streaming=True,
                supports_structured_output=True,
                timeout_seconds=timeout_seconds,
            ),
            request=request,
            endpoint_path="chat/completions",
        )

    def _config_for_prepared(self, prepared: PreparedProviderRequest) -> OpenAICompatibleChatConfig:
        return OpenAICompatibleChatConfig.from_env_file(
            self.env_file,
            provider_name=self.provider_name,
            model=prepared.model_name,
            base_url=prepared.base_url,
            prompt=prepared.request.prompt,
            timeout_seconds=prepared.request.timeout_seconds,
            max_output_tokens=prepared.request.max_output_tokens,
            instructions=prepared.request.instructions,
            temperature=prepared.request.temperature,
        )

    def stream_text(self, prepared: PreparedProviderRequest) -> Iterable[ProviderEvent]:
        config = self._config_for_prepared(prepared)
        for chunk in self.streamer_factory(config).stream_text():
            yield ProviderEvent(
                sequence=chunk.sequence,
                content=chunk.content,
                done=chunk.done,
                event_type=chunk.response_event_type,
                response_id=chunk.response_id,
                error_message=chunk.error_message,
            )
