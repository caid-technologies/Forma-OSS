from __future__ import annotations

import json
import os
import unittest
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from backend import main
from backend.auth import UserContext, optional_user_context
from blueprint_core.models import (
    FunctionalRequirements,
    GenerateProjectRequest,
    HardwareIR,
    MechanicalNotes,
    MechanicalSource,
    ProjectOverview,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/projects",
            "headers": [],
        }
    )


def _user_context(owner_user_id: str) -> UserContext:
    return UserContext(
        provider="clerk",
        subject=owner_user_id,
        owner_user_id=owner_user_id,
        is_authenticated=True,
        is_admin=False,
        claims={"sub": owner_user_id},
    )


def _anonymous_context() -> UserContext:
    return UserContext(
        provider="clerk",
        subject=None,
        owner_user_id=None,
        is_authenticated=False,
        is_admin=False,
        claims={},
    )


def _project(
    project_id: str,
    *,
    owner_user_id: str,
    visibility: str,
    hardware_ir: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        project_id=project_id,
        chat_id=f"chat-{project_id}",
        owner_user_id=owner_user_id,
        visibility=visibility,
        title=f"Project {project_id}",
        prompt="Build a low-voltage test fixture.",
        created_at="2026-07-25T12:00:00Z",
        hardware_ir=hardware_ir
        or {
            "components": [],
            "assembly_metadata": {"project_id": project_id},
        },
    )


class LocalProjectIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_user_context_owns_local_dev_user_projects(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "local"}, clear=False):
            context = await optional_user_context(_request())

        self.assertEqual("local", context.provider)
        self.assertEqual("local-dev-user", context.subject)
        self.assertEqual("local-dev-user", context.owner_user_id)
        self.assertTrue(context.is_authenticated)
        self.assertTrue(context.is_admin)


class ProjectReadAccessTests(unittest.TestCase):
    def _summary_dependencies(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                main,
                "hydrate_image_storage_metadata",
                side_effect=lambda metadata, _project_id: metadata,
            )
        )
        stack.enter_context(patch.object(main, "creator_display_name", return_value="test-user"))
        return stack

    def test_public_list_includes_public_and_excludes_another_users_private_project(self) -> None:
        public_project = _project(
            "public-project",
            owner_user_id="user-b",
            visibility="public",
        )
        private_project = _project(
            "private-project",
            owner_user_id="user-b",
            visibility="private",
        )

        with self._summary_dependencies(), patch.object(
            main,
            "list_generated_projects",
            return_value=[private_project, public_project],
        ):
            response = main.list_projects_endpoint(_user_context("user-a"))

        self.assertEqual(["public-project"], [item["project_id"] for item in response])

    def test_owner_can_read_own_private_project(self) -> None:
        private_project = _project(
            "private-project",
            owner_user_id="user-a",
            visibility="private",
        )

        with self._summary_dependencies(), patch.object(
            main,
            "get_generated_project",
            return_value=private_project,
        ):
            response = main.get_project_endpoint(
                private_project.project_id,
                _user_context("user-a"),
            )

        self.assertEqual(private_project.project_id, response["project_id"])
        self.assertTrue(response["can_chat"])

    def test_nonowner_private_project_read_returns_not_found(self) -> None:
        private_project = _project(
            "private-project",
            owner_user_id="user-b",
            visibility="private",
        )

        with patch.object(main, "get_generated_project", return_value=private_project):
            with self.assertRaises(HTTPException) as raised:
                main.get_project_endpoint(
                    private_project.project_id,
                    _user_context("user-a"),
                )

        self.assertEqual(404, raised.exception.status_code)

    def test_public_legacy_project_read_redacts_downloadable_cad_urls(self) -> None:
        downloadable_url = "https://downloads.example.test/private/enclosure.step"
        legacy_ir = {
            # This deliberately resembles a saved legacy payload rather than a
            # current HardwareIR. Public reads must not turn schema drift into a
            # 500 response merely to display the inspectable project artifact.
            "overview": {"title": "Legacy enclosure"},
            "components": [
                {
                    "legacy_shape": "not-a-current-component",
                    "category": "mechanical",
                    "name": "Printed enclosure",
                    "url": downloadable_url,
                    "sourcing_url": downloadable_url,
                }
            ],
            "mechanical": {
                "cad_sources": [
                    {
                        "name": "Enclosure CAD",
                        "format": "STEP",
                        "url": downloadable_url,
                        "download_url": downloadable_url,
                    }
                ]
            },
            "assembly_metadata": {"project_id": "legacy-public-project"},
        }
        public_project = _project(
            "legacy-public-project",
            owner_user_id="user-b",
            visibility="public",
            hardware_ir=legacy_ir,
        )

        with self._summary_dependencies(), patch.object(
            main,
            "get_generated_project",
            return_value=public_project,
        ):
            response = main.get_project_endpoint(
                public_project.project_id,
                _anonymous_context(),
            )

        self.assertEqual(public_project.project_id, response["project_id"])
        self.assertFalse(response["can_chat"])
        self.assertIsInstance(response["project_ir"], dict)
        self.assertNotIn(downloadable_url, json.dumps(response, default=str))

    def test_public_current_ir_keeps_required_cad_url_field_valid_while_redacting_value(self) -> None:
        downloadable_url = "https://downloads.example.test/private/enclosure.step"
        ir = HardwareIR(
            overview=ProjectOverview(
                title="Public enclosure",
                description="A small low-voltage enclosure.",
                difficulty="Beginner",
                estimated_cost=12.0,
                category="Mechanical",
            ),
            requirements=FunctionalRequirements(
                requirements=["Protect the electronics"],
                power_needs="USB 5V",
                operating_voltage=5.0,
            ),
            mechanical=MechanicalNotes(
                enclosure_type="3D Printed",
                mounting_guidance="Fasten the board to internal standoffs.",
                manufacturability_rating="Easy",
                cad_sources=[
                    MechanicalSource(
                        name="Enclosure STEP",
                        source_type="Vendor CAD",
                        url=downloadable_url,
                        file_formats=["STEP"],
                    )
                ],
            ),
            assembly_metadata={"project_id": "current-public-project"},
        )
        public_project = _project(
            "current-public-project",
            owner_user_id="user-b",
            visibility="public",
            hardware_ir=ir.model_dump(mode="json"),
        )

        with self._summary_dependencies(), patch.object(
            main,
            "get_generated_project",
            return_value=public_project,
        ):
            response = main.get_project_endpoint(public_project.project_id, _anonymous_context())

        self.assertFalse(response["can_chat"])
        self.assertEqual("", response["project_ir"]["mechanical"]["cad_sources"][0]["url"])
        self.assertNotIn(downloadable_url, json.dumps(response, default=str))


class ProjectGenerationAccessTests(unittest.TestCase):
    def test_generation_response_marks_new_project_as_owner_chat_capable(self) -> None:
        job_store = MagicMock()
        job_store.is_cancelled.return_value = False
        job_store.get_job.return_value = {"status": "succeeded"}
        generated_response = {
            "project_ir": {
                "assembly_metadata": {
                    "project_id": "generated-project",
                    "chat_id": "generated-chat",
                }
            }
        }

        with (
            patch.object(main, "_apply_user_integrations"),
            patch.object(main, "get_workflow_debug_config", return_value={}),
            patch.object(main, "_deployment_runtime_config", return_value={"alpha_generation_gate_active": False}),
            patch.object(main, "JOB_STORE", job_store),
            patch.object(main, "observe_agent_pipeline", return_value=nullcontext()),
            patch.object(main, "build_generation_response", return_value=generated_response),
            patch.object(main, "_attach_generation_timing_metadata", side_effect=lambda response, _job: response),
            patch.object(main, "update_generated_project_hardware_ir"),
        ):
            response = main.generate_project_endpoint(
                GenerateProjectRequest(prompt="Build a sensor", chat_id="generated-chat"),
                _user_context("user-a"),
            )

        self.assertTrue(response["can_chat"])
        self.assertEqual("generated-project", response["project_id"])
        self.assertEqual("generated-chat", response["chat_id"])


if __name__ == "__main__":
    unittest.main()
