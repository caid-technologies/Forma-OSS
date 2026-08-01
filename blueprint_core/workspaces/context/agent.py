from __future__ import annotations

import hashlib
import re

from blueprint_core.agents.clarification import ask_clarifying_questions
from blueprint_core.workspaces.context.models import ContextAttachment, ContextGatheringRequest
from blueprint_core.workspaces.design_briefs import (
    DESIGN_BRIEF_SCHEMA_VERSION,
    DesignBrief,
    DesignBriefCreate,
    DesignBriefReadiness,
    DesignBriefReference,
)
from blueprint_core.workspaces.projects.models import ClarifyingQuestionsRequest


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _sentences(text: str) -> list[str]:
    return _unique(re.split(r"(?:[\r\n]+|(?<=[.!?])\s+)", text.strip()))


def _intent(text: str, previous: DesignBrief | None) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("modify", "revise", "change", "iterate", "update")):
        return "modify a hardware design"
    if any(word in lowered for word in ("reverse engineer", "identify this", "recreate this")):
        return "reverse engineer a hardware reference"
    if any(word in lowered for word in ("validate", "review", "check this design")):
        return "validate a hardware design"
    if previous:
        return previous.intent
    return "design a buildable hardware product"


def _requested_outputs(text: str) -> list[str]:
    mappings = {
        "wiring": ("wire", "wiring", "pinout"),
        "schematic": ("schematic", "circuit diagram"),
        "bom": ("bom", "bill of materials", "parts list"),
        "firmware": ("firmware", "code", "software"),
        "enclosure": ("enclosure", "case", "housing"),
        "cad": ("cad", "step file", "stl", "3d model"),
        "product images": ("product image", "render", "concept image"),
        "validation": ("validation", "test plan", "verify"),
        "assembly instructions": ("assembly", "build guide", "instructions"),
    }
    lowered = text.casefold()
    return [output for output, markers in mappings.items() if any(marker in lowered for marker in markers)]


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


class ContextBriefUpdater:
    """Updates a DesignBrief without invoking a model, tool, or worker job."""

    def update(self, request: ContextGatheringRequest, previous: DesignBrief | None = None) -> tuple[DesignBriefCreate, str, list[str]]:
        text = request.text.strip()
        attachment_text = [item.extracted_text for item in request.attachments if item.extracted_text]
        combined_update = "\n".join([text, *attachment_text]).strip()
        update_sentences = _sentences(combined_update)

        prior_requirements = list(previous.requirements) if previous else []
        requirements = _unique([*prior_requirements, *update_sentences])
        constraint_markers = re.compile(
            r"\b(must|only|under|maximum|max\b|minimum|min\b|budget|fit|within|voltage|battery|usb|no\s+|without|weatherproof|waterproof|material)\b",
            re.IGNORECASE,
        )
        constraints = _unique([
            *(list(previous.constraints) if previous else []),
            *(sentence for sentence in update_sentences if constraint_markers.search(sentence)),
        ])
        assumption_markers = re.compile(r"\b(assume|assuming|probably|for now)\b", re.IGNORECASE)
        assumptions = _unique([
            *(list(previous.assumptions) if previous else []),
            *(sentence for sentence in update_sentences if assumption_markers.search(sentence)),
        ])
        validation_markers = re.compile(r"\b(success|validate|validation|test|verify|passes|works when)\b", re.IGNORECASE)
        validation = _unique([
            *(list(previous.validation_criteria) if previous else []),
            *(sentence for sentence in update_sentences if validation_markers.search(sentence)),
        ])

        references = list(previous.references) if previous else []
        references_by_id = {item.reference_id: item for item in references}
        for attachment in request.attachments:
            item = _reference(attachment)
            references_by_id[item.reference_id] = item

        prior_outputs = list(previous.requested_outputs) if previous else []
        requested_outputs = _unique([*prior_outputs, *_requested_outputs(combined_update)])
        full_context = "\n".join(_unique([*requirements, *constraints]))
        clarification = ask_clarifying_questions(ClarifyingQuestionsRequest(
            prompt=full_context,
            has_image=any(item.kind == "image" for item in request.attachments) or any(
                reference.kind == "uploaded_image" for reference in references_by_id.values()
            ),
            workflow="default",
            force=False,
            max_questions=3,
        ))
        questions = _unique([
            *(list(previous.unresolved_questions) if previous else []),
            *(question.question for question in clarification.questions),
        ])

        if previous and previous.summary:
            summary = previous.summary
        elif text:
            summary = text[:500]
        elif request.attachments:
            kinds = ", ".join(sorted({item.kind for item in request.attachments}))
            summary = f"Hardware design based on the supplied {kinds} reference."
        else:  # model validation makes this unreachable
            summary = "Hardware design context"

        brief = DesignBriefCreate(
            schema_version=DESIGN_BRIEF_SCHEMA_VERSION,
            conversation_id=request.conversation_id,
            intent=_intent(combined_update, previous),
            summary=summary,
            requirements=requirements,
            constraints=constraints,
            references=list(references_by_id.values()),
            requested_outputs=requested_outputs,
            validation_criteria=validation,
            unresolved_questions=questions,
            assumptions=assumptions,
            readiness=DesignBriefReadiness.NEEDS_CLARIFICATION if questions else DesignBriefReadiness.DRAFT,
        )
        if questions:
            assistant_message = "I’ve saved that context. " + " ".join(questions)
        else:
            assistant_message = "I’ve saved that context. Add any remaining constraints, references, or expected outputs when you’re ready."
        return brief, assistant_message, questions
