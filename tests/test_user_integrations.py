from __future__ import annotations

import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from blueprint_core import user_integrations
from blueprint_core.user_integrations import (
    UserIntegrationStore,
    apply_user_integrations_to_environment,
    integration_status_payload,
)


TEST_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_STREAM_MODEL",
    "BASETEN_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
)


@contextmanager
def isolated_integration_env() -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in TEST_ENV_KEYS}
    user_integrations._APPLIED_ENV_VALUES.clear()
    user_integrations._ORIGINAL_ENV_VALUES.clear()
    try:
        for key in TEST_ENV_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key in TEST_ENV_KEYS:
            os.environ.pop(key, None)
            if old_values[key] is not None:
                os.environ[key] = old_values[key] or ""
        user_integrations._APPLIED_ENV_VALUES.clear()
        user_integrations._ORIGINAL_ENV_VALUES.clear()


def integration_by_id(payload: dict[str, object], integration_id: str) -> dict[str, object]:
    integrations = payload["integrations"]
    assert isinstance(integrations, list)
    for integration in integrations:
        assert isinstance(integration, dict)
        if integration["id"] == integration_id:
            return integration
    raise AssertionError(f"integration not found: {integration_id}")


def field_by_id(integration: dict[str, object], field_id: str) -> dict[str, object]:
    fields = integration["fields"]
    assert isinstance(fields, list)
    for field in fields:
        assert isinstance(field, dict)
        if field["id"] == field_id:
            return field
    raise AssertionError(f"field not found: {field_id}")


class UserIntegrationTests(unittest.TestCase):
    def test_saved_secret_is_masked_and_nonsecret_value_is_visible(self) -> None:
        with isolated_integration_env(), tempfile.TemporaryDirectory() as tmpdir:
            store = UserIntegrationStore(Path(tmpdir) / "integrations.json")
            store.update_integration(
                "openai",
                field_values={
                    "api_key": "sk-testsecret123456",
                    "model": "gpt-5.5",
                },
            )

            payload = integration_status_payload(store)
            openai = integration_by_id(payload, "openai")
            api_key = field_by_id(openai, "api_key")
            model = field_by_id(openai, "model")

            self.assertTrue(api_key["configured"])
            self.assertEqual("saved", api_key["source"])
            self.assertEqual("sk-t...3456", api_key["masked_value"])
            self.assertIsNone(api_key["value"])
            self.assertEqual("gpt-5.5", model["value"])
            self.assertEqual("saved", model["source"])
            self.assertNotIn("sk-testsecret123456", str(payload))
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)

    def test_apply_sets_runtime_environment_and_restores_previous_env_values(self) -> None:
        with isolated_integration_env(), tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENAI_API_KEY"] = "sk-env-original"
            store = UserIntegrationStore(Path(tmpdir) / "integrations.json")
            store.update_integration(
                "openai",
                field_values={
                    "api_key": "sk-user-managed",
                    "model": "gpt-5.5",
                },
            )

            apply_user_integrations_to_environment(store)
            self.assertEqual("sk-user-managed", os.environ["OPENAI_API_KEY"])
            self.assertEqual("sk-user-managed", os.environ["OPENAI_IMAGE_API_KEY"])
            self.assertEqual("gpt-5.5", os.environ["OPENAI_MODEL"])
            self.assertEqual("gpt-5.5", os.environ["OPENAI_STREAM_MODEL"])

            store.clear_integration("openai")
            apply_user_integrations_to_environment(store)
            self.assertEqual("sk-env-original", os.environ["OPENAI_API_KEY"])
            self.assertNotIn("OPENAI_IMAGE_API_KEY", os.environ)
            self.assertNotIn("OPENAI_MODEL", os.environ)
            self.assertNotIn("OPENAI_STREAM_MODEL", os.environ)

    def test_disabled_integration_is_saved_but_not_applied(self) -> None:
        with isolated_integration_env(), tempfile.TemporaryDirectory() as tmpdir:
            store = UserIntegrationStore(Path(tmpdir) / "integrations.json")
            store.update_integration(
                "baseten",
                enabled=False,
                field_values={"api_key": "baseten-secret"},
            )

            payload = integration_status_payload(store)
            baseten = integration_by_id(payload, "baseten")

            self.assertFalse(baseten["enabled"])
            self.assertTrue(baseten["configured"])
            self.assertNotIn("BASETEN_API_KEY", os.environ)

    def test_runtime_defaults_apply_to_llm_selector(self) -> None:
        with isolated_integration_env(), tempfile.TemporaryDirectory() as tmpdir:
            store = UserIntegrationStore(Path(tmpdir) / "integrations.json")
            store.update_integration(
                "runtime",
                field_values={
                    "llm_provider": "gmi",
                    "llm_model": "anthropic/claude-fable-5",
                },
            )

            apply_user_integrations_to_environment(store)

            self.assertEqual("gmi", os.environ["LLM_PROVIDER"])
            self.assertEqual("anthropic/claude-fable-5", os.environ["LLM_MODEL"])


if __name__ == "__main__":
    unittest.main()
