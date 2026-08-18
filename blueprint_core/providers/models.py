from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_text: bool = True
    supports_streaming: bool = False
    supports_chat_completions: bool = False
    supports_responses_api: bool = False
    supports_images: bool = False
    supports_structured_output: bool = False
    supports_async_jobs: bool = False


@dataclass(frozen=True)
class ProviderAuth:
    api_key: str = ""
    source_name: str = ""
    header_name: str = "Authorization"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    base_url: str
    default_model: str
    auth: ProviderAuth = field(default_factory=ProviderAuth)
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    timeout_seconds: float = 300.0

    @property
    def configured(self) -> bool:
        return self.auth.configured


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    supports_text: bool = True
    supports_streaming: bool = False
    supports_images: bool = False
    supports_structured_output: bool = False
    timeout_seconds: float = 300.0

    @property
    def llm_id(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class ProviderPolicy:
    allow_fallback: bool = False
    retry_count: int = 0
    fail_fast: bool = True
    record_raw_errors: bool = True


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    model: str
    prompt: str
    instructions: Optional[str] = None
    max_output_tokens: int = 1600
    timeout_seconds: Optional[float] = None
    stream: bool = True
    temperature: Optional[float] = None
    policy: ProviderPolicy = field(default_factory=ProviderPolicy)


@dataclass(frozen=True)
class PreparedProviderRequest:
    spec: ProviderSpec
    model: ModelSpec
    request: ProviderRequest
    endpoint_path: str

    @property
    def provider(self) -> str:
        return self.spec.name

    @property
    def model_name(self) -> str:
        return self.model.model

    @property
    def base_url(self) -> str:
        return self.spec.base_url


@dataclass(frozen=True)
class ProviderEvent:
    sequence: int
    content: str
    done: bool
    event_type: str
    response_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    status: str
    text: str
    event_count: int
    error_message: Optional[str] = None
    duration_seconds: float = 0.0

    @classmethod
    def from_events(
        cls,
        *,
        provider: str,
        model: str,
        events: tuple[ProviderEvent, ...],
        duration_seconds: float = 0.0,
    ) -> "ProviderResult":
        error = next((event.error_message for event in events if event.error_message), None)
        return cls(
            provider=provider,
            model=model,
            status="failed" if error else "succeeded",
            text="".join(event.content for event in events),
            event_count=len(events),
            error_message=error,
            duration_seconds=duration_seconds,
        )
