from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from blueprint_core.config import AppConfig, config


REPO_ROOT = Path(__file__).resolve().parents[2]


class AppConfigTests(unittest.TestCase):
    def test_reads_and_parses_environment_values(self) -> None:
        environment = {
            "TEXT_SETTING": " value ",
            "EMPTY_SETTING": "  ",
            "TRUE_SETTING": "yes",
            "FALSE_SETTING": "off",
            "INTEGER_SETTING": "42",
            "NUMBER_SETTING": "1.25",
        }

        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(" value ", config.get("TEXT_SETTING"))
            self.assertEqual("value", config.optional("TEXT_SETTING"))
            self.assertIsNone(config.optional("EMPTY_SETTING"))
            self.assertEqual("value", config.first(("MISSING_SETTING", "TEXT_SETTING")))
            self.assertTrue(config.is_set("EMPTY_SETTING"))
            self.assertTrue(config.boolean("TRUE_SETTING"))
            self.assertFalse(config.boolean("FALSE_SETTING", True))
            self.assertEqual(42, config.integer("INTEGER_SETTING", 0))
            self.assertEqual(1.25, config.number("NUMBER_SETTING", 0.0))
            self.assertEqual(environment, config.snapshot())

    def test_invalid_or_missing_typed_values_use_defaults(self) -> None:
        with patch.dict(os.environ, {"INVALID": "not-a-number"}, clear=True):
            self.assertEqual("fallback", config.get("MISSING", "fallback"))
            self.assertTrue(config.boolean("MISSING", True))
            self.assertEqual(7, config.integer("INVALID", 7))
            self.assertEqual(2.5, config.number("INVALID", 2.5))
            self.assertEqual("web_research", config.default_generation_workflow)

    def test_default_generation_workflow_is_configurable(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_DEFAULT_GENERATION_WORKFLOW": "default"}, clear=True):
            self.assertEqual("default", config.default_generation_workflow)

    def test_cloudflare_thinking_defaults_off_and_can_be_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(config.cloudflare_enable_thinking)
        with patch.dict(os.environ, {"CLOUDFLARE_ENABLE_THINKING": "true"}, clear=True):
            self.assertTrue(config.cloudflare_enable_thinking)

    def test_config_is_live_instead_of_an_import_time_snapshot(self) -> None:
        isolated = AppConfig()
        with patch.dict(os.environ, {"LIVE_SETTING": "before"}, clear=True):
            self.assertEqual("before", isolated.get("LIVE_SETTING"))
            isolated.set("LIVE_SETTING", "after")
            self.assertEqual("after", isolated.get("LIVE_SETTING"))

    def test_mutation_and_temporary_overrides_are_centralized(self) -> None:
        with patch.dict(os.environ, {"EXISTING": "before"}, clear=True):
            config.set_default("EXISTING", "ignored")
            config.set_default("DEFAULTED", "default")
            config.set("DIRECT", "value")
            config.update({"UPDATED": "value"})
            config.unset("DIRECT")

            self.assertEqual("before", config.get("EXISTING"))
            self.assertEqual("default", config.get("DEFAULTED"))
            self.assertIsNone(config.get("DIRECT"))
            self.assertEqual("value", config.get("UPDATED"))

            with config.override({"EXISTING": "during", "TEMPORARY": "value", "IGNORED": None}):
                self.assertEqual("during", config.get("EXISTING"))
                self.assertEqual("value", config.get("TEMPORARY"))
                self.assertIsNone(config.get("IGNORED"))

            self.assertEqual("before", config.get("EXISTING"))
            self.assertIsNone(config.get("TEMPORARY"))

            config.replace({"REPLACED": "yes"})
            self.assertEqual({"REPLACED": "yes"}, config.snapshot())

    def test_non_test_python_uses_only_the_config_environment_boundary(self) -> None:
        direct_access_patterns = ("os.getenv", "os.environ", "os.putenv", "os.unsetenv")
        violations: list[str] = []
        for relative_root in ("blueprint_core", "apps", "scripts", "examples", "evals"):
            for path in (REPO_ROOT / relative_root).rglob("*.py"):
                if any(part in {".venv", "node_modules", "tests", "test"} for part in path.parts):
                    continue
                if path == REPO_ROOT / "blueprint_core" / "config" / "environment.py":
                    continue
                source = path.read_text(encoding="utf-8")
                if any(pattern in source for pattern in direct_access_patterns):
                    violations.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
