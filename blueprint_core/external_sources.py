from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from blueprint_core.agents.firecrawl_mcp import FirecrawlMCPResearchClient


DEFAULT_EXTERNAL_SOURCE_PROVIDER = "firecrawl"
SUPPORTED_EXTERNAL_SOURCE_PROVIDERS = {"auto", "none", "disabled", "off", "tavily", "firecrawl"}
DEFAULT_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


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
            "domain": source_domain(self.url),
            "provider": self.provider,
            "source_type": self.source_type,
            "score": self.score,
            "published_at": self.published_at,
            "relevance_reason": self.metadata.get("relevance_reason"),
            "matched_query_terms": self.metadata.get("matched_query_terms"),
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

        search_limit = _env_int(
            "EXTERNAL_SOURCE_SEARCH_LIMIT",
            _env_int("FIRECRAWL_SEARCH_LIMIT", _env_int("TAVILY_SEARCH_LIMIT", 3, 1, 8), 1, 8),
            1,
            8,
        )
        timeout = _env_float(
            "EXTERNAL_SOURCE_TIMEOUT_SECONDS",
            _env_float("FIRECRAWL_MCP_TIMEOUT_SECONDS", _env_float("TAVILY_TIMEOUT_SECONDS", 45.0, 5.0, 180.0), 5.0, 180.0),
            5.0,
            180.0,
        )

        if requested in {"none", "disabled", "off"}:
            return cls(provider="none", enabled=False, reason="External source research is disabled.")
        if requested == "tavily":
            api_key = _first_env(("TAVILY_API_KEY",))
            return cls(
                provider="tavily",
                enabled=bool(api_key),
                reason=None if api_key else "Set TAVILY_API_KEY to enable Tavily source research.",
                search_limit=_env_int("TAVILY_SEARCH_LIMIT", search_limit, 1, 20),
                timeout_seconds=timeout,
                search_depth=(os.getenv("TAVILY_SEARCH_DEPTH") or "basic").strip().lower() or "basic",
                include_answer=_env_bool("TAVILY_INCLUDE_ANSWER", True),
                include_raw_content=_env_bool("TAVILY_INCLUDE_RAW_CONTENT", False),
            )

        if requested in {"auto", "firecrawl"}:
            firecrawl_config = FirecrawlMCPResearchClient().config
            return cls(
                provider="firecrawl",
                enabled=firecrawl_config.enabled,
                reason=firecrawl_config.reason,
                search_limit=firecrawl_config.search_limit or search_limit,
                timeout_seconds=firecrawl_config.timeout_seconds or timeout,
            )

        return cls(
            provider=requested,
            enabled=False,
            reason=f"Unsupported EXTERNAL_SOURCE_PROVIDER {requested!r}.",
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
        query_list = [query for query in queries if query and query.strip()]
        result = self.client.research(query_list)
        sources = [
            ExternalSourceRecord(
                title=hit.title,
                url=hit.url,
                content=hit.content,
                provider="firecrawl",
                source_type="web",
                metadata=source_relevance_metadata(hit.title, hit.url, hit.content, query_list, provider="Firecrawl"),
            )
            for hit in result.hits
        ]
        return ExternalSourceLibrary(
            provider="firecrawl",
            configured=result.configured,
            searches_attempted=result.searches_attempted,
            sources=sources,
            error=result.error,
            metadata={"tool_name": result.tool_name, "queries": query_list},
        )


class TavilyExternalSourceProvider(ExternalSourceProvider):
    def __init__(self, config: Optional[ExternalSourceProviderConfig] = None) -> None:
        super().__init__(config)
        self.api_key = _first_env(("TAVILY_API_KEY",))
        self.search_url = os.getenv("TAVILY_SEARCH_URL", DEFAULT_TAVILY_SEARCH_URL).strip() or DEFAULT_TAVILY_SEARCH_URL

    def research(self, queries: Iterable[str]) -> ExternalSourceLibrary:
        query_list = [query for query in queries if query and query.strip()]
        if not self.config.enabled or not self.api_key:
            return ExternalSourceLibrary(
                provider="tavily",
                configured=False,
                searches_attempted=0,
                error=self.config.reason or "Set TAVILY_API_KEY to enable Tavily source research.",
                metadata={"requested_queries": len(query_list)},
            )
        if not query_list:
            return ExternalSourceLibrary(
                provider="tavily",
                configured=True,
                searches_attempted=0,
                error="No research queries were provided.",
            )

        sources: list[ExternalSourceRecord] = []
        answer_parts: list[str] = []
        request_ids: list[str] = []
        searches_attempted = 0
        try:
            for query in query_list:
                searches_attempted += 1
                payload = {
                    "query": query,
                    "search_depth": self.config.search_depth or "basic",
                    "max_results": self.config.search_limit,
                    "include_answer": self.config.include_answer,
                    "include_raw_content": self.config.include_raw_content,
                    "include_images": False,
                    "include_image_descriptions": False,
                    "include_favicon": False,
                    "include_usage": True,
                }
                data = json.dumps(payload).encode("utf-8")
                request = urllib.request.Request(
                    self.search_url,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    response_payload = json.loads(response.read().decode("utf-8"))

                if isinstance(response_payload.get("answer"), str) and response_payload["answer"].strip():
                    answer_parts.append(response_payload["answer"].strip())
                if isinstance(response_payload.get("request_id"), str):
                    request_ids.append(response_payload["request_id"])
                for result in response_payload.get("results") or []:
                    if not isinstance(result, dict):
                        continue
                    title = str(result.get("title") or "")
                    url = str(result.get("url") or "")
                    content = str(result.get("raw_content") or result.get("content") or "")
                    sources.append(
                        ExternalSourceRecord(
                            title=title,
                            url=url,
                            content=content,
                            provider="tavily",
                            source_type="web",
                            score=result.get("score") if isinstance(result.get("score"), (int, float)) else None,
                            metadata=source_relevance_metadata(title, url, content, query_list, provider="Tavily"),
                        )
                    )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            return ExternalSourceLibrary(
                provider="tavily",
                configured=True,
                searches_attempted=searches_attempted,
                sources=_dedupe_sources(sources, max_items=self.config.search_limit * 4),
                answer="\n\n".join(answer_parts) or None,
                error=f"Tavily search failed with HTTP {exc.code}: {error_body[:500]}",
                metadata={"queries": query_list, "request_ids": request_ids},
            )
        except Exception as exc:
            return ExternalSourceLibrary(
                provider="tavily",
                configured=True,
                searches_attempted=searches_attempted,
                sources=_dedupe_sources(sources, max_items=self.config.search_limit * 4),
                answer="\n\n".join(answer_parts) or None,
                error=str(exc),
                metadata={"queries": query_list, "request_ids": request_ids},
            )

        return ExternalSourceLibrary(
            provider="tavily",
            configured=True,
            searches_attempted=searches_attempted,
            sources=_dedupe_sources(sources, max_items=self.config.search_limit * 4),
            answer="\n\n".join(answer_parts) or None,
            metadata={"queries": query_list, "request_ids": request_ids},
        )


SOURCE_STOP_WORDS = {
    "and",
    "are",
    "bom",
    "for",
    "from",
    "how",
    "make",
    "maker",
    "module",
    "open",
    "project",
    "reference",
    "search",
    "source",
    "the",
    "this",
    "with",
}


def source_domain(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc.lower().removeprefix("www.")


def _query_terms(queries: Iterable[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for query in queries:
        for term in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9+.-]{2,}", query.lower()):
            if term in SOURCE_STOP_WORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def source_relevance_metadata(title: str, url: str, content: str, queries: Iterable[str], *, provider: str = "external source") -> dict[str, Any]:
    haystack = f"{title}\n{url}\n{content}".lower()
    terms = _query_terms(queries)
    matched_terms = [term for term in terms if term in haystack][:8]
    domain = source_domain(url)
    if matched_terms:
        reason = f"Matched search terms: {', '.join(matched_terms[:5])}."
    elif title or content:
        reason = f"Returned by {provider} for the active hardware research query and included source text for review."
    else:
        reason = f"Returned by {provider} for the active hardware research query."
    if domain:
        reason = f"{reason} Source domain: {domain}."
    return {
        "domain": domain,
        "relevance_reason": reason,
        "matched_query_terms": matched_terms,
    }


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
    if resolved.provider == "tavily":
        return TavilyExternalSourceProvider(resolved)
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
    "TavilyExternalSourceProvider",
    "build_external_source_provider",
]
