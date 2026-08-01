"""Structured evidence and inference contracts for artifact inspection."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


REVERSE_ENGINEERING_REPORT_SCHEMA_VERSION = "1.0"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReverseEngineeringFindingKind(str, Enum):
    STRUCTURE = "structure"
    FUNCTION = "function"
    PROPERTY = "property"


class ReverseEngineeringEvidenceSource(str, Enum):
    ARTIFACT = "artifact"
    DESIGN_BRIEF = "design_brief"


class ReverseEngineeringConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReverseEngineeringArtifactReference(BaseModel):
    """A bounded reference supplied to the worker; v1 supports inline raster images."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: NonEmptyString
    kind: NonEmptyString
    uri: NonEmptyString
    media_type: NonEmptyString
    label: NonEmptyString | None = None


class ReverseEngineeringEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: NonEmptyString
    source: ReverseEngineeringEvidenceSource
    observation: NonEmptyString
    method: NonEmptyString


class ReverseEngineeringFinding(BaseModel):
    """An inference linked to observations and explicit residual uncertainty."""

    model_config = ConfigDict(extra="forbid")

    finding_id: NonEmptyString
    kind: ReverseEngineeringFindingKind
    inference: NonEmptyString
    evidence_ids: list[NonEmptyString] = Field(min_length=1)
    confidence: ReverseEngineeringConfidence
    uncertainties: list[NonEmptyString] = Field(min_length=1)


class AnalyzedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: NonEmptyString
    kind: NonEmptyString
    media_type: NonEmptyString
    content_sha256: NonEmptyString
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)


class ReverseEngineeringReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: AnalyzedArtifact
    evidence: list[ReverseEngineeringEvidence] = Field(min_length=1)
    findings: list[ReverseEngineeringFinding] = Field(min_length=1)
    ambiguous: bool
    overall_uncertainties: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def require_linked_unique_findings(self) -> "ReverseEngineeringReportDraft":
        evidence_ids = [item.evidence_id for item in self.evidence]
        finding_ids = [item.finding_id for item in self.findings]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Reverse-engineering evidence_id values must be unique.")
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("Reverse-engineering finding_id values must be unique.")
        available_evidence = set(evidence_ids)
        dangling = sorted({
            evidence_id
            for finding in self.findings
            for evidence_id in finding.evidence_ids
            if evidence_id not in available_evidence
        })
        if dangling:
            raise ValueError(
                "Reverse-engineering findings reference unknown evidence: " + ", ".join(dangling)
            )
        return self


class ReverseEngineeringReport(ReverseEngineeringReportDraft):
    schema_version: Literal["1.0"] = REVERSE_ENGINEERING_REPORT_SCHEMA_VERSION
    project_id: UUID
    project_revision: int = Field(ge=1)
    design_brief_id: UUID
    design_brief_version: int = Field(ge=1)


__all__ = [
    "REVERSE_ENGINEERING_REPORT_SCHEMA_VERSION",
    "AnalyzedArtifact",
    "ReverseEngineeringArtifactReference",
    "ReverseEngineeringConfidence",
    "ReverseEngineeringEvidence",
    "ReverseEngineeringEvidenceSource",
    "ReverseEngineeringFinding",
    "ReverseEngineeringFindingKind",
    "ReverseEngineeringReport",
    "ReverseEngineeringReportDraft",
]
