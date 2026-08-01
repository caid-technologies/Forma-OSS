from __future__ import annotations

import asyncio
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apps.api import a2a, main
from apps.api.a2a import A2AMessage
from apps.api.auth import UserContext, require_user_context
from apps.api.context_gathering_api import router
from blueprint_core import database
from blueprint_core.persistence.providers import create_sqlite_provider
from blueprint_core.persistence.repositories import SqlAlchemyRepository
from blueprint_core.workspaces.projects.models import GenerateProjectRequest
from blueprint_core.workspaces.workflow import WorkflowStateError


OWNER = "context-user"
USER = UserContext(
    provider="test",
    subject=OWNER,
    owner_user_id=OWNER,
    is_authenticated=True,
    is_admin=False,
)


@contextmanager
def sqlite_repository() -> Iterator[None]:
    with tempfile.TemporaryDirectory() as directory:
        provider = create_sqlite_provider(
            source="context gathering test",
            url=f"sqlite:///{Path(directory) / 'blueprint.db'}",
            import_legacy_jobs=False,
        )
        assert provider.session_factory is not None
        provider.initialize()
        original = database._DATABASE_REPOSITORY
        try:
            database._DATABASE_REPOSITORY = SqlAlchemyRepository(provider.session_factory)
            yield
        finally:
            database._DATABASE_REPOSITORY = original


class ContextGatheringIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_user_context] = lambda: USER
        self.client = TestClient(app)

    def test_text_image_and_document_append_brief_versions_without_enqueuing_jobs(self) -> None:
        project_id = str(uuid.uuid4())
        conversation_id = "context-chat-1"

        with sqlite_repository(), patch.object(a2a.JOB_STORE, "create_job") as create_job:
            first = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={
                    "conversation_id": conversation_id,
                    "text": "Build an ESP32 environmental monitor with USB-C power and wiring.",
                },
            )
            second = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={
                    "conversation_id": conversation_id,
                    "text": "It must fit within 100 mm and include product images.",
                    "attachments": [
                        {
                            "attachment_id": "clipboard-image",
                            "kind": "image",
                            "name": "reference.png",
                            "media_type": "image/png",
                            "data_url": "data:image/png;base64,aW1hZ2U=",
                            "source": "clipboard",
                        },
                        {
                            "attachment_id": "requirements-document",
                            "kind": "document",
                            "name": "requirements.txt",
                            "media_type": "text/plain",
                            "extracted_text": "The display must remain readable outdoors.",
                        },
                    ],
                },
            )
            versions = database.list_design_brief_versions(project_id, OWNER)
            chat = database.get_project_chat(conversation_id, OWNER)

        self.assertEqual(201, first.status_code, first.text)
        self.assertEqual("gathering_context", first.json()["workflow"]["state"])
        self.assertTrue(first.json()["questions"])
        self.assertEqual(201, second.status_code, second.text)
        self.assertEqual(2, second.json()["design_brief"]["brief_version"])
        self.assertEqual([1, 2], [brief.brief_version for brief in versions])
        self.assertEqual(2, len(versions[-1].references))
        self.assertIn("product images", versions[-1].requested_outputs)
        self.assertIn("The display must remain readable outdoors.", versions[-1].requirements)
        self.assertEqual(4, len(chat.messages))
        create_job.assert_not_called()

    def test_generation_and_mutating_tools_are_blocked_during_gathering(self) -> None:
        project_id = str(uuid.uuid4())
        with sqlite_repository():
            database.initialize_project_workflow(project_id, OWNER)

            for action in ("blueprint.generate_project", "fabricator.plan", "opencad.mutate"):
                with self.subTest(action=action), self.assertRaises(WorkflowStateError) as raised:
                    database.ensure_project_action_allowed(project_id, OWNER, action, require_workflow=True)
                self.assertEqual("tool_execution_blocked_while_gathering_context", raised.exception.code)

    def test_generate_endpoint_rejects_before_worker_job_is_created(self) -> None:
        project_id = str(uuid.uuid4())
        with sqlite_repository(), patch.object(main.JOB_STORE, "create_job") as create_job:
            database.initialize_project_workflow(project_id, OWNER)
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.generate_project_endpoint(
                    GenerateProjectRequest(prompt="Build it", project_id=project_id),
                    USER,
                ))

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual("tool_execution_blocked_while_gathering_context", raised.exception.detail["code"])
        create_job.assert_not_called()

    def test_a2a_generation_rejects_before_worker_job_is_created(self) -> None:
        project_id = str(uuid.uuid4())
        message = A2AMessage(
            sender="test-agent",
            action="blueprint.generate_project",
            payload={"project_id": project_id, "owner_user_id": OWNER, "prompt": "Build it"},
        )
        with sqlite_repository(), patch.object(a2a.A2A_HUB, "register", new=AsyncMock()), patch.object(
            a2a.JOB_STORE, "create_job"
        ) as create_job:
            database.initialize_project_workflow(project_id, OWNER)
            with self.assertRaises(WorkflowStateError):
                asyncio.run(a2a.submit_a2a_message(message))

        create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
