from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.auth import UserContext, require_user_context
from blueprint_core.agents.context_gathering import ContextGatheringAgent
from blueprint_core.llm_providers import (
    LLMProviderConfigError,
    LLMProviderInputError,
    LLMProviderOutputError,
)
from blueprint_core.database import (
    DesignBriefAccessError,
    DesignBriefNotFoundError,
    create_design_brief_version,
    get_latest_design_brief,
    get_project_chat,
    initialize_project_workflow,
    upsert_project_chat,
)
from blueprint_core.workspaces.context import (
    ContextGatheringRequest,
    ContextGatheringResponse,
)
from blueprint_core.workspaces.workflow import ProjectWorkflowState, WorkflowActorType, WorkflowStateError
from blueprint_core.user_integrations import UserIntegrationStore, apply_user_integrations_to_environment


router = APIRouter(prefix="/projects/{project_id}/context", tags=["context-gathering"])
logger = logging.getLogger(__name__)


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


@router.post("/messages", response_model=ContextGatheringResponse, status_code=status.HTTP_201_CREATED)
def gather_project_context_endpoint(
    project_id: UUID,
    request: ContextGatheringRequest,
    user: UserContext = Depends(require_user_context),
) -> ContextGatheringResponse:
    """Persist one conversational turn without invoking generation or worker tools."""

    owner = _owner(user)
    try:
        initialized = initialize_project_workflow(
            str(project_id),
            owner,
            actor_type=WorkflowActorType.USER,
            actor_id=owner,
            reason="Context-gathering conversation started.",
        )
    except WorkflowStateError as exc:
        raise _workflow_error(exc) from exc
    workflow = initialized.workflow
    if workflow.state != ProjectWorkflowState.GATHERING_CONTEXT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "context_gathering_not_active",
                "message": "Project context can only be updated while gathering_context is active.",
                "context": {"project_id": str(project_id), "workflow_state": workflow.state.value},
            },
        )

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

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    existing_chat = get_project_chat(request.conversation_id, owner)
    existing_messages = list(getattr(existing_chat, "messages", None) or [])
    if user.provider == "local":
        apply_user_integrations_to_environment()
    else:
        apply_user_integrations_to_environment(UserIntegrationStore.for_user(owner))
    try:
        brief_create, assistant_message, questions = ContextGatheringAgent(
            provider_name=request.provider,
            model_name=request.model,
        ).update(request, previous, messages=existing_messages)
    except (LLMProviderConfigError, LLMProviderInputError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "context_model_unavailable", "message": str(exc)},
        ) from exc
    except LLMProviderOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "context_model_output_invalid", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception(
            "Context conversation failed for provider=%s model=%s.",
            request.provider,
            request.model,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "context_model_failed", "message": str(exc)},
        ) from exc

    brief = previous
    if brief_create is not None:
        try:
            brief = create_design_brief_version(str(project_id), owner, brief_create)
        except DesignBriefAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found."},
            ) from exc

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
    assistant_record = {
        "id": f"context-assistant-{uuid4().hex}",
        "role": "assistant",
        "content": assistant_message,
        "status": "complete",
        "timestamp": now,
        "contextProjectId": str(project_id),
        "questions": questions,
    }
    if brief is not None:
        assistant_record["designBriefVersion"] = brief.brief_version
    existing_messages.extend([
        {
            "id": f"context-user-{uuid4().hex}",
            "role": "user",
            "content": request.text or "Shared a project reference.",
            "status": "complete",
            "timestamp": now,
            "contextProjectId": str(project_id),
            "attachments": attachments,
        },
        assistant_record,
    ])
    title = str(getattr(existing_chat, "title", "") or "").strip()
    if not title:
        title = (request.text or (brief.summary if brief else "Forma conversation"))[:100]
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
        workflow=workflow,
        design_brief=brief,
        assistant_message=assistant_message,
        questions=questions,
    )
