from __future__ import annotations

import re
from datetime import datetime, timezone

from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.readiness.models import (
    ReadinessBlocker,
    ReadinessBlockerCategory,
    ReadinessResult,
    ReadinessStatus,
)


CRITICAL_QUESTION_PATTERNS: tuple[tuple[ReadinessBlockerCategory, re.Pattern[str]], ...] = (
    (ReadinessBlockerCategory.SAFETY, re.compile(
        r"\b(safe|safety|hazard|protection|emergency|mains|medical|flammab|pressure limit|current limit)\b",
        re.IGNORECASE,
    )),
    (ReadinessBlockerCategory.DIMENSIONAL, re.compile(
        r"\b(dimension\w*|size|fit|clearance\w*|tolerance\w*|length|width|height|diameter|footprint|mounting)\b",
        re.IGNORECASE,
    )),
    (ReadinessBlockerCategory.ELECTRICAL, re.compile(
        r"\b(electrical|voltage|current|power|rail|battery|adapter|usb|connector|wire|wiring|gpio|controller|motor|stall)\b",
        re.IGNORECASE,
    )),
    (ReadinessBlockerCategory.MATERIAL, re.compile(
        r"\b(material|temperature|chemical|biocompat|waterproof|weatherproof|corrosion|food.safe)\b",
        re.IGNORECASE,
    )),
    (ReadinessBlockerCategory.MANUFACTURING, re.compile(
        r"\b(manufactur|fabricat|tooling|assembly method|3d print|injection mold|pcb stack|process)\b",
        re.IGNORECASE,
    )),
)


def _question_blocker(index: int, question: str) -> ReadinessBlocker:
    for category, pattern in CRITICAL_QUESTION_PATTERNS:
        if pattern.search(question):
            return ReadinessBlocker(
                code=f"critical_{category.value}_unknown",
                category=category,
                message=question,
                critical=True,
                source=f"unresolved_questions[{index}]",
            )
    return ReadinessBlocker(
        code="unresolved_context_question",
        category=ReadinessBlockerCategory.OTHER,
        message=question,
        critical=False,
        source=f"unresolved_questions[{index}]",
    )


def evaluate_readiness(brief: DesignBrief) -> ReadinessResult:
    blockers: list[ReadinessBlocker] = []
    if not brief.requirements:
        blockers.append(ReadinessBlocker(
            code="requirements_missing",
            category=ReadinessBlockerCategory.REQUIREMENTS,
            message="At least one concrete product requirement is required.",
            critical=False,
            source="requirements",
        ))
    if not brief.requested_outputs:
        blockers.append(ReadinessBlocker(
            code="requested_outputs_missing",
            category=ReadinessBlockerCategory.OUTPUTS,
            message="Specify at least one output to produce in the build.",
            critical=False,
            source="requested_outputs",
        ))
    if not brief.validation_criteria:
        blockers.append(ReadinessBlocker(
            code="validation_criteria_missing",
            category=ReadinessBlockerCategory.VALIDATION,
            message="Define at least one criterion for validating the result.",
            critical=False,
            source="validation_criteria",
        ))
    blockers.extend(_question_blocker(index, question) for index, question in enumerate(brief.unresolved_questions))

    if any(blocker.critical for blocker in blockers):
        status = ReadinessStatus.BLOCKED
        reasons = ["Critical project unknowns must be resolved before execution can start."]
    elif blockers:
        status = ReadinessStatus.NOT_READY
        reasons = ["The brief is incomplete but contains no critical execution blocker."]
    else:
        status = ReadinessStatus.READY
        reasons = ["The brief contains requirements, requested outputs, validation criteria, and no unresolved questions."]
    return ReadinessResult(
        project_id=brief.project_id,
        design_brief_id=brief.design_brief_id,
        brief_version=brief.brief_version,
        status=status,
        reasons=reasons,
        unresolved_blockers=blockers,
        evaluated_at=datetime.now(timezone.utc),
    )
