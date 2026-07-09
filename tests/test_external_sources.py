from __future__ import annotations

import os
import sys
import types
import unittest
from contextlib import contextmanager
from typing import Iterator

from blueprint_core.external_sources import (
    ExternalSourceLibrary,
    ExternalSourceProviderConfig,
    ExternalSourceRecord,
    TavilyExternalSourceProvider,
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


class FakeTavilyClient:
    calls: list[dict] = []

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


class ExternalSourceTests(unittest.TestCase):
    def test_auto_provider_selects_tavily_when_key_is_present(self) -> None:
        with isolated_external_source_env(TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider()

        self.assertIsInstance(provider, TavilyExternalSourceProvider)
        self.assertEqual("tavily", provider.provider_name)
        self.assertTrue(provider.config.enabled)

    def test_explicit_provider_override_beats_env_default(self) -> None:
        with isolated_external_source_env(EXTERNAL_SOURCE_PROVIDER="firecrawl", TAVILY_API_KEY="tvly_test"):
            provider = build_external_source_provider(provider="tavily")

        self.assertIsInstance(provider, TavilyExternalSourceProvider)
        self.assertEqual("tavily", provider.provider_name)

    def test_tavily_provider_maps_search_results_to_source_objects(self) -> None:
        fake_module = types.ModuleType("tavily")
        fake_module.TavilyClient = FakeTavilyClient
        previous_module = sys.modules.get("tavily")
        sys.modules["tavily"] = fake_module
        FakeTavilyClient.calls.clear()

        try:
            with isolated_external_source_env(TAVILY_API_KEY="tvly_test", TAVILY_SEARCH_LIMIT="1"):
                provider = TavilyExternalSourceProvider(ExternalSourceProviderConfig.from_env())
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

    def test_external_source_library_builds_prompt_context(self) -> None:
        library = ExternalSourceLibrary(
            provider="tavily",
            configured=True,
            answer="Short answer.",
            sources=[
                ExternalSourceRecord(
                    title="Example",
                    url="https://example.com",
                    content="Useful sourced text.",
                    provider="tavily",
                )
            ],
        )

        context = library.as_prompt_context()

        self.assertIn("Short answer.", context)
        self.assertIn("Provider: tavily", context)
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
