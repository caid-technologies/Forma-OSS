from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from backend.auth import UserApiKeyPrincipal, require_user_api_key
from backend.job_store import JOB_STORE
from backend.public_api import (
    developer_api_create_job,
    developer_api_job,
    developer_api_jobs,
    developer_api_llms,
    router as developer_api_router,
)
from blueprint_core import database
from blueprint_core.models import GenerateProjectRequest


def _route_client(principal: UserApiKeyPrincipal) -> TestClient:
    app = FastAPI()
    app.include_router(developer_api_router, prefix="/api")
    app.dependency_overrides[require_user_api_key] = lambda: principal
    return TestClient(app)


def _stub_generation_response(provider: str, model: str) -> dict:
    return {
        "project_ir": {
            "overview": {"title": f"{provider} route test"},
            "components": [],
            "nets": [],
            "assembly_metadata": {
                "runtime_provider": provider,
                "runtime_model": model,
            },
        },
        "schematic_svg": "<svg></svg>",
        "mermaid_diagram": "graph TD",
    }


class DeveloperApiSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database.init_db()
        JOB_STORE.init_db()

    def test_llm_listing_is_available_to_generation_keys(self) -> None:
        principal = UserApiKeyPrincipal(key_id="key_models", owner_user_id="user_models", scopes=["generate:project"])

        with patch.dict(os.environ, {"LLM_PROVIDER": "simulation"}, clear=False):
            payload = developer_api_llms(principal)

        self.assertIn("default", payload)
        self.assertIn("providers", payload)
        self.assertTrue(any(provider["id"] == "simulation" for provider in payload["providers"]))

    def test_job_listing_is_scoped_to_api_key_sender(self) -> None:
        principal = UserApiKeyPrincipal(key_id="key_jobs_unit", owner_user_id="user_jobs_unit", scopes=["read:job"])
        JOB_STORE.create_job(
            job_id="job_api_unit_visible",
            message_id="msg_unit_visible",
            correlation_id=None,
            action="blueprint.generate_project",
            sender="api:key_jobs_unit",
            recipient="blueprint",
            payload={
                "prompt": "visible",
                "workflow": "default",
                "owner_user_id": "user_jobs_unit",
                "api_key_id": "key_jobs_unit",
                "provider": "simulation",
                "model": "simulation",
            },
            server_owned=True,
            status="queued",
        )
        JOB_STORE.create_job(
            job_id="job_api_unit_hidden",
            message_id="msg_unit_hidden",
            correlation_id=None,
            action="blueprint.generate_project",
            sender="api:key_other",
            recipient="blueprint",
            payload={
                "prompt": "hidden",
                "workflow": "default",
                "owner_user_id": "user_other",
                "api_key_id": "key_other",
            },
            server_owned=True,
            status="queued",
        )

        payload = developer_api_jobs(job_status=None, limit=20, scope="key", include_progress=False, principal=principal)
        job_ids = {job["job_id"] for job in payload["jobs"]}

        self.assertIn("job_api_unit_visible", job_ids)
        self.assertNotIn("job_api_unit_hidden", job_ids)

    def test_job_detail_allows_same_owner_across_keys(self) -> None:
        principal = UserApiKeyPrincipal(key_id="key_owner_reader", owner_user_id="user_owner_reader", scopes=["read:job"])
        JOB_STORE.create_job(
            job_id="job_api_unit_owner_visible",
            message_id="msg_unit_owner_visible",
            correlation_id=None,
            action="blueprint.generate_project",
            sender="api:key_other_same_owner",
            recipient="blueprint",
            payload={
                "prompt": "owner visible",
                "workflow": "default",
                "owner_user_id": "user_owner_reader",
                "api_key_id": "key_other_same_owner",
            },
            server_owned=True,
            status="queued",
        )

        payload = developer_api_job("job_api_unit_owner_visible", principal=principal)

        self.assertEqual("job_api_unit_owner_visible", payload["job_id"])

    def test_async_job_creation_returns_pollable_status(self) -> None:
        principal = UserApiKeyPrincipal(key_id="key_async_unit", owner_user_id="user_async_unit", scopes=["generate:project"])
        request = GenerateProjectRequest(
            prompt="async blink tester",
            provider="simulation",
            model="simulation",
            client_job_id="job_api_unit_async",
        )

        payload = developer_api_create_job(request, BackgroundTasks(), principal)

        self.assertEqual("job_api_unit_async", payload["job_id"])
        self.assertEqual("queued", payload["status"])
        self.assertEqual("/api/v1/jobs/job_api_unit_async", payload["poll_url"])

    def test_async_job_routes_run_and_poll_real_simulation_pipeline(self) -> None:
        principal = UserApiKeyPrincipal(
            key_id="key_simulation_route",
            owner_user_id="user_simulation_route",
            scopes=["generate:project", "read:job"],
        )
        client = _route_client(principal)

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "simulation",
                "LLM_MODEL": "simulation",
                "LLM_ALLOWED_PROVIDERS": "simulation",
                "IMAGE_PROVIDER": "none",
                "IMAGE_OUTPUT_ENABLED": "false",
            },
            clear=False,
        ):
            create_response = client.post(
                "/api/v1/jobs",
                json={
                    "prompt": "A simulated USB-powered LED continuity tester",
                    "workflow": "default",
                    "provider": "simulation",
                    "model": "simulation",
                    "generate_image": False,
                },
            )

        self.assertEqual(202, create_response.status_code, create_response.text)
        created = create_response.json()
        self.assertEqual("queued", created["status"])
        self.assertEqual(f"/api/v1/jobs/{created['job_id']}", created["poll_url"])

        poll_response = client.get(created["poll_url"])
        self.assertEqual(200, poll_response.status_code, poll_response.text)
        job = poll_response.json()
        self.assertEqual("succeeded", job["status"])
        self.assertEqual("simulation", job["provider"])
        self.assertEqual("simulation", job["model"])
        self.assertIsNotNone(job["project_id"])

    def test_generate_route_passes_explicit_provider_and_model(self) -> None:
        principal = UserApiKeyPrincipal(
            key_id="key_provider_route",
            owner_user_id="user_provider_route",
            scopes=["generate:project"],
        )
        client = _route_client(principal)
        selections = [
            ("baseten", "zai-org/GLM-5.2"),
            ("openai", "gpt-5.5"),
        ]

        with (
            patch("backend.public_api._validate_generation_request"),
            patch("backend.public_api.build_generation_response") as generate,
        ):
            generate.side_effect = [
                _stub_generation_response(provider, model)
                for provider, model in selections
            ]
            for provider, model in selections:
                with self.subTest(provider=provider, model=model):
                    response = client.post(
                        "/api/v1/generate",
                        json={
                            "prompt": f"Route using {provider}",
                            "provider": provider,
                            "model": model,
                            "generate_image": False,
                        },
                    )
                    self.assertEqual(200, response.status_code, response.text)
                    metadata = response.json()["project_ir"]["assembly_metadata"]
                    self.assertEqual(provider, metadata["runtime_provider"])
                    self.assertEqual(model, metadata["runtime_model"])

        self.assertEqual(2, generate.call_count)
        for invocation, (provider, model) in zip(generate.call_args_list, selections):
            self.assertEqual(provider, invocation.kwargs["provider"])
            self.assertEqual(model, invocation.kwargs["model"])

    def test_llm_route_lists_configured_provider_model_choices(self) -> None:
        principal = UserApiKeyPrincipal(
            key_id="key_model_choices_route",
            owner_user_id="user_model_choices_route",
            scopes=["generate:project"],
        )
        client = _route_client(principal)

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "simulation",
                "LLM_ALLOWED_PROVIDERS": "simulation,baseten,openai",
                "BASETEN_ALLOWED_MODELS": "zai-org/GLM-5.2",
                "OPENAI_ALLOWED_MODELS": "gpt-5.5,gpt-4.1-mini",
            },
            clear=False,
        ):
            response = client.get("/api/v1/llms")

        self.assertEqual(200, response.status_code, response.text)
        providers = {item["id"]: item["models"] for item in response.json()["providers"]}
        self.assertEqual(["zai-org/GLM-5.2"], providers["baseten"])
        self.assertEqual(["gpt-4.1-mini", "gpt-5.5"], providers["openai"])

    def test_generate_route_rejects_disallowed_model_without_fallback(self) -> None:
        principal = UserApiKeyPrincipal(
            key_id="key_disallowed_model_route",
            owner_user_id="user_disallowed_model_route",
            scopes=["generate:project"],
        )
        client = _route_client(principal)

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "simulation",
                "LLM_ALLOWED_PROVIDERS": "simulation,openai",
                "OPENAI_ALLOWED_MODELS": "gpt-5.5",
            },
            clear=False,
        ):
            response = client.post(
                "/api/v1/generate",
                json={
                    "prompt": "This request must fail before an external call",
                    "provider": "openai",
                    "model": "not-allowed-model",
                    "generate_image": False,
                },
            )

        self.assertEqual(400, response.status_code, response.text)
        self.assertEqual("llm_config_invalid", response.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
