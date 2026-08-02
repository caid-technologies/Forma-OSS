from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from blueprint_core.workspaces.design_briefs import DesignBrief
from blueprint_core.workspaces.workflow import ProjectWorkflow


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

    @model_validator(mode="after")
    def require_context_input(self) -> "ContextGatheringRequest":
        self.text = self.text.strip()
        if not self.text and not self.attachments:
            raise ValueError("Provide text or at least one attachment.")
        return self


class ContextGatheringResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: ProjectWorkflow
    design_brief: DesignBrief | None = None
    assistant_message: NonEmptyString
    questions: list[NonEmptyString] = Field(default_factory=list)
    action: Literal["respond", "update_design_brief", "build_project"]
    generation_prompt: NonEmptyString | None = None
