from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from blueprint_core.llm_providers import (
    LLMProviderConfigError,
    StructuredLLMProvider,
    build_llm_provider,
)
from blueprint_core.workspaces.context.models import ContextAttachment, ContextGatheringRequest
from blueprint_core.workspaces.design_briefs import (
    DESIGN_BRIEF_SCHEMA_VERSION,
    DesignBrief,
    DesignBriefCreate,
    DesignBriefReadiness,
    DesignBriefReference,
)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split()).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _reference(attachment: ContextAttachment) -> DesignBriefReference:
    identity = attachment.attachment_id
    if not identity:
        digest_source = "|".join((attachment.kind, attachment.name or "", attachment.uri or "", attachment.data_url or ""))
        identity = f"attachment-{hashlib.sha256(digest_source.encode()).hexdigest()[:20]}"
    metadata: dict[str, object] = {"source": attachment.source}
    if attachment.data_url:
        metadata["inline_data_supplied"] = True
        metadata["inline_data_length"] = len(attachment.data_url)
    if attachment.extracted_text:
        metadata["text_extracted"] = True
    return DesignBriefReference(
        reference_id=identity,
        kind=f"uploaded_{attachment.kind}",
        label=attachment.name,
        uri=attachment.uri,
        media_type=attachment.media_type,
        metadata=metadata,
    )


class ContextBriefState(BaseModel):
    """The complete brief state supplied to the update_design_brief tool."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    validation_criteria: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    readiness: DesignBriefReadiness = DesignBriefReadiness.DRAFT


class ContextAgentTurn(BaseModel):
    """A conversational response plus the persistence tool the model chose."""

    model_config = ConfigDict(extra="forbid")

    assistant_message: str = Field(min_length=1)
    tool: Literal["respond", "update_design_brief"]
    brief: ContextBriefState | None

    @model_validator(mode="after")
    def require_brief_for_update(self) -> "ContextAgentTurn":
        if self.tool == "update_design_brief" and self.brief is None:
            raise ValueError("update_design_brief requires a complete brief state.")
        if self.tool == "respond" and self.brief is not None:
            raise ValueError("respond must not include a brief update.")
        return self


def _history_for_prompt(messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in (messages or [])[-12:]:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content[:2000]})
    return history


def _attachment_context(attachments: list[ContextAttachment]) -> list[dict[str, Any]]:
    return [
        {
            "kind": item.kind,
            "name": item.name,
            "media_type": item.media_type,
            "uri": item.uri,
            "source": item.source,
            "has_inline_data": bool(item.data_url),
            "extracted_text": item.extracted_text,
        }
        for item in attachments
    ]


def _first_inline_image(attachments: list[ContextAttachment]) -> tuple[bytes | None, str | None]:
    for item in attachments:
        if item.kind != "image" or not item.data_url:
            continue
        header, separator, payload = item.data_url.partition(",")
        if not separator or ";base64" not in header.lower():
            continue
        try:
            image_bytes = base64.b64decode(payload, validate=True)
        except (ValueError, TypeError):
            continue
        if image_bytes:
            media_type = item.media_type or header.removeprefix("data:").split(";", 1)[0] or "image/png"
            return image_bytes, media_type
    return None, None


class ContextBriefUpdater:
    """Runs a conversational model turn and executes its structured brief tool call."""

    def __init__(
        self,
        provider_name: str | None = None,
        model_name: str | None = None,
        *,
        llm_provider: StructuredLLMProvider | None = None,
    ) -> None:
        self.llm_provider = llm_provider or build_llm_provider(provider_name=provider_name, model_name=model_name)
        if not self.llm_provider.is_configured:
            validation = self.llm_provider.validate_configured_model(raise_on_strict=False)
            raise LLMProviderConfigError(
                validation.validation_error or "A live language model provider is required for context conversation."
            )

    def _prompt(
        self,
        request: ContextGatheringRequest,
        previous: DesignBrief | None,
        messages: list[dict[str, Any]] | None,
    ) -> str:
        previous_state = None
        if previous is not None:
            previous_state = {
                "intent": previous.intent,
                "summary": previous.summary,
                "requirements": previous.requirements,
                "constraints": previous.constraints,
                "requested_outputs": previous.requested_outputs,
                "validation_criteria": previous.validation_criteria,
                "unresolved_questions": previous.unresolved_questions,
                "assumptions": previous.assumptions,
                "readiness": previous.readiness.value,
            }

        turn_input = {
            "conversation_history": _history_for_prompt(messages),
            "current_user_message": request.text,
            "attachments": _attachment_context(request.attachments),
            "current_design_brief": previous_state,
        }
        return (
            "You are Forma, a conversational hardware-design collaborator. Respond naturally to the user's actual "
            "message and use one of the two tools represented by the output schema.\n\n"
            "Tool policy:\n"
            "- Choose `respond` for greetings, thanks, meta-conversation, capability questions, or any turn that does "
            "not add or change project facts. Set brief to null for this tool. Never save pleasantries such as 'hi' "
            "as requirements.\n"
            "- Choose `update_design_brief` when the user supplies, changes, or answers something about a project, or "
            "provides a project attachment. Return the complete updated brief state, merging useful prior facts and "
            "removing questions the user has answered.\n"
            "- The assistant_message must sound like a direct continuation of the conversation. Do not mention JSON, "
            "schemas, tools, persistence, or internal workflow.\n"
            "- If clarification is genuinely useful, ask only the single most important contextual follow-up in the "
            "assistant_message and include that question in unresolved_questions. Do not present a generic questionnaire.\n"
            "- Do not invent requirements. Keep facts concise and user-authored. Preserve prior facts unless the user "
            "revises them. Every explicit project fact from the user must appear in the appropriate requirements, "
            "constraints, requested_outputs, validation_criteria, or assumptions list; the summary alone is not enough.\n"
            "- Set readiness to needs_clarification only when a blocking question remains, ready when the user explicitly "
            "indicates the brief is complete enough to build, otherwise draft.\n\n"
            f"Turn input:\n{json.dumps(turn_input, ensure_ascii=False, indent=2)}"
        )

    def update(
        self,
        request: ContextGatheringRequest,
        previous: DesignBrief | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
    ) -> tuple[DesignBriefCreate | None, str, list[str]]:
        image_bytes, image_mime_type = _first_inline_image(request.attachments)
        turn = self.llm_provider.generate_structured(
            self._prompt(request, previous, messages),
            ContextAgentTurn,
            image_bytes,
            image_mime_type,
        )
        if turn.tool == "respond":
            return None, turn.assistant_message, list(previous.unresolved_questions) if previous else []

        assert turn.brief is not None
        references = list(previous.references) if previous else []
        references_by_id = {item.reference_id: item for item in references}
        for attachment in request.attachments:
            item = _reference(attachment)
            references_by_id[item.reference_id] = item

        state = turn.brief
        questions = _unique(state.unresolved_questions)
        brief = DesignBriefCreate(
            schema_version=DESIGN_BRIEF_SCHEMA_VERSION,
            conversation_id=request.conversation_id,
            intent=state.intent.strip(),
            summary=state.summary.strip(),
            requirements=_unique(state.requirements),
            constraints=_unique(state.constraints),
            references=list(references_by_id.values()),
            requested_outputs=_unique(state.requested_outputs),
            validation_criteria=_unique(state.validation_criteria),
            unresolved_questions=questions,
            assumptions=_unique(state.assumptions),
            readiness=state.readiness,
        )
        return brief, turn.assistant_message.strip(), questions
