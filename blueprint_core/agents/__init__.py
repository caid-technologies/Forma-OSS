"""Canonical home for Forma agent implementations and infrastructure."""

__all__ = [
    "ContextClarifierAgent",
    "ContextGatheringAgent",
    "ContinuousAgentCoordinator",
    "FireworksVideoSelfCorrectionAgent",
    "HardwarePipelineOrchestrator",
    "ProjectSelfCorrectionAgent",
    "PromptCompactionAgent",
    "generate_project_with_workflow",
    "get_workflow_debug_config",
    "list_workflows",
]


def __getattr__(name: str):
    if name == "ContextClarifierAgent":
        from blueprint_core.agents.clarification import ContextClarifierAgent

        return ContextClarifierAgent
    if name == "ContextGatheringAgent":
        from blueprint_core.agents.context_gathering import ContextGatheringAgent

        return ContextGatheringAgent
    if name == "ContinuousAgentCoordinator":
        from blueprint_core.agents.continuous import ContinuousAgentCoordinator

        return ContinuousAgentCoordinator
    if name == "FireworksVideoSelfCorrectionAgent":
        from blueprint_core.agents.video_correction import FireworksVideoSelfCorrectionAgent

        return FireworksVideoSelfCorrectionAgent
    if name == "HardwarePipelineOrchestrator":
        from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator

        return HardwarePipelineOrchestrator
    if name in {"generate_project_with_workflow", "get_workflow_debug_config", "list_workflows"}:
        from blueprint_core.agents import workflows

        return getattr(workflows, name)
    if name == "ProjectSelfCorrectionAgent":
        from blueprint_core.agents.project_correction import ProjectSelfCorrectionAgent

        return ProjectSelfCorrectionAgent
    if name == "PromptCompactionAgent":
        from blueprint_core.agents.prompt_compaction import PromptCompactionAgent

        return PromptCompactionAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
