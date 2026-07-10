from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from typing import Iterator

from blueprint_core.agents.firecrawl_mcp import FirecrawlResearchResult, FirecrawlSearchHit
from blueprint_core.external_sources import (
    ExternalSourceLibrary,
    ExternalSourceProviderConfig,
    ExternalSourceRecord,
    FirecrawlExternalSourceProvider,
    build_external_source_provider,
)
from blueprint_core.job_source_usage import infer_source_usage, normalize_source_usage


EXTERNAL_SOURCE_ENV_KEYS = {
    "EXTERNAL_SOURCE_DISABLED",
    "EXTERNAL_SOURCE_PROVIDER",
    "EXTERNAL_SOURCE_SEARCH_LIMIT",
    "EXTERNAL_SOURCE_TIMEOUT_SECONDS",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_MCP_COMMAND",
    "TAVILY_API_KEY",
    "TAVILY_INCLUDE_ANSWER",
    "TAVILY_INCLUDE_RAW_CONTENT",
    "TAVILY_SEARCH_DEPTH",
    "TAVILY_SEARCH_LIMIT",
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
    def test_auto_provider_selects_firecrawl_even_when_tavily_key_is_present(self) -> None:
        with isolated_external_source_env(FIRECRAWL_API_KEY="fc_test", TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider()

        self.assertIsInstance(provider, FirecrawlExternalSourceProvider)
        self.assertEqual("firecrawl", provider.provider_name)
        self.assertTrue(provider.config.enabled)

    def test_legacy_tavily_provider_override_resolves_to_firecrawl(self) -> None:
        with isolated_external_source_env(FIRECRAWL_API_KEY="fc_test", EXTERNAL_SOURCE_PROVIDER="firecrawl", TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider(provider="tavily")

        self.assertIsInstance(provider, FirecrawlExternalSourceProvider)
        self.assertEqual("firecrawl", provider.provider_name)

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
            action="blueprint.generate_project",
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
