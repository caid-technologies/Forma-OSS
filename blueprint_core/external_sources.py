from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

from blueprint_core.agents.firecrawl_mcp import FirecrawlMCPResearchClient


DEFAULT_EXTERNAL_SOURCE_PROVIDER = "firecrawl"
SUPPORTED_EXTERNAL_SOURCE_PROVIDERS = {"auto", "none", "disabled", "off", "tavily", "firecrawl"}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, min(maximum, int(raw.strip())))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, min(maximum, float(raw.strip())))
    except ValueError:
        return default


def _first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


class ExternalSourceRecord(BaseModel):
    title: str = ""
    url: str = ""
    content: str = ""
    source_type: str = "web"
    provider: str = ""
    score: Optional[float] = None
    published_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_prompt_block(self, index: int, *, max_chars: int) -> str:
        text = (self.content or "").strip() or self.title or self.url
        block = f"[{index}] {self.title or 'Untitled source'}\nProvider: {self.provider or 'unknown'}\nURL: {self.url or 'unknown'}\n{text}"
        if len(block) > max_chars:
            return block[: max(0, max_chars - 3)] + "..."
        return block

    def metadata_preview(self, *, max_chars: int = 360) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "provider": self.provider,
            "source_type": self.source_type,
            "score": self.score,
            "published_at": self.published_at,
            "content_preview": self.content[:max_chars],
        }


class ExternalSourceLibrary(BaseModel):
    provider: str
    configured: bool
    searches_attempted: int = 0
    sources: list[ExternalSourceRecord] = Field(default_factory=list)
    answer: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def hits(self) -> list[ExternalSourceRecord]:
        return self.sources

    def as_prompt_context(self, max_chars: int = 14000) -> str:
        if not self.sources:
            return f"No {self.provider} external source results were available."

        blocks: list[str] = []
        remaining = max_chars
        if self.answer:
            answer_block = f"{self.provider} answer summary:\n{self.answer.strip()}"
            blocks.append(answer_block[:remaining])
            remaining -= len(blocks[-1])

        for index, source in enumerate(self.sources, start=1):
            if remaining <= 0:
                break
            block = source.as_prompt_block(index, max_chars=remaining)
            blocks.append(block)
            remaining -= len(block)
        return "\n\n".join(blocks)

    def source_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "searches_attempted": self.searches_attempted,
            "source_count": len(self.sources),
            "sources": [source.metadata_preview() for source in self.sources[:12]],
            "answer": self.answer,
            "error": self.error,
            **self.metadata,
        }


@dataclass(frozen=True)
class ExternalSourceProviderConfig:
    provider: str
    enabled: bool
    reason: Optional[str] = None
    search_limit: int = 3
    timeout_seconds: float = 45.0
    search_depth: str = "basic"
    include_answer: bool = True
    include_raw_content: bool = False

    @classmethod
    def from_env(cls, provider_override: Optional[str] = None) -> "ExternalSourceProviderConfig":
        if _env_bool("EXTERNAL_SOURCE_DISABLED", False) or _env_bool("WEB_RESEARCH_DISABLED", False):
            return cls(provider="none", enabled=False, reason="EXTERNAL_SOURCE_DISABLED or WEB_RESEARCH_DISABLED is true.")

        requested = (
            provider_override
            or os.getenv("EXTERNAL_SOURCE_PROVIDER")
            or os.getenv("WEB_RESEARCH_PROVIDER")
            or DEFAULT_EXTERNAL_SOURCE_PROVIDER
        ).strip().lower().replace("_", "-")
        if requested not in SUPPORTED_EXTERNAL_SOURCE_PROVIDERS:
            return cls(provider=requested, enabled=False, reason=f"Unsupported EXTERNAL_SOURCE_PROVIDER {requested!r}.")

        search_limit = _env_int("EXTERNAL_SOURCE_SEARCH_LIMIT", _env_int("FIRECRAWL_SEARCH_LIMIT", 3, 1, 8), 1, 8)
        timeout = _env_float(
            "EXTERNAL_SOURCE_TIMEOUT_SECONDS",
            _env_float("FIRECRAWL_MCP_TIMEOUT_SECONDS", 45.0, 5.0, 180.0),
            5.0,
            180.0,
        )

        if requested in {"none", "disabled", "off"}:
            return cls(provider="none", enabled=False, reason="External source research is disabled.")
        if requested in {"auto", "tavily", "firecrawl"}:
            firecrawl_config = FirecrawlMCPResearchClient().config
            return cls(
                provider="firecrawl",
                enabled=firecrawl_config.enabled,
                reason=firecrawl_config.reason,
                search_limit=firecrawl_config.search_limit or search_limit,
                timeout_seconds=firecrawl_config.timeout_seconds or timeout,
            )

        return cls(
            provider="firecrawl",
            enabled=False,
            reason="Set FIRECRAWL_API_KEY or FIRECRAWL_MCP_COMMAND to enable web research.",
            search_limit=search_limit,
            timeout_seconds=timeout,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "reason": self.reason,
            "search_limit": self.search_limit,
            "timeout_seconds": self.timeout_seconds,
            "search_depth": self.search_depth,
            "include_answer": self.include_answer,
            "include_raw_content": self.include_raw_content,
        }


class ExternalSourceProvider(ABC):
    provider_name: str

    def __init__(self, config: Optional[ExternalSourceProviderConfig] = None) -> None:
        self.config = config or ExternalSourceProviderConfig.from_env()
        self.provider_name = self.config.provider

    @abstractmethod
    def research(self, queries: Iterable[str]) -> ExternalSourceLibrary:
        raise NotImplementedError

    def get_debug_config(self) -> dict[str, Any]:
        return self.config.as_dict()


class NoExternalSourceProvider(ExternalSourceProvider):
    def research(self, queries: Iterable[str]) -> ExternalSourceLibrary:
        query_list = [query for query in queries if query and query.strip()]
        return ExternalSourceLibrary(
            provider=self.config.provider,
            configured=False,
            searches_attempted=0,
            error=self.config.reason or "External source provider is not configured.",
            metadata={"requested_queries": len(query_list)},
        )


class FirecrawlExternalSourceProvider(ExternalSourceProvider):
    def __init__(self, config: Optional[ExternalSourceProviderConfig] = None) -> None:
        super().__init__(config)
        self.client = FirecrawlMCPResearchClient()

    def research(self, queries: Iterable[str]) -> ExternalSourceLibrary:
        result = self.client.research(queries)
        sources = [
            ExternalSourceRecord(
                title=hit.title,
                url=hit.url,
                content=hit.content,
                provider="firecrawl",
                source_type="web",
            )
            for hit in result.hits
        ]
        return ExternalSourceLibrary(
            provider="firecrawl",
            configured=result.configured,
            searches_attempted=result.searches_attempted,
            sources=sources,
            error=result.error,
            metadata={"tool_name": result.tool_name},
        )


def _dedupe_sources(sources: list[ExternalSourceRecord], *, max_items: int) -> list[ExternalSourceRecord]:
    seen: set[str] = set()
    deduped: list[ExternalSourceRecord] = []
    for source in sources:
        key = (source.url or source.title or source.content[:80]).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped[:max_items]


def build_external_source_provider(
    config: Optional[ExternalSourceProviderConfig] = None,
    *,
    provider: Optional[str] = None,
) -> ExternalSourceProvider:
    resolved = config or ExternalSourceProviderConfig.from_env(provider_override=provider)
    if not resolved.enabled:
        return NoExternalSourceProvider(resolved)
    if resolved.provider == "firecrawl":
        return FirecrawlExternalSourceProvider(resolved)
    return NoExternalSourceProvider(resolved)


__all__ = [
    "ExternalSourceLibrary",
    "ExternalSourceProvider",
    "ExternalSourceProviderConfig",
    "ExternalSourceRecord",
    "FirecrawlExternalSourceProvider",
    "NoExternalSourceProvider",
    "SUPPORTED_EXTERNAL_SOURCE_PROVIDERS",
    "build_external_source_provider",
]
