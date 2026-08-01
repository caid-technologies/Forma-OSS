"""Deterministic baseline checks for canonical project revisions."""

from __future__ import annotations

import re

from blueprint_core.workspaces.design_briefs import DesignBrief
from blueprint_core.workspaces.projects import ProjectRevision
from blueprint_core.workspaces.validation.models import (
    ValidationCheckStatus,
    ValidationFindingDraft,
    ValidationFindingKind,
    ValidationReportDraft,
    ValidationSeverity,
)


SUPPORTED_VALIDATION_CHECKS = frozenset({"constraints", "consistency", "assumptions", "criteria"})


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:64] or "check"


def _artifact_for(revision: ProjectRevision, *kinds: str) -> str | None:
    for kind in kinds:
        artifact = next((item for item in revision.artifacts if item.kind == kind), None)
        if artifact is not None:
            return artifact.artifact_id
    return revision.artifacts[0].artifact_id if revision.artifacts else None


def _finding(
    *,
    criterion_id: str,
    criterion: str,
    kind: ValidationFindingKind,
    status: ValidationCheckStatus,
    evidence: list[str],
    remediation: str,
    artifact_id: str | None,
) -> ValidationFindingDraft:
    severity = {
        ValidationCheckStatus.PASSED: ValidationSeverity.INFO,
        ValidationCheckStatus.WARNING: ValidationSeverity.WARNING,
        ValidationCheckStatus.FAILED: ValidationSeverity.ERROR,
        ValidationCheckStatus.SKIPPED: ValidationSeverity.INFO,
    }[status]
    return ValidationFindingDraft(
        criterion_id=criterion_id,
        criterion=criterion,
        kind=kind,
        status=status,
        severity=severity,
        affected_artifact_id=artifact_id,
        evidence=evidence,
        remediation=remediation,
    )


def _constraint_findings(revision: ProjectRevision, brief: DesignBrief) -> list[ValidationFindingDraft]:
    available = {
        value.strip().casefold()
        for value in [
            *revision.state.constraints,
            *(revision.state.requirements.physical_constraints if revision.state.requirements else []),
        ]
        if value.strip()
    }
    if not brief.constraints:
        return [_finding(
            criterion_id="constraints:none-declared",
            criterion="DesignBrief constraints are represented in project state",
            kind=ValidationFindingKind.CONSTRAINT,
            status=ValidationCheckStatus.SKIPPED,
            evidence=["The frozen DesignBrief declares no explicit constraints."],
            remediation="Declare constraints in a new DesignBrief version before revalidation.",
            artifact_id=_artifact_for(revision, "project-state"),
        )]
    findings: list[ValidationFindingDraft] = []
    for index, constraint in enumerate(brief.constraints, start=1):
        present = constraint.strip().casefold() in available
        findings.append(_finding(
            criterion_id=f"constraint:{index}:{_slug(constraint)}",
            criterion=constraint,
            kind=ValidationFindingKind.CONSTRAINT,
            status=ValidationCheckStatus.PASSED if present else ValidationCheckStatus.WARNING,
            evidence=(
                [f"Constraint is present in canonical project state: {constraint}"]
                if present
                else [f"Constraint is declared by DesignBrief but not represented verbatim in project state: {constraint}"]
            ),
            remediation=(
                "No action required."
                if present
                else "Represent the constraint explicitly in the next project revision or document an equivalent mapping."
            ),
            artifact_id=_artifact_for(revision, "project-state"),
        ))
    return findings


def _consistency_findings(revision: ProjectRevision) -> list[ValidationFindingDraft]:
    component_refs = [item.ref_des for item in revision.components]
    duplicates = sorted({value for value in component_refs if component_refs.count(value) > 1})
    known = set(component_refs)
    dangling = sorted({
        pin.ref_des
        for net in revision.state.nets
        for pin in net.pins
        if pin.ref_des not in known
    })
    if duplicates or dangling:
        evidence = []
        if duplicates:
            evidence.append(f"Duplicate component references: {', '.join(duplicates)}.")
        if dangling:
            evidence.append(f"Net pins reference unknown components: {', '.join(dangling)}.")
        return [_finding(
            criterion_id="consistency:component-references",
            criterion="Component and net references are internally consistent",
            kind=ValidationFindingKind.CONSISTENCY,
            status=ValidationCheckStatus.FAILED,
            evidence=evidence,
            remediation="Resolve duplicate or dangling component references in a new project revision.",
            artifact_id=_artifact_for(revision, "wiring", "project-state"),
        )]
    return [_finding(
        criterion_id="consistency:component-references",
        criterion="Component and net references are internally consistent",
        kind=ValidationFindingKind.CONSISTENCY,
        status=ValidationCheckStatus.PASSED,
        evidence=[f"Validated {len(component_refs)} component references and {len(revision.state.nets)} nets."],
        remediation="No action required.",
        artifact_id=_artifact_for(revision, "wiring", "project-state"),
    )]


def _assumption_findings(revision: ProjectRevision, brief: DesignBrief) -> list[ValidationFindingDraft]:
    findings: list[ValidationFindingDraft] = []
    for index, question in enumerate(brief.unresolved_questions, start=1):
        findings.append(_finding(
            criterion_id=f"assumption:unresolved:{index}:{_slug(question)}",
            criterion=question,
            kind=ValidationFindingKind.ASSUMPTION,
            status=ValidationCheckStatus.FAILED,
            evidence=[f"The frozen DesignBrief still marks this question unresolved: {question}"],
            remediation="Resolve the question in a new DesignBrief and regenerate or revise the project.",
            artifact_id=_artifact_for(revision, "project-state"),
        ))
    for index, assumption in enumerate(revision.assumptions, start=1):
        findings.append(_finding(
            criterion_id=f"assumption:declared:{index}:{_slug(assumption)}",
            criterion=assumption,
            kind=ValidationFindingKind.ASSUMPTION,
            status=ValidationCheckStatus.WARNING,
            evidence=[f"Project revision {revision.revision} depends on this recorded assumption: {assumption}"],
            remediation="Confirm the assumption with evidence or replace it in a new project revision.",
            artifact_id=_artifact_for(revision, "project-state"),
        ))
    if findings:
        return findings
    return [_finding(
        criterion_id="assumption:none-unresolved",
        criterion="No unresolved assumptions remain",
        kind=ValidationFindingKind.ASSUMPTION,
        status=ValidationCheckStatus.PASSED,
        evidence=["The revision and frozen DesignBrief contain no unresolved assumptions or questions."],
        remediation="No action required.",
        artifact_id=_artifact_for(revision, "project-state"),
    )]


def _criterion_finding(
    revision: ProjectRevision,
    criterion: str,
    index: int,
) -> ValidationFindingDraft:
    lowered = criterion.casefold()
    critical = list(revision.state.validation.critical or [])
    criterion_id = f"criterion:{index}:{_slug(criterion)}"
    if "critical" in lowered or "valid" in lowered:
        passed = revision.state.is_valid and not critical
        return _finding(
            criterion_id=criterion_id,
            criterion=criterion,
            kind=ValidationFindingKind.CRITERION,
            status=ValidationCheckStatus.PASSED if passed else ValidationCheckStatus.FAILED,
            evidence=(
                ["Project state is valid and contains no critical validation issues."]
                if passed
                else [f"Project state is_valid={revision.state.is_valid} with {len(critical)} critical issues."]
            ),
            remediation="No action required." if passed else "Resolve every critical validation issue and request revalidation.",
            artifact_id=_artifact_for(revision, "validation", "project-state"),
        )
    if "component" in lowered:
        passed = bool(revision.components)
        return _finding(
            criterion_id=criterion_id,
            criterion=criterion,
            kind=ValidationFindingKind.CRITERION,
            status=ValidationCheckStatus.PASSED if passed else ValidationCheckStatus.FAILED,
            evidence=[f"Canonical revision contains {len(revision.components)} components."],
            remediation="No action required." if passed else "Add the required components in a new project revision.",
            artifact_id=_artifact_for(revision, "bom", "project-state"),
        )
    if "voltage" in lowered or "power" in lowered:
        voltages = [item.voltage for item in revision.state.power_rails]
        if revision.state.requirements and revision.state.requirements.operating_voltage:
            voltages.append(revision.state.requirements.operating_voltage)
        if not voltages:
            return _finding(
                criterion_id=criterion_id,
                criterion=criterion,
                kind=ValidationFindingKind.CRITERION,
                status=ValidationCheckStatus.SKIPPED,
                evidence=["No structured power rail or operating voltage is available for this check."],
                remediation="Add structured voltage data or use a domain-specific electrical validator.",
                artifact_id=_artifact_for(revision, "wiring", "project-state"),
            )
        voltage_issues = [item for item in critical if "voltage" in item.category.casefold()]
        passed = not voltage_issues
        return _finding(
            criterion_id=criterion_id,
            criterion=criterion,
            kind=ValidationFindingKind.CRITERION,
            status=ValidationCheckStatus.PASSED if passed else ValidationCheckStatus.FAILED,
            evidence=[f"Structured voltages: {', '.join(str(value) for value in voltages)}; critical voltage issues: {len(voltage_issues)}."],
            remediation="No action required." if passed else "Resolve critical voltage findings and request revalidation.",
            artifact_id=_artifact_for(revision, "wiring", "project-state"),
        )
    return _finding(
        criterion_id=criterion_id,
        criterion=criterion,
        kind=ValidationFindingKind.CRITERION,
        status=ValidationCheckStatus.SKIPPED,
        evidence=["The baseline Validation worker does not implement this domain-specific criterion."],
        remediation="Route this criterion to a compatible domain validator or perform documented manual review.",
        artifact_id=_artifact_for(revision, "project-state"),
    )


def evaluate_project_revision(
    revision: ProjectRevision,
    design_brief: DesignBrief,
    requested_checks: list[str] | None = None,
) -> ValidationReportDraft:
    checks: list[str] = []
    seen_checks: set[str] = set()
    for requested in requested_checks or ["constraints", "consistency", "assumptions", "criteria"]:
        normalized = requested.strip().lower()
        if normalized not in seen_checks:
            checks.append(requested)
            seen_checks.add(normalized)
    findings: list[ValidationFindingDraft] = []
    for check in checks:
        normalized = check.strip().lower()
        if normalized == "constraints":
            findings.extend(_constraint_findings(revision, design_brief))
        elif normalized == "consistency":
            findings.extend(_consistency_findings(revision))
        elif normalized == "assumptions":
            findings.extend(_assumption_findings(revision, design_brief))
        elif normalized == "criteria":
            if design_brief.validation_criteria:
                findings.extend(
                    _criterion_finding(revision, criterion, index)
                    for index, criterion in enumerate(design_brief.validation_criteria, start=1)
                )
            else:
                findings.append(_finding(
                    criterion_id="criteria:none-declared",
                    criterion="Declared DesignBrief validation criteria",
                    kind=ValidationFindingKind.CRITERION,
                    status=ValidationCheckStatus.SKIPPED,
                    evidence=["The frozen DesignBrief declares no validation criteria."],
                    remediation="Declare validation criteria in a new DesignBrief version.",
                    artifact_id=_artifact_for(revision, "project-state"),
                ))
        else:
            findings.append(_finding(
                criterion_id=f"requested-check:{_slug(check)}",
                criterion=check,
                kind=ValidationFindingKind.REQUESTED_CHECK,
                status=ValidationCheckStatus.SKIPPED,
                evidence=[f"Requested check '{check}' is not supported by this Validation worker version."],
                remediation=f"Use one of the supported checks: {', '.join(sorted(SUPPORTED_VALIDATION_CHECKS))}.",
                artifact_id=_artifact_for(revision, "project-state"),
            ))
    return ValidationReportDraft(findings=findings)


__all__ = ["SUPPORTED_VALIDATION_CHECKS", "evaluate_project_revision"]
