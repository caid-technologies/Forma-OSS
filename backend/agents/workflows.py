from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.agents.orchestrator import HardwarePipelineOrchestrator
from backend.agents.web_research_workflow import WebResearchHardwarePipeline
from backend.job_source_usage import (
    DEFAULT_WORKFLOW_ID,
    WEB_RESEARCH_WORKFLOW_ID,
    normalize_generation_workflow_id,
    source_usage_for_workflow,
)
from backend.models import HardwareIR


@dataclass(frozen=True)
class WorkflowDescriptor:
    id: str
    label: str
    description: str
    uses_catalog: bool = False
    uses_web_research: bool = False
    uses_firecrawl_mcp: bool = False


WORKFLOW_DESCRIPTORS = [
    WorkflowDescriptor(
        id=DEFAULT_WORKFLOW_ID,
        label="Catalog",
        description="Original sequential pipeline constrained to the active component catalog.",
        uses_catalog=True,
    ),
    WorkflowDescriptor(
        id=WEB_RESEARCH_WORKFLOW_ID,
        label="Web Research",
        description="Firecrawl MCP research pipeline that sources components from web research before validation.",
        uses_web_research=True,
        uses_firecrawl_mcp=True,
    ),
]


def normalize_workflow_id(value: Optional[str]) -> str:
    return normalize_generation_workflow_id(value, strict=True)


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
    source_usage = source_usage_for_workflow(normalized)
    if normalized == WEB_RESEARCH_WORKFLOW_ID:
        ir = WebResearchHardwarePipeline().generate_project(
            prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )
    else:
        ir = HardwarePipelineOrchestrator().generate_project(
            prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )
    ir.assembly_metadata = {
        **(ir.assembly_metadata or {}),
        "workflow": normalized,
        "source_usage": source_usage,
    }
    return ir
