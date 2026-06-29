import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_FIRECRAWL_MCP_URL = "https://mcp.firecrawl.dev/v2/mcp"
DEFAULT_FIRECRAWL_SEARCH_TOOL = "firecrawl_search"
DEFAULT_RESEARCH_QUERIES = 3
DEFAULT_RESULTS_PER_QUERY = 3
DEFAULT_MAX_CONTEXT_CHARS = 12000
DEFAULT_TIMEOUT_SECONDS = 25.0


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer %s=%r; using %s.", name, raw, default)
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        logger.warning("Invalid float %s=%r; using %.1f.", name, raw, default)
        return default


def _truncate(value: str, max_chars: int) -> str:
    normalized = re.sub(r"\n{3,}", "\n\n", value.strip())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max(0, max_chars - 32)].rstrip() + "\n...[truncated]"


def _safe_prompt_fragment(prompt: str, max_chars: int = 140) -> str:
    normalized = re.sub(r"\s+", " ", (prompt or "").strip())
    return normalized[:max_chars].strip() or "low-voltage electronics project"


def _build_research_queries(prompt: str) -> List[str]:
    subject = _safe_prompt_fragment(prompt)
    configured_query = _env("DESIGN_RESEARCH_QUERIES")
    if configured_query:
        return [
            query.strip()
            for query in configured_query.split("||")
            if query.strip()
        ][: _env_int("DESIGN_RESEARCH_MAX_QUERIES", DEFAULT_RESEARCH_QUERIES, minimum=1, maximum=6)]

    queries = [
        f"{subject} electronics project schematic BOM",
        f"{subject} Arduino ESP32 components wiring",
        f"{subject} enclosure CAD STL 3D print",
    ]
    return queries[: _env_int("DESIGN_RESEARCH_MAX_QUERIES", DEFAULT_RESEARCH_QUERIES, minimum=1, maximum=6)]


def _extract_urls(value: Any) -> List[str]:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    urls = re.findall(r"https?://[^\s)>\]\"']+", text)
    seen = set()
    deduped = []
    for url in urls:
        clean = url.rstrip(".,;:")
        if clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped[:12]


def _extract_component_mentions(text: str) -> List[str]:
    patterns = [
        r"\bESP32[-A-Z0-9]*\b",
        r"\bArduino\s+Nano\b",
        r"\bArduino\s+Uno\b",
        r"\bDHT22\b",
        r"\bDHT11\b",
        r"\bBMP280\b",
        r"\bBME280\b",
        r"\bMPU[- ]?6050\b",
        r"\bHC[- ]?SR04\b",
        r"\bSSD1306\b",
        r"\bSG90\b",
        r"\bTP4056\b",
        r"\bWS2812B\b",
        r"\bOLED\b",
        r"\bmicroSD\b",
        r"\bI2S\b",
    ]
    mentions: List[str] = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = re.sub(r"\s+", " ", match.group(0)).strip()
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            mentions.append(value)
    return mentions[:20]


@dataclass
class DesignResearchResult:
    enabled: bool
    provider: str = "firecrawl-mcp"
    queries: List[str] = field(default_factory=list)
    references: List[Dict[str, Any]] = field(default_factory=list)
    discovered_components: List[str] = field(default_factory=list)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    raw_context: str = ""
    errors: List[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.raw_context.strip())

    def to_prompt_context(self, max_chars: Optional[int] = None) -> str:
        if not self.available:
            if not self.enabled:
                return "Design research disabled or not configured."
            return "Design research ran but did not return usable context."

        budget = max_chars or _env_int("DESIGN_RESEARCH_MAX_CONTEXT_CHARS", DEFAULT_MAX_CONTEXT_CHARS, minimum=1000, maximum=50000)
        references = "\n".join(
            f"- {item.get('title') or 'Reference'}: {item.get('url')}"
            for item in self.references[:8]
            if item.get("url")
        )
        components = ", ".join(self.discovered_components[:20]) or "No component names extracted."
        body = f"""
Design research provider: {self.provider}
Search queries:
{chr(10).join(f"- {query}" for query in self.queries)}

Potential reference URLs:
{references or "- None extracted"}

Component names or modules mentioned in research:
{components}

Research excerpts:
{self.raw_context}
"""
        return _truncate(body, budget)

    def metadata(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "queries": self.queries,
            "reference_count": len(self.references),
            "references": self.references[:8],
            "discovered_components": self.discovered_components[:20],
            "logs": self.logs[:8],
            "errors": self.errors[:5],
        }


class FirecrawlMCPClient:
    """Small MCP-over-HTTP client for Firecrawl search calls."""

    def __init__(self) -> None:
        api_key = _env("FIRECRAWL_API_KEY") or _env("FIRECRAWL_OAUTH_TOKEN")
        configured_url = _env("FIRECRAWL_MCP_URL")
        self.url = configured_url or (DEFAULT_FIRECRAWL_MCP_URL if api_key else None)
        self.api_key = api_key
        self.search_tool = _env("FIRECRAWL_MCP_SEARCH_TOOL", DEFAULT_FIRECRAWL_SEARCH_TOOL) or DEFAULT_FIRECRAWL_SEARCH_TOOL
        self.timeout_seconds = _env_float("FIRECRAWL_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=1.0)
        self.initialize = _env_bool("FIRECRAWL_MCP_INITIALIZE", True)
        self.require_initialize = _env_bool("FIRECRAWL_MCP_REQUIRE_INITIALIZE", False)
        self._request_id = 0
        self._initialized = False
        self._session_id: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.url)

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            "provider": "firecrawl-mcp",
            "configured": self.is_configured,
            "enabled": design_research_enabled() and self.is_configured,
            "mcp_url_configured": bool(self.url),
            "using_default_mcp_url": self.url == DEFAULT_FIRECRAWL_MCP_URL,
            "api_key_configured": bool(self.api_key),
            "search_tool": self.search_tool,
            "timeout_seconds": self.timeout_seconds,
        }

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _parse_response(self, data: bytes, content_type: str) -> Dict[str, Any]:
        text = data.decode("utf-8", errors="replace").strip()
        if "text/event-stream" in content_type:
            for line in text.splitlines():
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if not payload or payload == "[DONE]":
                    continue
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
            raise RuntimeError("MCP server returned an event stream without a JSON data event.")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("MCP server returned a non-object JSON-RPC response.")
        return parsed

    def _json_rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.url:
            raise RuntimeError("FIRECRAWL_MCP_URL or FIRECRAWL_API_KEY is required for Firecrawl MCP research.")

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
                if session_id:
                    self._session_id = session_id
                parsed = self._parse_response(response.read(), response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"Firecrawl MCP HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Firecrawl MCP request failed: {exc}") from exc

        if "error" in parsed:
            raise RuntimeError(f"Firecrawl MCP {method} error: {parsed['error']}")
        return parsed.get("result", parsed)

    def _ensure_initialized(self) -> None:
        if not self.initialize or self._initialized:
            return
        try:
            self._json_rpc(
                "initialize",
                {
                    "protocolVersion": _env("MCP_PROTOCOL_VERSION", "2024-11-05"),
                    "capabilities": {},
                    "clientInfo": {"name": "blueprint-oss", "version": "1.0.0"},
                },
            )
            self._initialized = True
        except Exception:
            if self.require_initialize:
                raise
            logger.info("Firecrawl MCP initialize failed; trying tools/call without initialization.", exc_info=True)
            self._initialized = True

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self._ensure_initialized()
        return self._json_rpc("tools/call", {"name": name, "arguments": arguments})

    def search(self, query: str, limit: int) -> Any:
        return self.call_tool(
            self.search_tool,
            {
                "query": query,
                "limit": limit,
                "lang": _env("FIRECRAWL_SEARCH_LANG", "en"),
                "country": _env("FIRECRAWL_SEARCH_COUNTRY", "us"),
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
            },
        )


def _extract_mcp_text(value: Any) -> str:
    if isinstance(value, dict) and "structuredContent" in value:
        structured = value.get("structuredContent")
        content_text = _extract_mcp_text(value.get("content"))
        return "\n".join(part for part in [json.dumps(structured, indent=2, default=str), content_text] if part)

    if isinstance(value, dict) and "content" in value:
        return _extract_mcp_text(value["content"])

    if isinstance(value, list):
        chunks: List[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
                elif text is not None:
                    chunks.append(json.dumps(text, indent=2, default=str))
                else:
                    chunks.append(_extract_mcp_text(item))
            elif item is not None:
                chunks.append(str(item))
        return "\n\n".join(chunk for chunk in chunks if chunk)

    if isinstance(value, dict):
        return json.dumps(value, indent=2, default=str)

    return str(value or "")


def _source_excerpt(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("markdown", "content", "text", "description", "snippet"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return _truncate(candidate, 360)
    return ""


def _extract_source_records(value: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            url = item.get("url") or item.get("link") or item.get("sourceURL") or item.get("source_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                clean_url = url.rstrip(".,;:")
                if clean_url not in seen:
                    seen.add(clean_url)
                    records.append({
                        "url": clean_url,
                        "title": item.get("title") or item.get("name") or clean_url,
                        "description": item.get("description") or item.get("snippet") or None,
                        "excerpt": _source_excerpt(item),
                    })
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)

    if not records:
        text = _extract_mcp_text(value)
        for url in _extract_urls(text):
            if url in seen:
                continue
            seen.add(url)
            records.append({"url": url, "title": url, "description": None, "excerpt": ""})

    return records[:12]


def design_research_enabled() -> bool:
    return _env_bool("DESIGN_RESEARCH_ENABLED", False) or _env_bool("FIRECRAWL_DESIGN_RESEARCH_ENABLED", False)


def get_design_research_debug_config() -> Dict[str, Any]:
    client = FirecrawlMCPClient()
    return {
        **client.get_debug_config(),
        "max_queries": _env_int("DESIGN_RESEARCH_MAX_QUERIES", DEFAULT_RESEARCH_QUERIES, minimum=1, maximum=6),
        "results_per_query": _env_int("DESIGN_RESEARCH_RESULTS_PER_QUERY", DEFAULT_RESULTS_PER_QUERY, minimum=1, maximum=10),
        "max_context_chars": _env_int("DESIGN_RESEARCH_MAX_CONTEXT_CHARS", DEFAULT_MAX_CONTEXT_CHARS, minimum=1000, maximum=50000),
    }


def collect_design_research(prompt: str) -> DesignResearchResult:
    enabled = design_research_enabled()
    client = FirecrawlMCPClient()
    if not enabled or not client.is_configured:
        return DesignResearchResult(
            enabled=enabled and client.is_configured,
            errors=[] if not enabled else ["Firecrawl MCP is not configured."],
        )

    queries = _build_research_queries(prompt)
    per_query_limit = _env_int("DESIGN_RESEARCH_RESULTS_PER_QUERY", DEFAULT_RESULTS_PER_QUERY, minimum=1, maximum=10)
    max_context_chars = _env_int("DESIGN_RESEARCH_MAX_CONTEXT_CHARS", DEFAULT_MAX_CONTEXT_CHARS, minimum=1000, maximum=50000)

    excerpts: List[str] = []
    references: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []
    errors: List[str] = []

    for query in queries:
        try:
            result = client.search(query, per_query_limit)
        except Exception as exc:
            logger.warning("Firecrawl design research failed for query %r: %s", query, exc)
            error = f"{query}: {str(exc)[:500]}"
            errors.append(error)
            logs.append({
                "query": query,
                "status": "error",
                "message": str(exc)[:500],
                "sources": [],
                "discovered_components": [],
            })
            continue

        text = _extract_mcp_text(result)
        if text:
            excerpts.append(f"## Query: {query}\n{text}")

        sources = _extract_source_records(result)
        query_components = _extract_component_mentions(text)
        for source in sources:
            if any(item.get("url") == source.get("url") for item in references):
                continue
            references.append({
                "url": source.get("url"),
                "title": source.get("title") or query,
                "description": source.get("description"),
                "excerpt": source.get("excerpt"),
            })

        logs.append({
            "query": query,
            "status": "ok",
            "message": f"Found {len(sources)} source(s) and {len(query_components)} component/module hint(s).",
            "sources": sources[:5],
            "discovered_components": query_components,
            "excerpt": _truncate(text, 700) if text else "",
        })
        logger.info(
            "Firecrawl research query=%r sources=%s components=%s",
            query,
            [source.get("url") for source in sources[:5]],
            query_components,
        )

    raw_context = _truncate("\n\n".join(excerpts), max_context_chars)
    discovered_components = _extract_component_mentions(raw_context)
    return DesignResearchResult(
        enabled=True,
        queries=queries,
        references=references,
        discovered_components=discovered_components,
        logs=logs,
        raw_context=raw_context,
        errors=errors,
    )
