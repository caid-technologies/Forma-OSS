from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable, Protocol

from blueprint_core.openai_streams import OpenAIResponsesStreamer, OpenAIStreamConfig, OpenAITextStreamChunk
from blueprint_core.providers.models import (
    ModelSpec,
    PreparedProviderRequest,
    ProviderAuth,
    ProviderCapabilities,
    ProviderEvent,
    ProviderRequest,
    ProviderSpec,
)
from blueprint_core.providers.registry_utils import model_name_for_provider


class OpenAIStreamerProtocol(Protocol):
    def stream_text(self) -> Iterable[OpenAITextStreamChunk]:
        ...


OpenAIResponsesStreamerFactory = Callable[[OpenAIStreamConfig], OpenAIStreamerProtocol]


class OpenAIResponsesProviderClient:
    def __init__(
        self,
        *,
        config: OpenAIStreamConfig,
        streamer_factory: OpenAIResponsesStreamerFactory | None = None,
    ) -> None:
        self.config = config
        self.streamer_factory = streamer_factory or OpenAIResponsesStreamer

    @property
    def provider_name(self) -> str:
        return "openai"

    def spec(self) -> ProviderSpec:
        return ProviderSpec(
            name="openai",
            display_name="OpenAI",
            base_url=self.config.base_url,
            default_model=self.config.model,
            auth=ProviderAuth(api_key=self.config.api_key, source_name="OPENAI_API_KEY"),
            capabilities=ProviderCapabilities(
                supports_text=True,
                supports_streaming=True,
                supports_responses_api=True,
                supports_structured_output=True,
            ),
            timeout_seconds=self.config.timeout_seconds,
        )

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        model = model_name_for_provider("openai", request.model or self.config.model)
        timeout_seconds = request.timeout_seconds or self.config.timeout_seconds
        return PreparedProviderRequest(
            spec=replace(self.spec(), timeout_seconds=timeout_seconds),
            model=ModelSpec(
                provider="openai",
                model=model,
                supports_text=True,
                supports_streaming=True,
                supports_structured_output=True,
                timeout_seconds=timeout_seconds,
            ),
            request=request,
            endpoint_path="responses",
        )

    def stream_text(self, prepared: PreparedProviderRequest) -> Iterable[ProviderEvent]:
        request = prepared.request
        config = replace(
            self.config,
            prompt=request.prompt,
            model=prepared.model_name,
            instructions=request.instructions if request.instructions is not None else self.config.instructions,
            max_output_tokens=request.max_output_tokens,
            timeout_seconds=request.timeout_seconds or self.config.timeout_seconds,
        )
        for chunk in self.streamer_factory(config).stream_text():
            yield ProviderEvent(
                sequence=chunk.sequence,
                content=chunk.content,
                done=chunk.done,
                event_type=chunk.response_event_type,
                response_id=chunk.response_id,
                error_message=chunk.error_message,
            )
