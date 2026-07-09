from __future__ import annotations

from pathlib import Path
from typing import Iterable

from blueprint_core.openai_streams import OpenAIStreamConfig
from blueprint_core.providers.base import ProviderClient, ProviderConfigurationError
from blueprint_core.providers.models import PreparedProviderRequest, ProviderEvent, ProviderRequest, ProviderSpec
from blueprint_core.providers.openai import OpenAIResponsesProviderClient, OpenAIResponsesStreamerFactory
from blueprint_core.providers.openai_compatible import OpenAICompatibleChatProviderClient, OpenAICompatibleStreamerFactory
from blueprint_core.providers.registry_utils import normalize_provider_name


class ProviderRegistry:
    def __init__(self, clients: Iterable[ProviderClient]) -> None:
        self._clients = {client.provider_name: client for client in clients}

    @classmethod
    def default(
        cls,
        *,
        env_file: Path,
        openai_config: OpenAIStreamConfig,
        openai_streamer_factory: OpenAIResponsesStreamerFactory | None = None,
        openai_compatible_streamer_factory: OpenAICompatibleStreamerFactory | None = None,
    ) -> "ProviderRegistry":
        return cls(
            (
                OpenAIResponsesProviderClient(
                    config=openai_config,
                    streamer_factory=openai_streamer_factory,
                ),
                OpenAICompatibleChatProviderClient.baseten(
                    env_file=env_file,
                    streamer_factory=openai_compatible_streamer_factory,
                ),
                OpenAICompatibleChatProviderClient.gmi(
                    env_file=env_file,
                    streamer_factory=openai_compatible_streamer_factory,
                ),
            )
        )

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._clients))

    def client(self, provider_name: str) -> ProviderClient:
        provider = normalize_provider_name(provider_name)
        client = self._clients.get(provider)
        if client is None:
            supported = ", ".join(self.providers()) or "none"
            raise ProviderConfigurationError(f"Unsupported provider {provider_name!r}. Supported providers: {supported}.")
        return client

    def spec(self, provider_name: str) -> ProviderSpec:
        return self.client(provider_name).spec()

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        client = self.client(request.provider)
        return client.prepare(request)

    def stream_text(self, prepared: PreparedProviderRequest) -> Iterable[ProviderEvent]:
        client = self.client(prepared.provider)
        yield from client.stream_text(prepared)
