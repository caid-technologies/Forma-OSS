from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.auth import UserContext, require_user_context
from apps.api.context_builds import ContextBuildDispatcher, context_build_dispatcher
from blueprint_core.agents.context_gathering import ContextGatheringAgent
from blueprint_core.database import (
    DesignBriefAccessError,
    DesignBriefNotFoundError,
    create_design_brief_version,
    get_latest_design_brief,
    get_project_chat,
    get_project_workflow,
    initialize_project_workflow,
    transition_project_workflow,
    upsert_project_chat,
)
from blueprint_core.llm import build_llm_provider
from blueprint_core.user_integrations import UserIntegrationStore, apply_user_integrations_to_environment
from blueprint_core.workspaces.context import (
    ContextBuildExecution,
    ContextGatheringRequest,
    ContextGatheringResponse,
)
from blueprint_core.workspaces.readiness import ReadinessError
from blueprint_core.workspaces.workflow import ProjectWorkflowState, WorkflowActorType, WorkflowStateError


router = APIRouter(prefix="/projects/{project_id}/context", tags=["context-gathering"])
logger = logging.getLogger(__name__)


_CONTEXT_FREE_USER_TURN = re.compile(
    r"^(?:(?:please\s+)?(?:go|go ahead|continue|start|start now|build|build it|build it now|"
    r"make it|make it now|do it|do it now|proceed|ready|skip|skip it|skip context gathering)|"
    r"idk|i do not know|i don t know|don t know|not sure|unsure|no idea|you choose|up to you|"
    r"hi|hello|hey)$",
)


def _contains_project_context(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(text or "").casefold()).strip()
    return bool(normalized and not _CONTEXT_FREE_USER_TURN.fullmatch(normalized))


def _bootstrap_context_request(
    request: ContextGatheringRequest,
    existing_messages: list[dict],
) -> ContextGatheringRequest | None:
    """Recover project context when build intent arrives before a DesignBrief exists."""

    context_parts: list[str] = []
    seen: set[str] = set()
    for message in existing_messages[-12:]:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = str(message.get("content") or "").strip()
        key = content.casefold()
        if _contains_project_context(content) and key not in seen:
            seen.add(key)
            context_parts.append(content)
    current_text = request.text.strip()
    current_key = current_text.casefold()
    if _contains_project_context(current_text) and current_key not in seen:
        context_parts.append(current_text)
    if not context_parts and not request.attachments:
        return None
    return request.model_copy(update={"text": "\n".join(context_parts)})


def _owner(user: UserContext) -> str:
    owner = str(user.owner_user_id or "").strip()
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "Sign in to gather project context."},
        )
    return owner


def _workflow_error(exc: WorkflowStateError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if exc.code == "workflow_not_found" else status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail=exc.as_dict())


def context_gathering_agent(
    user: UserContext = Depends(require_user_context),
) -> ContextGatheringAgent:
    if user.owner_user_id:
        apply_user_integrations_to_environment(UserIntegrationStore.for_user(user.owner_user_id))
    else:
        apply_user_integrations_to_environment()
    return ContextGatheringAgent(llm_provider=build_llm_provider())


@router.post("/messages", response_model=ContextGatheringResponse, status_code=status.HTTP_201_CREATED)
def gather_project_context_endpoint(
    project_id: UUID,
    request: ContextGatheringRequest,
    user: UserContext = Depends(require_user_context),
    agent: ContextGatheringAgent = Depends(context_gathering_agent),
    build_dispatcher: ContextBuildDispatcher | None = Depends(context_build_dispatcher),
) -> ContextGatheringResponse:
    """Route one natural conversation turn and mutate context only when appropriate."""

    owner = _owner(user)
    existing_chat = get_project_chat(request.conversation_id, owner)
    existing_messages = list(getattr(existing_chat, "messages", None) or [])
    try:
        previous = get_latest_design_brief(str(project_id), owner)
    except DesignBriefNotFoundError:
        previous = None
    if previous and previous.conversation_id != request.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "context_conversation_mismatch",
                "message": "This project is already associated with a different conversation.",
                "context": {"conversation_id": previous.conversation_id},
            },
        )

    try:
        workflow = get_project_workflow(str(project_id), owner)
    except WorkflowStateError as exc:
        if exc.code != "workflow_not_found":
            raise _workflow_error(exc) from exc
        workflow = None

    try:
        decision = agent.route_turn(
            request,
            previous,
            workflow_state=workflow.state.value if workflow else None,
            messages=existing_messages,
        )
    except Exception:
        # Provider failures must not make the conversation unusable.
        decision = ContextGatheringAgent().route_turn(
            request,
            previous,
            workflow_state=workflow.state.value if workflow else None,
            messages=existing_messages,
        )

    brief = previous
    questions: list[str] = []
    suggestions = list(decision.suggestions) if decision.tool_name == "ask_question" else []
    build_execution: ContextBuildExecution | None = None
    if decision.tool_name == "build_project" and brief is None:
        bootstrap_request = _bootstrap_context_request(request, existing_messages)
        if bootstrap_request is not None:
            if workflow is None:
                try:
                    workflow = initialize_project_workflow(
                        str(project_id),
                        owner,
                        actor_type=WorkflowActorType.USER,
                        actor_id=owner,
                        reason="Build request supplied initial project context.",
                    ).workflow
                except WorkflowStateError as exc:
                    raise _workflow_error(exc) from exc
            brief_create, _, questions, _ = agent.update(bootstrap_request, None)
            try:
                brief = create_design_brief_version(str(project_id), owner, brief_create)
            except DesignBriefAccessError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "project_not_found", "message": "Project not found."},
                ) from exc
            logger.info(
                "Bootstrapped DesignBrief from first-turn build request: project_id=%s conversation_id=%s",
                project_id,
                request.conversation_id,
            )
    elif decision.tool_name == "build_project" and workflow is None:
        try:
            workflow = initialize_project_workflow(
                str(project_id),
                owner,
                actor_type=WorkflowActorType.USER,
                actor_id=owner,
                reason="Build request resumed existing project context.",
            ).workflow
        except WorkflowStateError as exc:
            raise _workflow_error(exc) from exc

    if decision.tool_name == "ask_question" and decision.save_context:
        if workflow is None:
            try:
                workflow = initialize_project_workflow(
                    str(project_id),
                    owner,
                    actor_type=WorkflowActorType.USER,
                    actor_id=owner,
                    reason="Conversation supplied project context.",
                ).workflow
            except WorkflowStateError as exc:
                raise _workflow_error(exc) from exc
        elif workflow.state == ProjectWorkflowState.READY_TO_BUILD:
            try:
                workflow = transition_project_workflow(
                    str(project_id),
                    owner,
                    ProjectWorkflowState.GATHERING_CONTEXT,
                    actor_type=WorkflowActorType.USER,
                    actor_id=owner,
                    reason="User added project context after the previous handoff.",
                ).workflow
            except WorkflowStateError as exc:
                raise _workflow_error(exc) from exc
        if workflow.state != ProjectWorkflowState.GATHERING_CONTEXT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "context_update_not_allowed",
                    "message": f"Project context cannot be changed while the workflow is {workflow.state.value}.",
                },
            )

        brief_create, _, questions, generated_suggestions = agent.update(request, previous)
        if not suggestions:
            suggestions = generated_suggestions
        try:
            brief = create_design_brief_version(str(project_id), owner, brief_create)
        except DesignBriefAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found."},
            ) from exc
    elif decision.tool_name == "build_project" and workflow is not None:
        if workflow.state == ProjectWorkflowState.GATHERING_CONTEXT:
            try:
                workflow = transition_project_workflow(
                    str(project_id),
                    owner,
                    ProjectWorkflowState.READY_TO_BUILD,
                    actor_type=WorkflowActorType.USER,
                    actor_id=owner,
                    reason="Conversational agent handed the brief to the next stage.",
                    idempotency_key=f"conversation-proceed:{request.conversation_id}",
                ).workflow
            except WorkflowStateError as exc:
                raise _workflow_error(exc) from exc
        if brief is not None and build_dispatcher is not None:
            try:
                build_execution, workflow = build_dispatcher.start(
                    str(project_id),
                    owner,
                    request.conversation_id,
                )
                execution_messages = {
                    "planned": (
                        "I’ve started the design. The build agents are generating the system architecture, "
                        "electronics, mechanics, and build artifacts now."
                    ),
                    "running": "The design build is already running; I’ll keep the existing agents working on it.",
                    "succeeded": "The first design revision is ready for review.",
                    "failed": "The design build stopped after an agent failure. The brief and build record are preserved.",
                }
                decision = decision.model_copy(update={
                    "assistant_message": execution_messages.get(
                        build_execution.status,
                        "The design build has been handed to the build agents.",
                    ),
                })
            except ReadinessError as exc:
                logger.exception("Conversational build readiness failed for project_id=%s", project_id)
                decision = decision.model_copy(update={
                    "assistant_message": (
                        "I couldn’t start the build automatically. The brief is preserved, so you can try again "
                        "without re-entering the project details."
                    ),
                })
            except Exception:
                logger.exception("Could not dispatch conversational build for project_id=%s", project_id)
                try:
                    workflow = transition_project_workflow(
                        str(project_id),
                        owner,
                        ProjectWorkflowState.FAILED,
                        actor_type=WorkflowActorType.SYSTEM,
                        actor_id="context-build-dispatcher",
                        reason="The conversational build could not be dispatched.",
                        idempotency_key=f"conversation-build-dispatch-failed:{request.conversation_id}",
                    ).workflow
                except WorkflowStateError:
                    logger.warning(
                        "Could not mark failed conversational build for project_id=%s",
                        project_id,
                        exc_info=True,
                    )
                decision = decision.model_copy(update={
                    "assistant_message": (
                        "I couldn’t start the build. The brief is preserved, so you can try again without "
                        "re-entering the project details."
                    ),
                })
    if decision.tool_name == "build_project" and (workflow is None or brief is None):
        decision = decision.model_copy(update={
            "turn_kind": "clarification",
            "tool_name": "ask_question",
            "save_context": False,
            "assistant_message": "Tell me what you want to build first, and I’ll help shape it and start the design.",
        })

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    attachments = [
        {
            "attachmentId": item.attachment_id,
            "kind": item.kind,
            "name": item.name,
            "mediaType": item.media_type,
            "uri": item.uri,
            "source": item.source,
            "hasInlineData": bool(item.data_url),
        }
        for item in request.attachments
    ]
    context_project_id = str(project_id) if workflow is not None or brief is not None else None
    user_message = {
            "id": f"context-user-{uuid4().hex}",
            "role": "user",
            "content": request.text or "Shared a project reference.",
            "status": "complete",
            "timestamp": now,
            "attachments": attachments,
        }
    assistant_message_record = {
            "id": f"context-assistant-{uuid4().hex}",
            "role": "assistant",
            "content": decision.assistant_message,
            "status": "complete",
            "timestamp": now,
            "questions": questions,
            "suggestions": suggestions,
            "turnKind": decision.turn_kind,
            "toolName": decision.tool_name,
        }
    if context_project_id:
        user_message["contextProjectId"] = context_project_id
        assistant_message_record["contextProjectId"] = context_project_id
    if workflow is not None:
        assistant_message_record["workflowState"] = workflow.state.value
    if brief is not None:
        assistant_message_record["designBriefVersion"] = brief.brief_version
    if build_execution is not None:
        assistant_message_record["buildExecution"] = build_execution.model_dump(mode="json")
    if request.requested_tool is None:
        existing_messages.append(user_message)
    existing_messages.append(assistant_message_record)
    title = str(getattr(existing_chat, "title", "") or "").strip()
    if not title:
        title = (request.text or (brief.summary if brief is not None else "Hardware project"))[:100]
    created_at = str(getattr(existing_chat, "created_at", "") or now)
    upsert_project_chat(
        chat_id=request.conversation_id,
        owner_user_id=owner,
        title=title,
        messages=existing_messages,
        created_at=created_at,
        updated_at=now,
    )
    return ContextGatheringResponse(
        turn_kind=decision.turn_kind,
        tool_name=decision.tool_name,
        workflow=workflow,
        design_brief=brief,
        assistant_message=decision.assistant_message,
        questions=questions,
        suggestions=suggestions,
        build_execution=build_execution,
    )
