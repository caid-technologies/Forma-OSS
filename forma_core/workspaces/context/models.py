from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.workflow import ProjectWorkflow


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ContextAttachment(BaseModel):
    """A user-supplied reference available to the context-gathering agent."""

    model_config = ConfigDict(extra="forbid")

    attachment_id: NonEmptyString | None = None
    kind: Literal["image", "document"]
    name: NonEmptyString | None = None
    media_type: NonEmptyString | None = None
    uri: NonEmptyString | None = None
    data_url: NonEmptyString | None = None
    extracted_text: NonEmptyString | None = None
    source: Literal["upload", "clipboard", "url"] = "upload"

    @model_validator(mode="after")
    def require_attachment_content(self) -> "ContextAttachment":
        if not any((self.uri, self.data_url, self.extracted_text)):
            raise ValueError("An attachment requires uri, data_url, or extracted_text.")
        return self


class ContextGatheringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: NonEmptyString
    text: str = ""
    attachments: list[ContextAttachment] = Field(default_factory=list)
    requested_tool: Literal["build_project", "render_project", "iterate_project"] | None = None

    @model_validator(mode="after")
    def require_context_input(self) -> "ContextGatheringRequest":
        self.text = self.text.strip()
        if not self.text and not self.attachments and self.requested_tool is None:
            raise ValueError("Provide text or at least one attachment.")
        return self


class ContextBuildExecution(BaseModel):
    """Small, stable handle for a build launched from a conversational turn."""

    model_config = ConfigDict(extra="forbid")

    build_id: UUID
    plan_id: NonEmptyString
    job_id: NonEmptyString
    status: NonEmptyString


class ContextGatheringResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_kind: Literal["chat", "clarification", "context", "proceed"] = "context"
    tool_name: Literal["ask_question", "build_project", "render_project", "iterate_project"] = "ask_question"
    workflow: ProjectWorkflow | None = None
    design_brief: DesignBrief | None = None
    assistant_message: NonEmptyString
    questions: list[NonEmptyString] = Field(default_factory=list)
    build_execution: ContextBuildExecution | None = None


class ContextTurnDecision(BaseModel):
    """Reasoning-model decision for one unified conversational turn."""

    model_config = ConfigDict(extra="forbid")

    turn_kind: Literal["chat", "clarification", "context", "proceed"]
    tool_name: Literal["ask_question", "build_project", "render_project", "iterate_project"] = "ask_question"
    save_context: bool = False
    assistant_message: NonEmptyString
