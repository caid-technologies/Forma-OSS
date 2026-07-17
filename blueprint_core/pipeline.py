from __future__ import annotations

import contextlib
import contextvars
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterator, List, Optional

from blueprint_core.job_source_usage import DEFAULT_WORKFLOW_ID, WEB_RESEARCH_WORKFLOW_ID, normalize_generation_workflow_id


@dataclass(frozen=True)
class AgentPipelineStep:
    id: str
    agent: str
    label: str
    description: str
    duration_ms: int = 5500
    optional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentPipelineEvent:
    workflow: str
    step_id: str
    status: str
    agent: str
    label: str
    description: str
    observed_at: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PipelineEventCallback = Callable[[AgentPipelineEvent], None]
_PIPELINE_EVENT_CALLBACK: contextvars.ContextVar[Optional[PipelineEventCallback]] = contextvars.ContextVar(
    "blueprint_pipeline_event_callback",
    default=None,
)


DEFAULT_AGENT_PIPELINE_STEPS = [
    AgentPipelineStep(
        id="safety_guardrail",
        agent="Safety Guardrail",
        label="Checking safe build scope",
        description="Screening the request for low-voltage maker hardware constraints.",
        duration_ms=3500,
    ),
    AgentPipelineStep(
        id="context_clarifier",
        agent="Context Clarifier Agent",
        label="Clarifying build context",
        description="Checking whether user-provided answers should be folded into the generation prompt.",
        duration_ms=2500,
    ),
    AgentPipelineStep(
        id="intent_parser",
        agent="Intent Parser Agent",
        label="Parsing the hardware idea",
        description="Converting the prompt into a project title, category, and build intent.",
    ),
    AgentPipelineStep(
        id="requirements",
        agent="Requirements Agent",
        label="Extracting requirements",
        description="Capturing functions, voltage, physical constraints, safety notes, and missing information.",
    ),
    AgentPipelineStep(
        id="component_selection",
        agent="Component Selection Agent",
        label="Selecting compatible parts",
        description="Choosing catalog components and pin definitions that satisfy the requirements.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="wiring_netlist",
        agent="Wiring/Netlist Agent",
        label="Drafting nets and pin mappings",
        description="Connecting power, ground, buses, sensors, actuators, displays, and controller pins.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="validation_repair",
        agent="Validation + Auto-Correction Agent",
        label="Validating and repairing wiring",
        description="Checking for shorts, voltage mismatches, unpowered parts, and pin conflicts.",
        duration_ms=5500,
    ),
    AgentPipelineStep(
        id="bom",
        agent="BOM Agent",
        label="Calculating BOM and cost",
        description="Summing selected components and updating the project estimate.",
        duration_ms=3000,
    ),
    AgentPipelineStep(
        id="mechanical_fabrication",
        agent="Mechanical/Fabrication Agent",
        label="Designing enclosure and placement",
        description="Generating mounting, fabrication, CAD sourcing, and 3D render placement details.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="assembly",
        agent="Assembly Instruction Agent",
        label="Writing build steps",
        description="Producing sequential assembly instructions and safety flags.",
        duration_ms=5500,
    ),
    AgentPipelineStep(
        id="package_project",
        agent="Project Packager",
        label="Packaging project artifacts",
        description="Building the HardwareIR, diagrams, validation summary, and saved project record.",
        duration_ms=3500,
    ),
]


WEB_RESEARCH_AGENT_PIPELINE_STEPS = [
    AgentPipelineStep(
        id="safety_guardrail",
        agent="Safety Guardrail",
        label="Checking safe build scope",
        description="Screening the request for low-voltage maker hardware constraints.",
        duration_ms=3500,
    ),
    AgentPipelineStep(
        id="context_clarifier",
        agent="Context Clarifier Agent",
        label="Clarifying build context",
        description="Checking whether user-provided answers should be folded into sourced generation.",
        duration_ms=2500,
    ),
    AgentPipelineStep(
        id="external_research",
        agent="External Source Research Agent",
        label="Gathering source context",
        description="Searching for reference designs, components, datasheets, and build context.",
        duration_ms=7500,
    ),
    AgentPipelineStep(
        id="web_architect",
        agent="Web Research Hardware Architect Agent",
        label="Planning sourced architecture",
        description="Turning source context into requirements, architecture notes, and component roles.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="web_component_sourcing",
        agent="Web Component Sourcing Agent",
        label="Selecting sourced components",
        description="Choosing real components with sourcing notes and pin definitions.",
        duration_ms=7500,
    ),
    AgentPipelineStep(
        id="wiring_netlist",
        agent="Wiring/Netlist Agent",
        label="Drafting nets and pin mappings",
        description="Connecting sourced components into safe low-voltage electrical nets.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="validation_repair",
        agent="Validation + Auto-Correction Agent",
        label="Validating and repairing wiring",
        description="Checking and correcting electrical or logical issues.",
        duration_ms=5500,
    ),
    AgentPipelineStep(
        id="mechanical_fabrication",
        agent="Mechanical/Fabrication Agent",
        label="Designing enclosure and placement",
        description="Generating fabrication details, CAD sourcing, and 3D render placements.",
        duration_ms=6500,
    ),
    AgentPipelineStep(
        id="assembly",
        agent="Assembly Instruction Agent",
        label="Writing build steps",
        description="Producing build instructions grounded in the sourced parts and generated wiring.",
        duration_ms=5500,
    ),
    AgentPipelineStep(
        id="completeness_audit",
        agent="Hardware Output Completeness Auditor Agent",
        label="Auditing completeness",
        description="Checking for missing power, protection, sourcing, wiring, and assembly details.",
        duration_ms=5500,
    ),
    AgentPipelineStep(
        id="package_project",
        agent="Project Packager",
        label="Packaging project artifacts",
        description="Building the HardwareIR, diagrams, validation summary, and saved project record.",
        duration_ms=3500,
    ),
]


IMAGE_OUTPUT_PIPELINE_STEP = AgentPipelineStep(
    id="image_generation",
    agent="Product Image Agent",
    label="Generating product visuals",
    description="Creating optional concept images from the completed HardwareIR visual spec.",
    duration_ms=8000,
    optional=True,
)


def list_agent_pipeline_steps(
    workflow: Optional[str] = None,
    *,
    include_image: bool = False,
) -> List[dict[str, Any]]:
    normalized = normalize_generation_workflow_id(workflow, strict=False)
    steps = WEB_RESEARCH_AGENT_PIPELINE_STEPS if normalized == WEB_RESEARCH_WORKFLOW_ID else DEFAULT_AGENT_PIPELINE_STEPS
    payload = [step.as_dict() for step in steps]
    if include_image:
        payload.append(IMAGE_OUTPUT_PIPELINE_STEP.as_dict())
    return payload


def pipeline_workflow_id(workflow: Optional[str] = None) -> str:
    normalized = normalize_generation_workflow_id(workflow, strict=False)
    return normalized if normalized in {DEFAULT_WORKFLOW_ID, WEB_RESEARCH_WORKFLOW_ID} else DEFAULT_WORKFLOW_ID


def external_source_response_status(error: Any) -> str:
    return "provider_response_unavailable" if error else "provider_response_received"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def pipeline_step_metadata(workflow: Optional[str], step_id: str) -> Optional[dict[str, Any]]:
    for step in list_agent_pipeline_steps(workflow, include_image=True):
        if step.get("id") == step_id:
            return step
    return None


def emit_agent_pipeline_event(
    workflow: Optional[str],
    step_id: str,
    status: str,
    *,
    details: Optional[dict[str, Any]] = None,
) -> Optional[AgentPipelineEvent]:
    callback = _PIPELINE_EVENT_CALLBACK.get()
    if callback is None:
        return None

    normalized_workflow = pipeline_workflow_id(workflow)
    step = pipeline_step_metadata(normalized_workflow, step_id) or {
        "agent": step_id.replace("_", " ").title(),
        "label": step_id.replace("_", " ").title(),
        "description": "",
    }
    event = AgentPipelineEvent(
        workflow=normalized_workflow,
        step_id=step_id,
        status=status,
        agent=str(step.get("agent") or step_id),
        label=str(step.get("label") or step_id),
        description=str(step.get("description") or ""),
        observed_at=_utc_now(),
        details=details or {},
    )
    callback(event)
    return event


@contextlib.contextmanager
def observe_agent_pipeline(callback: PipelineEventCallback) -> Iterator[None]:
    token = _PIPELINE_EVENT_CALLBACK.set(callback)
    try:
        yield
    finally:
        _PIPELINE_EVENT_CALLBACK.reset(token)


@contextlib.contextmanager
def agent_pipeline_step(
    workflow: Optional[str],
    step_id: str,
    *,
    details: Optional[dict[str, Any]] = None,
) -> Iterator[None]:
    emit_agent_pipeline_event(workflow, step_id, "started", details=details)
    try:
        yield
    except Exception as exc:
        emit_agent_pipeline_event(
            workflow,
            step_id,
            "failed",
            details={**(details or {}), "error_type": exc.__class__.__name__, "error": str(exc)[:500]},
        )
        raise
    else:
        emit_agent_pipeline_event(workflow, step_id, "completed", details=details)
