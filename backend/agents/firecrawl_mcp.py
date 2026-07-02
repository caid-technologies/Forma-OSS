from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_FIRECRAWL_MCP_COMMAND = "npx -y firecrawl-mcp"


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


@dataclass(frozen=True)
class FirecrawlMCPConfig:
    enabled: bool
    command: List[str] = field(default_factory=list)
    timeout_seconds: float = 45.0
    search_limit: int = 3
    reason: Optional[str] = None

    @classmethod
    def from_env(cls) -> "FirecrawlMCPConfig":
        if _env_bool("FIRECRAWL_MCP_DISABLED", False):
            return cls(enabled=False, reason="FIRECRAWL_MCP_DISABLED is true.")

        configured_command = os.getenv("FIRECRAWL_MCP_COMMAND")
        api_key = os.getenv("FIRECRAWL_API_KEY")
        if configured_command:
            command = shlex.split(configured_command)
        elif api_key:
            command = shlex.split(DEFAULT_FIRECRAWL_MCP_COMMAND)
        else:
            return cls(
                enabled=False,
                reason="Set FIRECRAWL_API_KEY or FIRECRAWL_MCP_COMMAND to enable Firecrawl MCP research.",
            )

        if not command:
            return cls(enabled=False, reason="FIRECRAWL_MCP_COMMAND resolved to an empty command.")

        timeout = float(_env_int("FIRECRAWL_MCP_TIMEOUT_SECONDS", 45, 5, 180))
        search_limit = _env_int("FIRECRAWL_SEARCH_LIMIT", 3, 1, 8)
        return cls(enabled=True, command=command, timeout_seconds=timeout, search_limit=search_limit)


@dataclass
class FirecrawlSearchHit:
    title: str = ""
    url: str = ""
    content: str = ""


@dataclass
class FirecrawlResearchResult:
    configured: bool
    searches_attempted: int = 0
    hits: List[FirecrawlSearchHit] = field(default_factory=list)
    tool_name: Optional[str] = None
    error: Optional[str] = None

    def as_prompt_context(self, max_chars: int = 14000) -> str:
        if not self.hits:
            return "No Firecrawl MCP search results were available."

        blocks = []
        remaining = max_chars
        for index, hit in enumerate(self.hits, start=1):
            text = (hit.content or "").strip()
            if not text:
                text = hit.title or hit.url
            block = f"[{index}] {hit.title or 'Untitled source'}\nURL: {hit.url or 'unknown'}\n{text}"
            if len(block) > remaining:
                block = block[: max(0, remaining - 3)] + "..."
            blocks.append(block)
            remaining -= len(block)
            if remaining <= 0:
                break
        return "\n\n".join(blocks)

    def metadata(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "searches_attempted": self.searches_attempted,
            "hits": [
                {"title": hit.title, "url": hit.url, "content_preview": hit.content[:360]}
                for hit in self.hits[:12]
            ],
            "tool_name": self.tool_name,
            "error": self.error,
        }


class _MCPStdioSession:
    def __init__(self, command: List[str], timeout_seconds: float):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._stderr_lines: "queue.Queue[str]" = queue.Queue()
        self.process: Optional[subprocess.Popen[bytes]] = None

    def __enter__(self) -> "_MCPStdioSession":
        env = os.environ.copy()
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
            env=env,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._initialize()
        return self

    def __exit__(self, *_: Any) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while True:
            headers: Dict[str, str] = {}
            line = self.process.stdout.readline()
            if not line:
                return
            while line and line.strip():
                try:
                    key, value = line.decode("utf-8", errors="replace").split(":", 1)
                    headers[key.strip().lower()] = value.strip()
                except ValueError:
                    pass
                line = self.process.stdout.readline()

            length = int(headers.get("content-length", "0") or "0")
            if length <= 0:
                continue

            body = self.process.stdout.read(length)
            if not body:
                return
            try:
                self._responses.put(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError:
                continue

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for raw in self.process.stderr:
            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                self._stderr_lines.put(text)

    def _send(self, payload: Dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + raw)
        self.process.stdin.flush()

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                message = self._responses.get(timeout=0.25)
            except queue.Empty:
                if self.process and self.process.poll() is not None:
                    break
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], sort_keys=True))
                return message.get("result") or {}
        raise TimeoutError(f"MCP request timed out: {method}")

    def _initialize(self) -> None:
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "blueprint-oss", "version": "1.0.0"},
            },
        )
        self.notify("notifications/initialized")

    def stderr_preview(self, limit: int = 6) -> str:
        lines = []
        while len(lines) < limit:
            try:
                lines.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "\n".join(lines)


def _stringify_tool_content(result: Dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif "json" in item:
                    parts.append(json.dumps(item["json"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return json.dumps(result, sort_keys=True)


def _flatten_firecrawl_hits(value: Any) -> List[FirecrawlSearchHit]:
    if isinstance(value, str):
        try:
            return _flatten_firecrawl_hits(json.loads(value))
        except json.JSONDecodeError:
            return [FirecrawlSearchHit(content=value)]

    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            return _flatten_firecrawl_hits(value["data"])
        if isinstance(value.get("results"), list):
            return _flatten_firecrawl_hits(value["results"])
        if any(key in value for key in ("url", "title", "markdown", "content", "description")):
            content = value.get("markdown") or value.get("content") or value.get("description") or value.get("text") or ""
            return [
                FirecrawlSearchHit(
                    title=str(value.get("title") or value.get("name") or ""),
                    url=str(value.get("url") or value.get("source") or ""),
                    content=str(content),
                )
            ]
        return [FirecrawlSearchHit(content=json.dumps(value, sort_keys=True))]

    if isinstance(value, list):
        hits: List[FirecrawlSearchHit] = []
        for item in value:
            hits.extend(_flatten_firecrawl_hits(item))
        return hits

    return []


class FirecrawlMCPResearchClient:
    def __init__(self, config: Optional[FirecrawlMCPConfig] = None):
        self.config = config or FirecrawlMCPConfig.from_env()

    def research(self, queries: Iterable[str]) -> FirecrawlResearchResult:
        if not self.config.enabled:
            return FirecrawlResearchResult(configured=False, error=self.config.reason)

        query_list = [query.strip() for query in queries if query and query.strip()]
        if not query_list:
            return FirecrawlResearchResult(configured=True, error="No research queries were provided.")

        try:
            with _MCPStdioSession(self.config.command, self.config.timeout_seconds) as session:
                tools_result = session.request("tools/list")
                tools = tools_result.get("tools") or []
                tool_names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
                search_tool = self._select_search_tool(tool_names)
                if not search_tool:
                    return FirecrawlResearchResult(
                        configured=True,
                        error=f"No Firecrawl search tool found. Available tools: {', '.join(tool_names) or 'none'}",
                    )

                hits: List[FirecrawlSearchHit] = []
                searches_attempted = 0
                for query in query_list:
                    searches_attempted += 1
                    result = self._call_search_tool(session, search_tool, query)
                    hits.extend(_flatten_firecrawl_hits(_stringify_tool_content(result)))

                deduped = self._dedupe_hits(hits)
                return FirecrawlResearchResult(
                    configured=True,
                    searches_attempted=searches_attempted,
                    hits=deduped,
                    tool_name=search_tool,
                )
        except Exception as exc:
            return FirecrawlResearchResult(configured=True, error=str(exc))

    def _select_search_tool(self, tool_names: List[str]) -> Optional[str]:
        preferred = [
            "firecrawl_search",
            "firecrawl.search",
            "search",
            "firecrawl_web_search",
        ]
        for name in preferred:
            if name in tool_names:
                return name
        for name in tool_names:
            if name and "search" in name:
                return name
        return None

    def _call_search_tool(self, session: _MCPStdioSession, tool_name: str, query: str) -> Dict[str, Any]:
        argument_variants = [
            {
                "query": query,
                "limit": self.config.search_limit,
                "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
            },
            {"query": query, "limit": self.config.search_limit},
            {"query": query},
        ]
        last_error: Optional[Exception] = None
        for arguments in argument_variants:
            try:
                return session.request("tools/call", {"name": tool_name, "arguments": arguments})
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Firecrawl search failed for query {query!r}: {last_error}")

    def _dedupe_hits(self, hits: List[FirecrawlSearchHit]) -> List[FirecrawlSearchHit]:
        seen = set()
        deduped = []
        for hit in hits:
            key = (hit.url or hit.title or hit.content[:80]).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped[: self.config.search_limit * 4]
