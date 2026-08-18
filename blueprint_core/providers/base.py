from __future__ import annotations

from typing import Iterable, Protocol

from blueprint_core.providers.models import PreparedProviderRequest, ProviderEvent, ProviderRequest, ProviderSpec


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderExecutionError(RuntimeError):
    pass


class ProviderClient(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    def spec(self) -> ProviderSpec:
        ...

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        ...

    def stream_text(self, prepared: PreparedProviderRequest) -> Iterable[ProviderEvent]:
        ...
