"""High-level generation API for package consumers."""

from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from blueprint_core.agents.workflows import (
    generate_project_with_workflow,
    get_workflow_debug_config,
    list_workflows,
    normalize_workflow_id,
)
from blueprint_core.agents.project_correction import ProjectSelfCorrectionAgent
from blueprint_core.workspaces.projects.iteration import ProjectIterator, iterate_project
from blueprint_core.workspaces.projects.objects import FormaProjectObject, build_project_object, list_project_namespaces
from blueprint_core.video_prompts import VIDEO_PROMPT_NAMESPACES, generate_image_to_video_prompt_from_namespaces

__all__ = [
    "HardwarePipelineOrchestrator",
    "FormaProjectObject",
    "ProjectIterator",
    "ProjectSelfCorrectionAgent",
    "VIDEO_PROMPT_NAMESPACES",
    "build_project_object",
    "generate_image_to_video_prompt_from_namespaces",
    "generate_project_with_workflow",
    "get_workflow_debug_config",
    "iterate_project",
    "list_project_namespaces",
    "list_workflows",
    "normalize_workflow_id",
]
