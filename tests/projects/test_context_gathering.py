from __future__ import annotations

import asyncio
import tempfile
import unittest
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apps.api import a2a, main
from apps.api.a2a import A2AMessage
from apps.api.auth import UserContext, require_user_context
from apps.api.context_gathering_api import router
from blueprint_core import database
from blueprint_core.persistence.providers import create_sqlite_provider
from blueprint_core.persistence.repositories import SqlAlchemyRepository
from blueprint_core.workspaces.context.agent import ContextAgentTurn, ContextBriefState
from blueprint_core.workspaces.design_briefs import DesignBriefReadiness
from blueprint_core.workspaces.projects.models import GenerateProjectRequest
from blueprint_core.workspaces.workflow import ProjectWorkflowState, WorkflowActorType, WorkflowStateError


OWNER = "context-user"
USER = UserContext(
    provider="test",
    subject=OWNER,
    owner_user_id=OWNER,
    is_authenticated=True,
    is_admin=False,
)


class StubContextProvider:
    provider_name = "test"
    model_name = "test-context-model"
    is_configured = True

    def __init__(self, turns: list[ContextAgentTurn]) -> None:
        self.turns = list(turns)
        self.prompts: list[str] = []

    def generate_structured(self, prompt, schema_class, image_bytes=None, image_mime_type=None):
        self.prompts.append(prompt)
        if not self.turns:
            raise AssertionError("Unexpected context model call.")
        return schema_class.model_validate(self.turns.pop(0).model_dump())


def brief_turn(
    assistant_message: str,
    *,
    summary: str,
    requirements: list[str],
    constraints: list[str] | None = None,
    requested_outputs: list[str] | None = None,
    validation_criteria: list[str] | None = None,
    questions: list[str] | None = None,
    assumptions: list[str] | None = None,
    tool: str = "update_design_brief",
    generation_prompt: str | None = None,
) -> ContextAgentTurn:
    unresolved = questions or []
    brief = ContextBriefState(
        intent="design a buildable hardware product",
        summary=summary,
        requirements=requirements,
        constraints=constraints or [],
        requested_outputs=requested_outputs or [],
        validation_criteria=validation_criteria or [],
        unresolved_questions=unresolved,
        assumptions=assumptions or [],
        readiness=(
            DesignBriefReadiness.NEEDS_CLARIFICATION
            if unresolved
            else DesignBriefReadiness.DRAFT
        ),
    )
    call: dict[str, object] = {
        "assistant_message": assistant_message,
        "tool": tool,
        "brief": brief.model_dump(mode="json"),
    }
    if generation_prompt is not None:
        call["generation_prompt"] = generation_prompt
    return ContextAgentTurn(call=call)


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
        provider = StubContextProvider([
            brief_turn(
                "An ESP32 environmental monitor is a good start. Where will it operate?",
                summary="ESP32 environmental monitor",
                requirements=["Build an ESP32 environmental monitor with USB-C power and wiring."],
                requested_outputs=["wiring"],
                questions=["Where will the monitor operate?"],
            ),
            brief_turn(
                "Got it. What environmental range should the enclosure tolerate?",
                summary="ESP32 environmental monitor",
                requirements=[
                    "Build an ESP32 environmental monitor with USB-C power and wiring.",
                    "It must fit within 100 mm and include product images.",
                    "The display must remain readable outdoors.",
                ],
                constraints=["It must fit within 100 mm.", "The display must remain readable outdoors."],
                requested_outputs=["wiring", "product images"],
                questions=["What environmental range should the enclosure tolerate?"],
            ),
        ])

        with sqlite_repository(), patch.object(a2a.JOB_STORE, "create_job") as create_job, patch(
            "blueprint_core.workspaces.context.agent.build_llm_provider",
            return_value=provider,
        ):
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

    def test_explicit_follow_up_answers_clear_matching_questions(self) -> None:
        project_id = str(uuid.uuid4())
        conversation_id = "context-chat-answers"
        provider = StubContextProvider([
            brief_turn(
                "Who will use the sensor, and where?",
                summary="Compact environmental sensor",
                requirements=["Build a compact environmental sensor."],
                questions=["Who will use the sensor, and where?"],
            ),
            brief_turn(
                "That gives me a solid first-version brief.",
                summary="Compact ESP32-S3 bench environmental sensor",
                requirements=[
                    "Build a compact environmental sensor.",
                    "Use an ESP32-S3 powered from USB-C 5 V.",
                    "Show readings on an OLED.",
                    "It is a bench tool for engineers.",
                ],
                constraints=["It must fit within 100 mm."],
                requested_outputs=["wiring", "BOM"],
                validation_criteria=["Readings remain within the sensor tolerance."],
            ),
        ])
        with sqlite_repository(), patch(
            "blueprint_core.workspaces.context.agent.build_llm_provider",
            return_value=provider,
        ):
            first = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={"conversation_id": conversation_id, "text": "Build a compact environmental sensor."},
            )
            second = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={
                    "conversation_id": conversation_id,
                    "text": (
                        "Use an ESP32-S3 powered from USB-C 5 V. Show readings on an OLED. "
                        "It is a bench tool for engineers, must fit within 100 mm, and should include wiring and a BOM. "
                        "Validate that readings remain within the sensor tolerance."
                    ),
                },
            )

        self.assertEqual(201, first.status_code)
        self.assertTrue(first.json()["questions"])
        self.assertEqual(201, second.status_code)
        self.assertEqual([], second.json()["questions"])

    def test_greeting_is_conversational_and_does_not_create_a_design_brief(self) -> None:
        project_id = str(uuid.uuid4())
        provider = StubContextProvider([
            ContextAgentTurn(
                call={
                    "assistant_message": "Hey! What are you thinking about building?",
                    "tool": "respond",
                },
            ),
        ])
        with sqlite_repository(), patch(
            "blueprint_core.workspaces.context.agent.build_llm_provider",
            return_value=provider,
        ):
            response = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={"conversation_id": "greeting-chat", "text": "hi"},
            )
            versions = database.list_design_brief_versions(project_id, OWNER)

        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual("Hey! What are you thinking about building?", response.json()["assistant_message"])
        self.assertIsNone(response.json()["design_brief"])
        self.assertEqual("test", response.json()["provider"])
        self.assertEqual("test-context-model", response.json()["model"])
        self.assertEqual([], versions)
        self.assertIn("Never save pleasantries", provider.prompts[0])

    def test_explicit_build_request_executes_build_tool_and_transitions_workflow(self) -> None:
        project_id = str(uuid.uuid4())
        generation_prompt = (
            "Generate a standard 250 mm adjustable steel wrench with a 30 mm jaw opening, "
            "mechanical specification, BOM, and validation plan."
        )
        provider = StubContextProvider([
            brief_turn(
                "I’m starting the adjustable-wrench build now.",
                summary="Standard industrial adjustable wrench",
                requirements=[],
                requested_outputs=[],
                validation_criteria=[],
                assumptions=["Use common industrial adjustable-wrench proportions."],
                tool="build_project",
                generation_prompt=generation_prompt,
            ),
        ])
        with sqlite_repository(), patch(
            "blueprint_core.workspaces.context.agent.build_llm_provider",
            return_value=provider,
        ):
            response = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={"conversation_id": "build-chat", "text": "Go ahead and build it."},
            )

        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual("build_project", response.json()["action"])
        self.assertEqual(generation_prompt, response.json()["generation_prompt"])
        self.assertEqual("building", response.json()["workflow"]["state"])
        self.assertEqual(1, response.json()["design_brief"]["brief_version"])
        self.assertTrue(response.json()["design_brief"]["requirements"])
        self.assertTrue(response.json()["design_brief"]["requested_outputs"])
        self.assertTrue(response.json()["design_brief"]["validation_criteria"])

    def test_try_again_recovers_a_legacy_building_workflow_and_restarts_generation(self) -> None:
        project_id = str(uuid.uuid4())
        first_prompt = "Generate a standalone handheld game controller."
        retry_prompt = "Retry generating the standalone handheld game controller."
        provider = StubContextProvider([
            brief_turn(
                "I’m starting the handheld build now.",
                summary="Standalone handheld game controller",
                requirements=["Run games entirely on the handheld."],
                requested_outputs=["wiring", "BOM"],
                validation_criteria=["The controls register correctly."],
                tool="build_project",
                generation_prompt=first_prompt,
            ),
            brief_turn(
                "I’m retrying the handheld build now.",
                summary="Standalone handheld game controller",
                requirements=["Run games entirely on the handheld."],
                requested_outputs=["wiring", "BOM"],
                validation_criteria=["The controls register correctly."],
                tool="build_project",
                generation_prompt=retry_prompt,
            ),
        ])
        with sqlite_repository(), patch(
            "blueprint_core.workspaces.context.agent.build_llm_provider",
            return_value=provider,
        ):
            first = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={"conversation_id": "retry-chat", "text": "Go."},
            )
            retry = self.client.post(
                f"/projects/{project_id}/context/messages",
                json={"conversation_id": "retry-chat", "text": "Try again."},
            )
            transitions = database.list_project_workflow_transitions(project_id, OWNER)

        self.assertEqual(201, first.status_code, first.text)
        self.assertEqual(201, retry.status_code, retry.text)
        self.assertEqual("build_project", retry.json()["action"])
        self.assertEqual(retry_prompt, retry.json()["generation_prompt"])
        self.assertEqual("building", retry.json()["workflow"]["state"])
        self.assertEqual(2, retry.json()["design_brief"]["brief_version"])
        self.assertEqual(
            ["gathering_context", "building", "failed", "gathering_context", "building"],
            [transition.to_state.value for transition in transitions],
        )
        self.assertIn('"previous_generation_state": "building"', provider.prompts[1])
        self.assertIn("Decide semantically; never route by matching fixed words or phrases.", provider.prompts[1])
        self.assertNotIn("retry, try again", provider.prompts[1])

    def test_generate_failure_marks_context_workflow_retryable(self) -> None:
        project_id = str(uuid.uuid4())
        job_store = MagicMock()
        retry_provider = StubContextProvider([
            brief_turn(
                "I’m restarting the pending build.",
                summary="Pending hardware project",
                requirements=["Generate the pending hardware project."],
                requested_outputs=["BOM"],
                validation_criteria=["The generated project satisfies the saved brief."],
                tool="build_project",
                generation_prompt="Generate the pending hardware project from its saved context.",
            ),
        ])
        with sqlite_repository():
            database.initialize_project_workflow(project_id, OWNER)
            database.transition_project_workflow(
                project_id,
                OWNER,
                ProjectWorkflowState.BUILDING,
                actor_type=WorkflowActorType.USER,
                actor_id=OWNER,
                reason="Start test build.",
            )
            with (
                patch.object(main, "_apply_user_integrations"),
                patch.object(main, "get_workflow_debug_config", return_value={}),
                patch.object(main, "_deployment_runtime_config", return_value={"alpha_generation_gate_active": False}),
                patch.object(main, "JOB_STORE", job_store),
                patch.object(main, "observe_agent_pipeline", return_value=nullcontext()),
                patch.object(main, "build_generation_response", side_effect=RuntimeError("provider failed")),
            ):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(main.generate_project_endpoint(
                        GenerateProjectRequest(prompt="Build it", project_id=project_id),
                        USER,
                    ))
            workflow = database.get_project_workflow(project_id, OWNER)
            with patch(
                "blueprint_core.workspaces.context.agent.build_llm_provider",
                return_value=retry_provider,
            ):
                retry = self.client.post(
                    f"/projects/{project_id}/context/messages",
                    json={"conversation_id": "failed-retry-chat", "text": "Continue."},
                )
            resumed_workflow = database.get_project_workflow(project_id, OWNER)

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("failed", workflow.state.value)
        job_store.mark_failed.assert_called_once()
        self.assertEqual(201, retry.status_code, retry.text)
        self.assertEqual("build_project", retry.json()["action"])
        self.assertEqual("building", resumed_workflow.state.value)
        self.assertIn('"previous_generation_state": "failed"', retry_provider.prompts[0])

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
