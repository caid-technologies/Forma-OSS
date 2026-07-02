from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.agents.orchestrator import HardwarePipelineOrchestrator
from backend.agents.web_research_workflow import WebResearchHardwarePipeline
from backend.models import HardwareIR


DEFAULT_WORKFLOW_ID = "default"
WEB_RESEARCH_WORKFLOW_ID = "web_research"


@dataclass(frozen=True)
class WorkflowDescriptor:
    id: str
    label: str
    description: str
    uses_firecrawl_mcp: bool = False


WORKFLOW_DESCRIPTORS = [
    WorkflowDescriptor(
        id=DEFAULT_WORKFLOW_ID,
        label="Catalog",
        description="Original sequential pipeline constrained to the active component catalog.",
    ),
    WorkflowDescriptor(
        id=WEB_RESEARCH_WORKFLOW_ID,
        label="Web Research",
        description="Firecrawl MCP research pipeline that sources components from web research before validation.",
        uses_firecrawl_mcp=True,
    ),
]


def normalize_workflow_id(value: Optional[str]) -> str:
    normalized = (value or DEFAULT_WORKFLOW_ID).strip().lower().replace("-", "_")
    aliases = {
        "catalog": DEFAULT_WORKFLOW_ID,
        "seed": DEFAULT_WORKFLOW_ID,
        "seed_db": DEFAULT_WORKFLOW_ID,
        "legacy": DEFAULT_WORKFLOW_ID,
        "firecrawl": WEB_RESEARCH_WORKFLOW_ID,
        "web": WEB_RESEARCH_WORKFLOW_ID,
        "internet": WEB_RESEARCH_WORKFLOW_ID,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {descriptor.id for descriptor in WORKFLOW_DESCRIPTORS}:
        valid = ", ".join(descriptor.id for descriptor in WORKFLOW_DESCRIPTORS)
        raise ValueError(f"Unsupported generation workflow '{value}'. Valid workflows: {valid}.")
    return normalized


def list_workflows() -> List[Dict[str, Any]]:
    return [descriptor.__dict__ for descriptor in WORKFLOW_DESCRIPTORS]


def get_workflow_debug_config(workflow_id: Optional[str] = None) -> Dict[str, Any]:
    normalized = normalize_workflow_id(workflow_id)
    if normalized == WEB_RESEARCH_WORKFLOW_ID:
        return WebResearchHardwarePipeline().get_debug_config()
    return {
        **HardwarePipelineOrchestrator().get_debug_config(),
        "workflow": DEFAULT_WORKFLOW_ID,
    }


def generate_project_with_workflow(
    workflow_id: Optional[str],
    prompt: str,
    *,
    image_bytes: Optional[bytes] = None,
    image_mime_type: Optional[str] = None,
) -> HardwareIR:
    normalized = normalize_workflow_id(workflow_id)
    if normalized == WEB_RESEARCH_WORKFLOW_ID:
        return WebResearchHardwarePipeline().generate_project(
            prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )

    ir = HardwarePipelineOrchestrator().generate_project(
        prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
    )
    ir.assembly_metadata = {
        **(ir.assembly_metadata or {}),
        "workflow": DEFAULT_WORKFLOW_ID,
    }
    return ir
