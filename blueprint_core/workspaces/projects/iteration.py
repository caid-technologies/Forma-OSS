from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from blueprint_core.llm import (
    LLMProviderConfigError,
    LLMProviderOutputError,
    LLMProviderValidation,
    LLMRuntimeConfig,
    StructuredLLMProvider,
    build_llm_provider,
    resolve_llm_runtime_config,
)
from blueprint_core.workspaces.projects.models import HardwareIR
from blueprint_core.workspaces.projects.objects import (
    DEFAULT_PROJECT_NAMESPACES,
    attach_project_object_metadata,
    normalize_project_namespace,
    namespace_payload,
)
from blueprint_core.validation import build_validation_summary, validate_circuit


logger = logging.getLogger(__name__)

PLACEHOLDER_TEXT_VALUES = {"", "unknown", "n/a", "na", "none", "null", "new", "new__rewrite_1"}
DEFAULT_CONTEXT_MAX_STRING_CHARS = 4000
PROTECTED_PROJECT_PATCH_ROOTS = frozenset({
    "assembly_metadata",
    "is_valid",
    "project_version_history",
    "validation",
})


class ProjectPatchOperation(BaseModel):
    """One deterministic mutation against the current HardwareIR document."""

    action: Literal["set", "append", "remove"] = Field(
        ...,
        description=(
            "Mutation type. set replaces an existing value, append adds one item to an existing list, "
            "and remove deletes an existing value or list item."
        ),
    )
    path: str = Field(
        ...,
        description="RFC 6901 JSON Pointer into the HardwareIR document, for example /overview/description.",
    )
    value_json: str = Field(
        ...,
        description="JSON-encoded mutation value. Use an empty string for remove operations.",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/") or normalized == "/":
            raise ValueError("patch path must be a non-root RFC 6901 JSON Pointer.")
        return normalized

    @model_validator(mode="after")
    def validate_encoded_value(self) -> "ProjectPatchOperation":
        if self.action == "remove":
            if self.value_json:
                raise ValueError("remove operations must use an empty value_json string.")
            return self
        try:
            json.loads(self.value_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"value_json must contain complete, valid JSON: {exc.msg}.") from exc
        return self


class ProjectIterationPatch(BaseModel):
    """Compact model output for revising selected parts of an existing project."""

    summary: str = Field(
        ...,
        min_length=1,
        description="Concise description of the project changes made by this patch.",
    )
    operations: list[ProjectPatchOperation] = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Ordered project mutations. Include every coordinated hardware and documentation change.",
    )


PROJECT_ITERATION_DOMAIN_ROOTS: dict[str, frozenset[str]] = {
    "product.overview": frozenset({"overview", "requirements", "constraints"}),
    "product.electrical": frozenset({
        "components",
        "nets",
        "buses",
        "pin_mappings",
        "power_rails",
        "estimated_current_draw_ma",
    }),
    "product.mech": frozenset({"mechanical", "fabrication_notes"}),
    "product.assembly": frozenset({"assembly"}),
}
PROJECT_ITERATION_DOMAIN_ORDER = tuple(PROJECT_ITERATION_DOMAIN_ROOTS)
PROJECT_ITERATION_DERIVED_NAMESPACES: dict[str, tuple[str, ...]] = {
    "product.overview": (),
    "product.electrical": ("product.bom", "product.firmware", "product.validation"),
    "product.mech": ("product.visuals",),
    "product.assembly": ("project.docs",),
}
ProjectIterationDomain = Literal[
    "product.overview",
    "product.electrical",
    "product.mech",
    "product.assembly",
]


class ProjectIterationDomainTask(BaseModel):
    """One bounded change assigned by the planner to a domain specialist."""

    namespace: ProjectIterationDomain
    instruction: str = Field(
        ...,
        min_length=1,
        description="Domain-specific change needed to fulfill the user's iteration request.",
    )

    @field_validator("instruction")
    @classmethod
    def normalize_instruction(cls, value: str) -> str:
        return value.strip()


class ProjectIterationPlan(BaseModel):
    """Small routing plan; domain agents produce the actual project patches."""

    summary: str = Field(..., min_length=1, description="Concise statement of the complete requested revision.")
    tasks: list[ProjectIterationDomainTask] = Field(
        ...,
        min_length=1,
        max_length=len(PROJECT_ITERATION_DOMAIN_ROOTS),
        description="Only the domain specialists required for this revision, one task per namespace.",
    )

    @model_validator(mode="after")
    def require_unique_domains(self) -> "ProjectIterationPlan":
        namespaces = [task.namespace for task in self.tasks]
        if len(namespaces) != len(set(namespaces)):
            raise ValueError("iteration plan must contain at most one task per domain namespace.")
        return self


@dataclass(frozen=True)
class ProjectIterationMetadata:
    """Debuggable summary of one project iteration operation."""

    mode: str
    revision: int
    previous_revision: int
    instruction: str
    provider: str
    model: Optional[str]
    live_generation_enabled: bool
    target_namespace: Optional[str] = None
    validation_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "revision": self.revision,
            "previous_revision": self.previous_revision,
            "instruction": self.instruction,
            "provider": self.provider,
            "model": self.model,
            "live_generation_enabled": self.live_generation_enabled,
            "target_namespace": self.target_namespace,
            "validation_error": self.validation_error,
        }


@dataclass(frozen=True)
class ProjectSelfCorrectionPlan:
    target_namespace: str
    instruction: str
    critical_issue_count: int
    warning_issue_count: int
    output_issue_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target_namespace": self.target_namespace,
            "instruction": self.instruction,
            "critical_issue_count": self.critical_issue_count,
            "warning_issue_count": self.warning_issue_count,
            "output_issue_count": self.output_issue_count,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def coerce_hardware_ir(value: HardwareIR | Dict[str, Any]) -> HardwareIR:
    if isinstance(value, HardwareIR):
        return value.model_copy(deep=True)
    if isinstance(value, dict):
        return HardwareIR.model_validate(value)
    raise TypeError("current project must be a HardwareIR or hardware IR dictionary.")


def normalize_iteration_instruction(value: str) -> str:
    instruction = (value or "").strip()
    if not instruction:
        raise ValueError("Iteration instruction is required.")
    return instruction


def _metadata_revision(ir: HardwareIR) -> int:
    metadata = ir.assembly_metadata or {}
    raw_value = metadata.get("revision")
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        history_count = len(ir.project_version_history or [])
        return max(1, history_count)


def next_revision_number(ir: HardwareIR) -> int:
    return _metadata_revision(ir) + 1


def _project_id_from_metadata(ir: HardwareIR, override: Optional[str] = None) -> str:
    value = override or (ir.assembly_metadata or {}).get("project_id")
    if value:
        try:
            return str(uuid.UUID(str(value).strip()))
        except (TypeError, ValueError, AttributeError):
            pass
    return str(uuid.uuid4())


def _is_placeholder_text(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_TEXT_VALUES


def _redact_context_value(value: Any, *, key: str = "", max_string_chars: int = DEFAULT_CONTEXT_MAX_STRING_CHARS) -> Any:
    lowered_key = key.lower()
    if isinstance(value, dict):
        return {
            item_key: _redact_context_value(item_value, key=item_key, max_string_chars=max_string_chars)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_context_value(item, max_string_chars=max_string_chars) for item in value]
    if isinstance(value, str):
        if ("image" in lowered_key or "data" in lowered_key) and value.startswith("data:"):
            return f"<redacted data url: {len(value)} chars>"
        if len(value) > max_string_chars:
            return value[:max_string_chars] + f"...<truncated {len(value) - max_string_chars} chars>"
    return value


def compact_hardware_ir_for_iteration(ir: HardwareIR, *, max_string_chars: int = DEFAULT_CONTEXT_MAX_STRING_CHARS) -> Dict[str, Any]:
    """Return an LLM-safe project context with large data URLs and huge fields compacted."""
    return _redact_context_value(ir.model_dump(mode="json", exclude_none=True), max_string_chars=max_string_chars)


def _domain_for_target_namespace(namespace: str) -> ProjectIterationDomain:
    normalized = normalize_project_namespace(namespace)
    aliases: dict[str, ProjectIterationDomain] = {
        "product.overview": "product.overview",
        "product.electrical": "product.electrical",
        "product.bom": "product.electrical",
        "product.firmware": "product.electrical",
        "product.validation": "product.electrical",
        "product.mech": "product.mech",
        "product.visuals": "product.mech",
        "product.assembly": "product.assembly",
        "project.docs": "product.assembly",
    }
    domain = aliases.get(normalized or "")
    if domain is None:
        raise ValueError(f"Project namespace {namespace!r} is not mutable through project iteration.")
    return domain


def compact_project_interfaces_for_iteration(ir: HardwareIR) -> Dict[str, Any]:
    """Return only the cross-domain contracts specialists need to coordinate."""
    overview = ir.overview.model_dump(mode="json") if ir.overview else None
    requirements = ir.requirements.model_dump(mode="json") if ir.requirements else None
    components = [
        {
            "ref_des": component.ref_des,
            "part_number": component.part_number,
            "name": component.name,
            "category": component.category,
        }
        for component in ir.components
    ]
    nets = [
        {
            "net_id": net.net_id,
            "name": net.name,
            "net_type": net.net_type,
            "voltage": net.voltage,
            "connected_refs": sorted({pin.ref_des for pin in net.pins}),
        }
        for net in ir.nets
    ]
    mechanical = None
    if ir.mechanical:
        mechanical = {
            "enclosure_type": ir.mechanical.enclosure_type,
            "render_dimensions": (
                ir.mechanical.render_dimensions.model_dump(mode="json")
                if ir.mechanical.render_dimensions
                else None
            ),
            "placements": [
                {
                    "ref_des": placement.ref_des,
                    "layer": placement.layer,
                    "mounting_face": placement.mounting_face,
                }
                for placement in ir.mechanical.component_placements
            ],
        }
    return {
        "overview": overview,
        "requirements": requirements,
        "component_interfaces": components,
        "net_interfaces": nets,
        "mechanical_interfaces": mechanical,
    }


def project_iteration_domain_contract(namespace: ProjectIterationDomain) -> Dict[str, Any]:
    """Return exact field schemas only for roots owned by one domain agent."""
    return {
        root: TypeAdapter(HardwareIR.model_fields[root].annotation).json_schema()
        for root in sorted(PROJECT_ITERATION_DOMAIN_ROOTS[namespace])
    }


def _decode_json_pointer(path: str) -> list[str]:
    return [token.replace("~1", "/").replace("~0", "~") for token in path.split("/")[1:]]


def _patch_list_index(token: str, *, length: int, path: str) -> int:
    if not token.isdigit():
        raise LLMProviderOutputError(f"Project patch path {path!r} requires a non-negative list index.")
    index = int(token)
    if index >= length:
        raise LLMProviderOutputError(
            f"Project patch path {path!r} references list index {index}, but the list has {length} items."
        )
    return index


def _resolve_patch_value(document: Any, tokens: list[str], *, path: str) -> Any:
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise LLMProviderOutputError(f"Project patch path {path!r} does not exist.")
            current = current[token]
            continue
        if isinstance(current, list):
            current = current[_patch_list_index(token, length=len(current), path=path)]
            continue
        raise LLMProviderOutputError(f"Project patch path {path!r} traverses a scalar value.")
    return current


def _validate_patch_root(path: str, tokens: list[str]) -> None:
    root = tokens[0] if tokens else ""
    if root in PROTECTED_PROJECT_PATCH_ROOTS:
        raise LLMProviderOutputError(
            f"Project patch path {path!r} targets backend-owned field {root!r}."
        )
    if root not in HardwareIR.model_fields:
        raise LLMProviderOutputError(f"Project patch path {path!r} is not a HardwareIR field.")


def _validate_patch_domain_scope(patch: ProjectIterationPatch, namespace: ProjectIterationDomain) -> None:
    allowed_roots = PROJECT_ITERATION_DOMAIN_ROOTS[namespace]
    for operation in patch.operations:
        tokens = _decode_json_pointer(operation.path)
        root = tokens[0] if tokens else ""
        if root not in allowed_roots:
            raise LLMProviderOutputError(
                f"The {namespace} agent cannot patch root {root!r}; "
                f"allowed roots are {', '.join(sorted(allowed_roots))}."
            )


def apply_project_iteration_patch(
    current_ir: HardwareIR | Dict[str, Any],
    patch: ProjectIterationPatch | Dict[str, Any],
) -> HardwareIR:
    """Apply a compact model patch and validate the resulting complete HardwareIR."""
    base = coerce_hardware_ir(current_ir)
    normalized_patch = (
        patch
        if isinstance(patch, ProjectIterationPatch)
        else ProjectIterationPatch.model_validate(patch)
    )
    base_document = base.model_dump(mode="json")
    document = base.model_dump(mode="json")

    for operation_index, operation in enumerate(normalized_patch.operations, start=1):
        tokens = _decode_json_pointer(operation.path)
        _validate_patch_root(operation.path, tokens)
        try:
            if operation.action == "append":
                target = _resolve_patch_value(document, tokens, path=operation.path)
                if not isinstance(target, list):
                    raise LLMProviderOutputError(
                        f"Project patch append path {operation.path!r} does not target a list."
                    )
                target.append(json.loads(operation.value_json))
                continue

            parent = _resolve_patch_value(document, tokens[:-1], path=operation.path)
            leaf = tokens[-1]
            if isinstance(parent, dict):
                if leaf not in parent:
                    raise LLMProviderOutputError(f"Project patch path {operation.path!r} does not exist.")
                if operation.action == "remove":
                    del parent[leaf]
                else:
                    parent[leaf] = json.loads(operation.value_json)
                continue
            if isinstance(parent, list):
                index = _patch_list_index(leaf, length=len(parent), path=operation.path)
                if operation.action == "remove":
                    parent.pop(index)
                else:
                    parent[index] = json.loads(operation.value_json)
                continue
            raise LLMProviderOutputError(f"Project patch path {operation.path!r} has no mutable parent.")
        except json.JSONDecodeError as exc:
            raise LLMProviderOutputError(
                f"Project patch operation {operation_index} has invalid value_json: {exc.msg}."
            ) from exc

    try:
        revised = HardwareIR.model_validate(document)
    except Exception as exc:
        raise LLMProviderOutputError(f"Project patch produced an invalid HardwareIR: {exc}") from exc
    if revised.model_dump(mode="json") == base_document:
        raise LLMProviderOutputError("Project patch did not change the project.")
    return revised


def build_iteration_planner_prompt(
    current_ir: HardwareIR,
    instruction: str,
    *,
    original_prompt: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str:
    interfaces = compact_project_interfaces_for_iteration(current_ir)
    domain_descriptions = {
        "product.overview": "product intent, requirements, power needs, constraints, and overview",
        "product.electrical": "components/BOM, motors or actuators, nets, buses, pins, and power rails",
        "product.mech": "enclosure, mechanisms, dimensions, placements, and fabrication",
        "product.assembly": "physical build sequence and assembly instructions",
    }
    return (
        "You are Forma's project iteration planner. Route the user's requested revision to small domain agents.\n"
        "Return one ProjectIterationPlan JSON document and no commentary.\n"
        "Create one task for every domain that must change for the request to be complete; omit unaffected domains.\n"
        "Do not design components, wiring, dimensions, or build steps in this plan. Domain agents do that work.\n"
        "Derived BOM views, validation, project history, and product visuals are refreshed by backend tools.\n"
        f"Available domain agents: {json.dumps(domain_descriptions, sort_keys=True)}\n"
        f"Project id: {project_id or (current_ir.assembly_metadata or {}).get('project_id') or 'unknown'}\n"
        f"Original project prompt: {original_prompt or 'unknown'}\n"
        f"User iteration request: {instruction}\n\n"
        "Current cross-domain interfaces:\n"
        f"{json.dumps(interfaces, indent=2, sort_keys=True)}"
    )


def build_domain_iteration_prompt(
    current_ir: HardwareIR,
    *,
    user_instruction: str,
    plan_summary: str,
    task: ProjectIterationDomainTask,
    original_prompt: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str:
    allowed_roots = sorted(PROJECT_ITERATION_DOMAIN_ROOTS[task.namespace])
    target_payload = namespace_payload(current_ir, task.namespace)
    interfaces = compact_project_interfaces_for_iteration(current_ir)
    domain_contract = project_iteration_domain_contract(task.namespace)
    return (
        f"You are Forma's {task.namespace} project iteration agent.\n"
        "Return one compact ProjectIterationPatch JSON document and no commentary.\n"
        "Each operation uses action set, append, or remove; an RFC 6901 JSON Pointer path; and value_json.\n"
        "value_json is a string containing complete JSON for the new value; use an empty string for remove.\n"
        "Use append only for an existing list. Use set for an existing scalar, object, or list item.\n"
        f"You may patch only these top-level HardwareIR roots: {', '.join(allowed_roots)}.\n"
        "Preserve stable IDs and all data outside your owned roots. Coordinate against the shared interfaces below.\n"
        f"Project id: {project_id or (current_ir.assembly_metadata or {}).get('project_id') or 'unknown'}\n"
        f"Original project prompt: {original_prompt or 'unknown'}\n"
        f"Complete user request: {user_instruction}\n"
        f"Planner summary: {plan_summary}\n"
        f"Your domain task: {task.instruction}\n\n"
        f"Current {task.namespace} payload:\n"
        f"{json.dumps(target_payload, indent=2, sort_keys=True)}\n\n"
        "Exact schemas for your owned HardwareIR roots:\n"
        f"{json.dumps(domain_contract, indent=2, sort_keys=True)}\n\n"
        "Current shared interfaces:\n"
        f"{json.dumps(interfaces, indent=2, sort_keys=True)}"
    )


def build_iteration_prompt(
    current_ir: HardwareIR,
    instruction: str,
    *,
    original_prompt: Optional[str] = None,
    project_id: Optional[str] = None,
    target_namespace: Optional[str] = None,
) -> str:
    compact_ir = compact_hardware_ir_for_iteration(current_ir)
    previous_revision = _metadata_revision(current_ir)
    next_revision = previous_revision + 1
    normalized_namespace = normalize_project_namespace(target_namespace)
    allowed_roots = sorted(set(HardwareIR.model_fields) - PROTECTED_PROJECT_PATCH_ROOTS)
    namespace_block = ""
    if normalized_namespace:
        namespace_block = (
            f"\nTarget namespace: {normalized_namespace}\n"
            "Focus the requested change on this namespace. Preserve other namespaces unless they must change to keep the project coherent.\n"
            "Current target namespace payload:\n"
            f"{json.dumps(namespace_payload(current_ir, normalized_namespace), indent=2, sort_keys=True)}\n"
        )
    return (
        "You are Forma's project iteration engine. Revise an existing HardwareIR project.\n"
        "Return one compact ProjectIterationPatch JSON document, not the complete project and not markdown.\n"
        "Each operation must use action set, append, or remove; an RFC 6901 JSON Pointer path; and value_json.\n"
        "value_json is a string containing the JSON encoding of the new value. Use an empty string for remove.\n"
        "Use set for an existing property or list item, append for one new item in an existing list, and remove for an existing property or list item.\n"
        f"Allowed top-level path fields: {', '.join(allowed_roots)}.\n"
        "Do not patch assembly_metadata, project_version_history, validation, or is_valid; the backend owns those fields.\n"
        "Preserve every part of the project that the instruction does not explicitly change.\n"
        "Keep the existing project_id, reference designators, and stable net IDs unless a requested change requires updates.\n"
        "If you add, remove, or replace components, update components, nets, buses, pin_mappings, power_rails, "
        "requirements, assembly steps, mechanical placement, cost inputs, and fabrication notes together.\n"
        "Never claim unsupported functionality without adding the required component and wiring changes.\n"
        f"The backend will set revision {next_revision}, append history, and recalculate validation after applying your patch.\n\n"
        f"Project id: {project_id or (current_ir.assembly_metadata or {}).get('project_id') or 'unknown'}\n"
        f"Original prompt: {original_prompt or 'unknown'}\n"
        f"Iteration instruction: {instruction}\n\n"
        f"{namespace_block}"
        "Current HardwareIR JSON:\n"
        f"{json.dumps(compact_ir, indent=2, sort_keys=True)}"
    )


def build_iteration_patch_repair_prompt(
    original_prompt: str,
    invalid_patch: ProjectIterationPatch | Dict[str, Any],
    validation_error: Exception,
) -> str:
    """Ask the provider to correct a patch that does not fit the current IR."""
    normalized_patch = (
        invalid_patch
        if isinstance(invalid_patch, ProjectIterationPatch)
        else ProjectIterationPatch.model_validate(invalid_patch)
    )
    return (
        f"{original_prompt}\n\n"
        "Your previous patch was valid JSON but could not be applied to the current HardwareIR.\n"
        f"Patch validation error: {validation_error}\n"
        "Previous invalid patch:\n"
        f"{json.dumps(normalized_patch.model_dump(mode='json'), indent=2, sort_keys=True)}\n\n"
        "Return one corrected ProjectIterationPatch JSON document. Do not return commentary. "
        "Match each operation to the current value type: append only to an existing list; "
        "use set to replace an existing scalar, object, or list item. Preserve the requested change "
        "and all coordinated updates from the original instruction."
    )


def _append_history_entry(
    ir: HardwareIR,
    *,
    instruction: str,
    revision: int,
    mode: str,
    provider: str,
    model: Optional[str],
    previous_revision: int,
) -> None:
    version = f"0.{revision}"
    history = [
        dict(item)
        for item in (ir.project_version_history or [])
        if isinstance(item, dict)
        and item.get("revision") != revision
        and item.get("version") != version
    ]
    history.append(
        {
            "version": version,
            "revision": revision,
            "previous_revision": previous_revision,
            "description": instruction,
            "change_type": "iteration",
            "mode": mode,
            "provider": provider,
            "model": model,
            "created_at": utc_now(),
        }
    )
    ir.project_version_history = history


def _metadata_value_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def _should_preserve_output_metadata_key(key: str) -> bool:
    if key in {
        "external_research",
        "firecrawl_research",
        "operation_statuses",
        "operation_summary",
        "source_usage",
        "tavily_research",
    }:
        return True
    return (
        key.startswith("image_output")
        or key.startswith("product_image")
        or key.startswith("product_case_image")
        or key.startswith("product_inside_image")
        or key.startswith("product_visual")
        or key.startswith("reference_image")
    )


def _preserve_output_metadata(metadata: Dict[str, Any], base_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Carry forward generated artifacts/source metadata when an iteration omits bulky output fields."""
    preserved = dict(metadata)
    for key, value in base_metadata.items():
        if not _should_preserve_output_metadata_key(str(key)):
            continue
        if key not in preserved or _metadata_value_missing(preserved.get(key)):
            preserved[key] = value
    return preserved


def _namespace_versions_for_iteration(
    *,
    base_ir: HardwareIR,
    current_metadata: Dict[str, Any],
    revision: int,
    previous_revision: int,
    target_namespace: Optional[str],
    affected_namespaces: Optional[list[str]] = None,
) -> Dict[str, int]:
    base_object = (base_ir.assembly_metadata or {}).get("project_object")
    base_versions = base_object.get("namespace_versions") if isinstance(base_object, dict) else None
    current_object = current_metadata.get("project_object")
    current_versions = current_object.get("namespace_versions") if isinstance(current_object, dict) else None
    namespace_names = list(DEFAULT_PROJECT_NAMESPACES.names)
    for source in (base_versions, current_versions):
        if isinstance(source, dict):
            for namespace in source:
                normalized = normalize_project_namespace(str(namespace))
                if normalized and normalized not in namespace_names:
                    namespace_names.append(normalized)

    normalized_affected = [
        namespace
        for namespace in (
            normalize_project_namespace(value)
            for value in (affected_namespaces or ([target_namespace] if target_namespace else []))
        )
        if namespace
    ]
    if normalized_affected:
        versions = {namespace: previous_revision for namespace in namespace_names}
        if isinstance(base_versions, dict):
            for namespace, raw_value in base_versions.items():
                normalized = normalize_project_namespace(str(namespace))
                if not normalized:
                    continue
                try:
                    versions[normalized] = max(1, int(raw_value))
                except (TypeError, ValueError):
                    versions[normalized] = previous_revision
        for namespace in normalized_affected:
            versions[namespace] = revision
        return versions

    return {namespace: revision for namespace in namespace_names}


def _normalize_iteration_metadata(
    ir: HardwareIR,
    *,
    base_ir: HardwareIR,
    instruction: str,
    mode: str,
    provider_validation: LLMProviderValidation,
    project_id: Optional[str],
    target_namespace: Optional[str],
    affected_namespaces: Optional[list[str]] = None,
) -> ProjectIterationMetadata:
    previous_revision = _metadata_revision(base_ir)
    revision = previous_revision + 1
    normalized_project_id = _project_id_from_metadata(base_ir, project_id)
    actual_model = provider_validation.actual_model or provider_validation.requested_model
    normalized_namespace = normalize_project_namespace(target_namespace)
    normalized_affected = sorted(
        {"project.history", "project.meta"}
        | {
            namespace
            for namespace in (
                normalize_project_namespace(value)
                for value in (affected_namespaces or ([normalized_namespace] if normalized_namespace else []))
            )
            if namespace
        }
    )
    metadata = dict(ir.assembly_metadata or {})
    base_metadata = dict(base_ir.assembly_metadata or {})
    metadata = _preserve_output_metadata(metadata, base_metadata)
    if (
        _metadata_value_missing(metadata.get("chat_id"))
        and not _metadata_value_missing(base_metadata.get("chat_id"))
    ):
        metadata["chat_id"] = base_metadata["chat_id"]
    metadata.update(
        {
            "project_id": normalized_project_id,
            "revision": revision,
            "previous_revision": previous_revision,
            "iterated_at": utc_now(),
            "iteration_instruction": instruction,
            "iteration_target_namespace": normalized_namespace,
            "iteration_affected_namespaces": normalized_affected,
            "iteration_mode": mode,
            "iteration_provider": provider_validation.provider,
            "iteration_model": actual_model,
            "iteration_live_generation_enabled": provider_validation.live_generation_enabled,
            "iteration_validation_error": provider_validation.validation_error,
            "last_iteration": {
                "instruction": instruction,
                "mode": mode,
                "target_namespace": normalized_namespace,
                "affected_namespaces": normalized_affected,
                "previous_revision": previous_revision,
                "revision": revision,
                "provider": provider_validation.provider,
                "model": actual_model,
                "created_at": utc_now(),
            },
        }
    )
    object_metadata = dict(metadata.get("project_object") or {})
    object_metadata["namespace_versions"] = _namespace_versions_for_iteration(
        base_ir=base_ir,
        current_metadata=metadata,
        revision=revision,
        previous_revision=previous_revision,
        target_namespace=normalized_namespace,
        affected_namespaces=normalized_affected,
    )
    metadata["project_object"] = object_metadata
    ir.assembly_metadata = metadata
    object_ir = attach_project_object_metadata(ir, target_namespace=normalized_namespace)
    ir.assembly_metadata = object_ir.assembly_metadata
    _append_history_entry(
        ir,
        instruction=instruction,
        revision=revision,
        mode=mode,
        provider=provider_validation.provider,
        model=actual_model,
        previous_revision=previous_revision,
    )
    return ProjectIterationMetadata(
        mode=mode,
        revision=revision,
        previous_revision=previous_revision,
        instruction=instruction,
        provider=provider_validation.provider,
        model=actual_model,
        live_generation_enabled=provider_validation.live_generation_enabled,
        target_namespace=normalized_namespace,
        validation_error=provider_validation.validation_error,
    )


def finalize_project_iteration(
    revised_ir: HardwareIR | Dict[str, Any],
    *,
    base_ir: HardwareIR | Dict[str, Any],
    instruction: str,
    provider_validation: LLMProviderValidation,
    project_id: Optional[str] = None,
    target_namespace: Optional[str] = None,
    affected_namespaces: Optional[list[str]] = None,
    mode: str = "llm",
) -> HardwareIR:
    base = coerce_hardware_ir(base_ir)
    revised = coerce_hardware_ir(revised_ir)
    instruction = normalize_iteration_instruction(instruction)

    if revised.overview and (_is_placeholder_text(revised.overview.title) or _is_placeholder_text(revised.overview.description)):
        raise LLMProviderOutputError(
            "Project iteration output was unusable: the selected model returned placeholder overview fields "
            f"(title={revised.overview.title!r}, description={revised.overview.description!r})."
        )

    issues = validate_circuit(revised.components, revised.nets, revised.requirements)
    revised.validation = build_validation_summary(issues)
    revised.is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in issues)
    _normalize_iteration_metadata(
        revised,
        base_ir=base,
        instruction=instruction,
        mode=mode,
        provider_validation=provider_validation,
        project_id=project_id,
        target_namespace=target_namespace,
        affected_namespaces=affected_namespaces,
    )
    return revised


def build_metadata_only_iteration(
    current_ir: HardwareIR | Dict[str, Any],
    instruction: str,
    *,
    provider_validation: LLMProviderValidation,
    project_id: Optional[str] = None,
    target_namespace: Optional[str] = None,
) -> HardwareIR:
    """Record an iteration request without pretending hardware content changed."""
    base = coerce_hardware_ir(current_ir)
    revised = base.model_copy(deep=True)
    metadata = dict(revised.assembly_metadata or {})
    requested = metadata.get("pending_iteration_instructions")
    pending = [item for item in requested if isinstance(item, dict)] if isinstance(requested, list) else []
    pending.append(
        {
            "instruction": normalize_iteration_instruction(instruction),
            "target_namespace": normalize_project_namespace(target_namespace),
            "created_at": utc_now(),
        }
    )
    metadata["pending_iteration_instructions"] = pending
    revised.assembly_metadata = metadata
    return finalize_project_iteration(
        revised,
        base_ir=base,
        instruction=instruction,
        provider_validation=provider_validation,
        project_id=project_id,
        target_namespace=target_namespace,
        mode="metadata-only",
    )


def _metadata_output_findings(ir: HardwareIR) -> list[str]:
    metadata = dict(ir.assembly_metadata or {})
    findings: list[str] = []

    external_research = metadata.get("external_research")
    if isinstance(external_research, dict):
        provider = str(external_research.get("provider") or "external source")
        error = external_research.get("error")
        source_count = external_research.get("source_count")
        configured = bool(external_research.get("configured"))
        if error:
            findings.append(f"External source research via {provider} reported an error: {error}")
        if configured and provider in {"firecrawl", "tavily"} and int(source_count or 0) == 0:
            findings.append(f"External source research via {provider} produced zero usable source records.")

    image_status = metadata.get("image_output_status")
    if metadata.get("image_output_requested") and image_status != "succeeded":
        findings.append(
            "Image generation was requested but did not succeed"
            + (f": {metadata.get('image_output_error')}" if metadata.get("image_output_error") else ".")
        )
    if image_status == "succeeded" and metadata.get("image_output_error"):
        findings.append(f"Image metadata still contains a stale error after success: {metadata.get('image_output_error')}")
    if image_status == "succeeded" and not metadata.get("product_image_url") and not metadata.get("product_image_data"):
        findings.append("Image metadata says generation succeeded, but no primary product image URL/data is present.")
    if image_status == "succeeded" and int(metadata.get("product_visual_sequence_count") or 0) <= 0:
        findings.append("Image metadata says generation succeeded, but product_visual_sequence_count is empty.")

    for record in metadata.get("product_visual_sequence") or []:
        if not isinstance(record, dict):
            continue
        if record.get("storage_error"):
            view_id = record.get("view_id") or "unknown"
            findings.append(f"Generated image view {view_id!r} has a storage error: {record.get('storage_error')}")

    for operation in metadata.get("operation_statuses") or []:
        if not isinstance(operation, dict):
            continue
        status = str(operation.get("status") or "").lower()
        if status in {"failed", "pending"}:
            label = operation.get("label") or operation.get("id") or "operation"
            error = operation.get("error") or operation.get("reason") or "no detail"
            findings.append(f"Operation {label!r} is {status}: {error}")

    return findings


def _stored_validation_issues(ir: HardwareIR) -> list[Any]:
    validation = ir.validation
    return [
        *list(validation.critical or []),
        *list(validation.warning or []),
    ]


def _dedupe_validation_issues(issues: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (
            str(getattr(issue, "severity", "") or "").upper(),
            str(getattr(issue, "category", "") or ""),
            str(getattr(issue, "description", "") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


class ProjectIterationPlanner:
    """Routes one conversational change into bounded domain-agent tasks."""

    def __init__(self, llm_provider: StructuredLLMProvider) -> None:
        self.llm_provider = llm_provider

    def plan(
        self,
        current_ir: HardwareIR,
        instruction: str,
        *,
        original_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        target_namespace: Optional[str] = None,
    ) -> ProjectIterationPlan:
        if target_namespace:
            domain = _domain_for_target_namespace(target_namespace)
            return ProjectIterationPlan(
                summary=instruction,
                tasks=[ProjectIterationDomainTask(namespace=domain, instruction=instruction)],
            )

        prompt = build_iteration_planner_prompt(
            current_ir,
            instruction,
            original_prompt=original_prompt,
            project_id=project_id,
        )
        result = self.llm_provider.generate_structured(prompt, ProjectIterationPlan)
        plan = result if isinstance(result, ProjectIterationPlan) else ProjectIterationPlan.model_validate(result)
        task_by_namespace = {task.namespace: task for task in plan.tasks}
        ordered_tasks = [
            task_by_namespace[namespace]
            for namespace in PROJECT_ITERATION_DOMAIN_ORDER
            if namespace in task_by_namespace
        ]
        return plan.model_copy(update={"tasks": ordered_tasks})


class ProjectDomainIterationAgent:
    """Produces and applies one patch limited to a single HardwareIR domain."""

    def __init__(self, llm_provider: StructuredLLMProvider, task: ProjectIterationDomainTask) -> None:
        self.llm_provider = llm_provider
        self.task = task

    def apply(
        self,
        current_ir: HardwareIR,
        *,
        user_instruction: str,
        plan_summary: str,
        original_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> tuple[HardwareIR, str]:
        prompt = build_domain_iteration_prompt(
            current_ir,
            user_instruction=user_instruction,
            plan_summary=plan_summary,
            task=self.task,
            original_prompt=original_prompt,
            project_id=project_id,
        )
        patch_result = self.llm_provider.generate_structured(
            prompt,
            ProjectIterationPatch,
            image_bytes,
            image_mime_type,
        )
        patch = (
            patch_result
            if isinstance(patch_result, ProjectIterationPatch)
            else ProjectIterationPatch.model_validate(patch_result)
        )
        try:
            _validate_patch_domain_scope(patch, self.task.namespace)
            return apply_project_iteration_patch(current_ir, patch), patch.summary
        except LLMProviderOutputError as patch_error:
            logger.warning(
                "%s project iteration agent patch was not applicable; requesting one repair: %s",
                self.task.namespace,
                patch_error,
            )
            repair_prompt = build_iteration_patch_repair_prompt(prompt, patch, patch_error)
            repaired_result = self.llm_provider.generate_structured(
                repair_prompt,
                ProjectIterationPatch,
                image_bytes,
                image_mime_type,
            )
            repaired_patch = (
                repaired_result
                if isinstance(repaired_result, ProjectIterationPatch)
                else ProjectIterationPatch.model_validate(repaired_result)
            )
            _validate_patch_domain_scope(repaired_patch, self.task.namespace)
            return apply_project_iteration_patch(current_ir, repaired_patch), repaired_patch.summary


class ProjectIterator:
    """Provider-agnostic project revision engine for HardwareIR documents."""

    def __init__(
        self,
        *,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        runtime_config: Optional[LLMRuntimeConfig] = None,
        llm_provider: Optional[StructuredLLMProvider] = None,
        use_simulation: bool = False,
        require_live_generation: bool = False,
    ) -> None:
        self.runtime_config = runtime_config or resolve_llm_runtime_config(
            provider_name=provider_name,
            model_name=model_name,
        )
        self.llm_provider = llm_provider or build_llm_provider(runtime_config=self.runtime_config)
        self.use_simulation = use_simulation or not self.llm_provider.is_configured
        self.require_live_generation = require_live_generation

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        return self.llm_provider.validate_configured_model(raise_on_strict=raise_on_strict)

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            **self.validate_configured_model(raise_on_strict=False).as_debug_dict(),
            "runtime": self.runtime_config.as_debug_dict(),
            "operation": "project_iteration",
            "use_simulation": self.use_simulation,
        }

    def iterate_project(
        self,
        current_ir: HardwareIR | Dict[str, Any],
        instruction: str,
        *,
        original_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        target_namespace: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> HardwareIR:
        base = coerce_hardware_ir(current_ir)
        instruction = normalize_iteration_instruction(instruction)
        normalized_namespace = normalize_project_namespace(target_namespace)

        try:
            validation = self.validate_configured_model()
        except LLMProviderConfigError:
            raise

        if self.use_simulation or not validation.live_generation_enabled:
            if self.require_live_generation:
                raise LLMProviderConfigError(
                    "Project iteration requires a live LLM provider; CLI fallback output is disabled. "
                    "Configure the requested provider or pass --simulation explicitly."
                )
            logger.info("Project iteration using metadata-only mode: provider=%s model=%s", validation.provider, validation.actual_model)
            return build_metadata_only_iteration(
                base,
                instruction,
                provider_validation=validation,
                project_id=project_id,
                target_namespace=normalized_namespace,
            )

        try:
            plan = ProjectIterationPlanner(self.llm_provider).plan(
                base,
                instruction,
                original_prompt=original_prompt,
                project_id=project_id,
                target_namespace=normalized_namespace,
            )
            revised = base
            completed_agents: list[dict[str, str]] = []
            for task in plan.tasks:
                revised, patch_summary = ProjectDomainIterationAgent(self.llm_provider, task).apply(
                    revised,
                    user_instruction=instruction,
                    plan_summary=plan.summary,
                    original_prompt=original_prompt,
                    project_id=project_id,
                    image_bytes=image_bytes,
                    image_mime_type=image_mime_type,
                )
                completed_agents.append({
                    "namespace": task.namespace,
                    "instruction": task.instruction,
                    "summary": patch_summary,
                })
        except Exception as exc:
            raise LLMProviderOutputError(
                f"Project iteration failed for provider={validation.provider} model={validation.actual_model or validation.requested_model}: {exc}"
            ) from exc

        affected_namespaces = {
            namespace
            for task in plan.tasks
            for namespace in (task.namespace, *PROJECT_ITERATION_DERIVED_NAMESPACES[task.namespace])
        }
        if normalized_namespace:
            affected_namespaces.add(normalized_namespace)
        finalized = finalize_project_iteration(
            revised,
            base_ir=base,
            instruction=instruction,
            provider_validation=validation,
            project_id=project_id,
            target_namespace=normalized_namespace,
            affected_namespaces=sorted(affected_namespaces),
            mode="llm",
        )
        finalized.assembly_metadata["iteration_agent_flow"] = {
            "planner_summary": plan.summary,
            "domains": completed_agents,
        }
        return finalized


def iterate_project(
    current_ir: HardwareIR | Dict[str, Any],
    instruction: str,
    *,
    original_prompt: Optional[str] = None,
    project_id: Optional[str] = None,
    target_namespace: Optional[str] = None,
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
    runtime_config: Optional[LLMRuntimeConfig] = None,
    llm_provider: Optional[StructuredLLMProvider] = None,
    use_simulation: bool = False,
    require_live_generation: bool = False,
) -> HardwareIR:
    iterator = ProjectIterator(
        provider_name=provider_name,
        model_name=model_name,
        runtime_config=runtime_config,
        llm_provider=llm_provider,
        use_simulation=use_simulation,
        require_live_generation=require_live_generation,
    )
    return iterator.iterate_project(
        current_ir,
        instruction,
        original_prompt=original_prompt,
        project_id=project_id,
        target_namespace=target_namespace,
    )


__all__ = [
    "ProjectDomainIterationAgent",
    "ProjectIterationDomainTask",
    "ProjectIterationMetadata",
    "ProjectIterationPatch",
    "ProjectIterationPlan",
    "ProjectIterationPlanner",
    "ProjectIterator",
    "ProjectPatchOperation",
    "ProjectSelfCorrectionPlan",
    "apply_project_iteration_patch",
    "build_domain_iteration_prompt",
    "build_iteration_prompt",
    "build_iteration_patch_repair_prompt",
    "build_iteration_planner_prompt",
    "build_metadata_only_iteration",
    "compact_hardware_ir_for_iteration",
    "compact_project_interfaces_for_iteration",
    "coerce_hardware_ir",
    "finalize_project_iteration",
    "iterate_project",
    "next_revision_number",
    "normalize_iteration_instruction",
    "project_iteration_domain_contract",
]
