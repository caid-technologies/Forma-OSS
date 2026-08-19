from __future__ import annotations

import json
import os
import sys
import types
import unittest
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from typing import Iterator

from forma_core.agents.firecrawl_mcp import (
    FirecrawlResearchResult,
    FirecrawlSearchHit,
    _MCPStdioSession,
    _flatten_firecrawl_hits,
)
from forma_core.external_sources import (
    ExternalSourceLibrary,
    ExternalSourceProviderConfig,
    ExternalSourceRecord,
    FirecrawlExternalSourceProvider,
    TavilyExternalSourceProvider,
    build_external_source_provider,
)
from forma_core.jobs.source_usage import infer_source_usage, normalize_source_usage


EXTERNAL_SOURCE_ENV_KEYS = {
    "EXTERNAL_SOURCE_DISABLED",
    "EXTERNAL_SOURCE_PROVIDER",
    "EXTERNAL_SOURCE_SEARCH_LIMIT",
    "EXTERNAL_SOURCE_TIMEOUT_SECONDS",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_MCP_COMMAND",
    "TAVILY_API_KEY",
    "TAVILY_CRAWL_EXTRACT_DEPTH",
    "TAVILY_CRAWL_LIMIT",
    "TAVILY_CRAWL_MAX_DEPTH",
    "TAVILY_INCLUDE_ANSWER",
    "TAVILY_INCLUDE_RAW_CONTENT",
    "TAVILY_RESEARCH_MODEL",
    "TAVILY_RESEARCH_OUTPUT_LENGTH",
    "TAVILY_SEARCH_DEPTH",
    "TAVILY_SEARCH_LIMIT",
    "TAVILY_TIMEOUT_SECONDS",
    "WEB_RESEARCH_DISABLED",
    "WEB_RESEARCH_PROVIDER",
}


@contextmanager
def isolated_external_source_env(**overrides: str) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in EXTERNAL_SOURCE_ENV_KEYS}
    try:
        for key in EXTERNAL_SOURCE_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        yield
    finally:
        for key in EXTERNAL_SOURCE_ENV_KEYS:
            os.environ.pop(key, None)
            if old_values[key] is not None:
                os.environ[key] = old_values[key] or ""


class FakeTavilyClient:
    calls: list[dict] = []
    crawl_calls: list[dict] = []

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "answer": "Use a low-voltage MCU and a sourced sensor module.",
            "results": [
                {
                    "title": "Sensor module datasheet",
                    "url": "https://example.com/sensor",
                    "content": "A maker sensor module with I2C pins.",
                    "score": 0.91,
                }
            ],
        }

    def crawl(self, **kwargs):
        self.crawl_calls.append(kwargs)
        return {
            "results": [
                {
                    "url": kwargs.get("url") or "https://example.com/docs",
                    "raw_content": "API search, crawl, and research endpoints.",
                }
            ]
        }


class FakeFirecrawlClient:
    queries: list[list[str]] = []

    def research(self, queries):
        query_list = list(queries)
        self.queries.append(query_list)
        return FirecrawlResearchResult(
            configured=True,
            searches_attempted=len(query_list),
            hits=[
                FirecrawlSearchHit(
                    title="Sensor module datasheet",
                    url="https://example.com/sensor",
                    content="A maker sensor module with I2C pins.",
                )
            ],
            tool_name="firecrawl_search",
        )


class ExternalSourceTests(unittest.TestCase):
    def test_mcp_stdio_sends_newline_delimited_json(self) -> None:
        stdin = BytesIO()
        session = _MCPStdioSession(["firecrawl-mcp"], timeout_seconds=1)
        session.process = SimpleNamespace(stdin=stdin)  # type: ignore[assignment]

        session._send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        payload = stdin.getvalue()
        self.assertTrue(payload.endswith(b"\n"))
        self.assertNotIn(b"Content-Length", payload)
        self.assertEqual("tools/list", json.loads(payload)["method"])

    def test_mcp_stdio_reads_newline_delimited_json(self) -> None:
        stdout = BytesIO(b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
        session = _MCPStdioSession(["firecrawl-mcp"], timeout_seconds=1)
        session.process = SimpleNamespace(stdout=stdout)  # type: ignore[assignment]

        session._read_stdout()

        self.assertEqual(1, session._responses.get_nowait()["id"])

    def test_firecrawl_flattens_nested_web_results(self) -> None:
        hits = _flatten_firecrawl_hits(
            {
                "success": True,
                "data": {
                    "web": [
                        {
                            "title": "Sensor datasheet",
                            "url": "https://example.com/datasheet",
                            "description": "Electrical specifications.",
                            "markdown": "# Sensor\nAdditional details.",
                        }
                    ]
                },
            }
        )

        self.assertEqual(1, len(hits))
        self.assertEqual("Sensor datasheet", hits[0].title)
        self.assertIn("Electrical specifications.", hits[0].content)
        self.assertIn("Additional details.", hits[0].content)

    def test_firecrawl_prompt_context_is_bounded(self) -> None:
        result = FirecrawlResearchResult(
            configured=True,
            searches_attempted=2,
            hits=[
                FirecrawlSearchHit(
                    title=f"Source {index}",
                    url=f"https://example.com/{index}",
                    content="Evidence " * 100,
                )
                for index in range(2)
            ],
        )

        context = result.as_prompt_context(max_chars=240)

        self.assertLessEqual(len(context), 240)
        self.assertIn("Source 0", context)

    def test_auto_provider_selects_firecrawl_even_when_tavily_key_is_present(self) -> None:
        with isolated_external_source_env(FIRECRAWL_API_KEY="fc_test", TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider()

        self.assertIsInstance(provider, FirecrawlExternalSourceProvider)
        self.assertEqual("firecrawl", provider.provider_name)
        self.assertTrue(provider.config.enabled)

    def test_tavily_provider_override_uses_tavily(self) -> None:
        with isolated_external_source_env(FIRECRAWL_API_KEY="fc_test", EXTERNAL_SOURCE_PROVIDER="firecrawl", TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider(provider="tavily")

        self.assertIsInstance(provider, TavilyExternalSourceProvider)
        self.assertEqual("tavily", provider.provider_name)

    def test_tavily_provider_maps_search_results_to_source_objects(self) -> None:
        fake_module = types.ModuleType("tavily")
        fake_module.TavilyClient = FakeTavilyClient
        previous_module = sys.modules.get("tavily")
        sys.modules["tavily"] = fake_module
        FakeTavilyClient.calls.clear()
        FakeTavilyClient.crawl_calls.clear()

        try:
            with isolated_external_source_env(TAVILY_API_KEY="tvly_test", TAVILY_SEARCH_LIMIT="1"):
                provider = TavilyExternalSourceProvider(ExternalSourceProviderConfig.from_env(provider_override="tavily"))
                library = provider.research(["blue sensor module"])
        finally:
            if previous_module is None:
                sys.modules.pop("tavily", None)
            else:
                sys.modules["tavily"] = previous_module

        self.assertTrue(library.configured)
        self.assertEqual("tavily", library.provider)
        self.assertEqual(1, library.searches_attempted)
        self.assertEqual("Sensor module datasheet", library.sources[0].title)
        self.assertEqual("https://example.com/sensor", library.sources[0].url)
        self.assertEqual(0.91, library.sources[0].score)
        self.assertEqual(1, FakeTavilyClient.calls[0]["max_results"])
        self.assertEqual([], FakeTavilyClient.crawl_calls)

    def test_tavily_provider_crawls_url_queries(self) -> None:
        fake_module = types.ModuleType("tavily")
        fake_module.TavilyClient = FakeTavilyClient
        previous_module = sys.modules.get("tavily")
        sys.modules["tavily"] = fake_module
        FakeTavilyClient.calls.clear()
        FakeTavilyClient.crawl_calls.clear()

        try:
            with isolated_external_source_env(TAVILY_API_KEY="tvly_test", TAVILY_CRAWL_MAX_DEPTH="2", TAVILY_CRAWL_LIMIT="8"):
                provider = TavilyExternalSourceProvider(ExternalSourceProviderConfig.from_env(provider_override="tavily"))
                library = provider.research(["https://docs.tavily.com"])
        finally:
            if previous_module is None:
                sys.modules.pop("tavily", None)
            else:
                sys.modules["tavily"] = previous_module

        self.assertTrue(library.configured)
        self.assertEqual("crawl", library.sources[0].source_type)
        self.assertEqual("https://docs.tavily.com", FakeTavilyClient.crawl_calls[0]["url"])
        self.assertEqual(2, FakeTavilyClient.crawl_calls[0]["max_depth"])
        self.assertEqual(8, FakeTavilyClient.crawl_calls[0]["limit"])
        self.assertEqual([], FakeTavilyClient.calls)

    def test_firecrawl_provider_maps_search_results_to_source_objects(self) -> None:
        with isolated_external_source_env(FIRECRAWL_API_KEY="fc_test", FIRECRAWL_SEARCH_LIMIT="1"):
            provider = FirecrawlExternalSourceProvider(ExternalSourceProviderConfig.from_env())
            fake_client = FakeFirecrawlClient()
            provider.client = fake_client
            library = provider.research(["blue sensor module"])

        self.assertTrue(library.configured)
        self.assertEqual("firecrawl", library.provider)
        self.assertEqual(1, library.searches_attempted)
        self.assertEqual("Sensor module datasheet", library.sources[0].title)
        self.assertEqual("https://example.com/sensor", library.sources[0].url)
        self.assertIsNone(library.sources[0].score)
        self.assertEqual(["blue sensor module"], fake_client.queries[0])

    def test_external_source_library_builds_prompt_context(self) -> None:
        library = ExternalSourceLibrary(
            provider="firecrawl",
            configured=True,
            answer="Short answer.",
            sources=[
                ExternalSourceRecord(
                    title="Example",
                    url="https://example.com",
                    content="Useful sourced text.",
                    provider="firecrawl",
                )
            ],
        )

        context = library.as_prompt_context()

        self.assertIn("Short answer.", context)
        self.assertIn("Provider: firecrawl", context)
        self.assertIn("Useful sourced text.", context)

    def test_external_source_library_prompt_context_is_bounded(self) -> None:
        library = ExternalSourceLibrary(
            provider="firecrawl",
            configured=True,
            answer="Summary " * 100,
            sources=[
                ExternalSourceRecord(
                    title="Example",
                    url="https://example.com",
                    content="Evidence " * 100,
                    provider="firecrawl",
                )
            ],
        )

        self.assertLessEqual(len(library.as_prompt_context(max_chars=240)), 240)

    def test_source_usage_records_tavily_provider(self) -> None:
        usage = infer_source_usage(
            result={
                "project_ir": {
                    "assembly_metadata": {
                        "workflow": "web_research",
                        "pipeline": "Tavily external source research + sourced hardware agents",
                        "external_research": {"provider": "tavily"},
                    }
                }
            }
        )

        self.assertTrue(usage["web_research"])
        self.assertTrue(usage["external_sources"])
        self.assertTrue(usage["tavily"])
        self.assertFalse(usage["firecrawl"])
        self.assertIn("Tavily", usage["source_labels"])

    def test_source_usage_reads_requested_external_provider(self) -> None:
        usage = infer_source_usage(
            action="forma.generate_project",
            payload={"workflow": "web_research", "external_source_provider": "firecrawl"},
        )

        self.assertTrue(usage["web_research"])
        self.assertEqual("firecrawl", usage["external_provider"])
        self.assertTrue(usage["firecrawl"])
        self.assertFalse(usage["tavily"])
        self.assertIn("Firecrawl", usage["source_labels"])

    def test_normalize_source_usage_accepts_tavily_flag(self) -> None:
        usage = normalize_source_usage({"workflow": "web_research", "tavily": True})

        self.assertTrue(usage["tavily"])
        self.assertEqual("tavily", usage["external_provider"])


if __name__ == "__main__":
    unittest.main()
