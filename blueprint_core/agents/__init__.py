"""Generation agents and workflow selection for Blueprint."""

__all__ = [
    "HardwarePipelineOrchestrator",
    "generate_project_with_workflow",
    "get_workflow_debug_config",
    "list_workflows",
]


def __getattr__(name: str):
    if name == "HardwarePipelineOrchestrator":
        from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator

        return HardwarePipelineOrchestrator
    if name in {"generate_project_with_workflow", "get_workflow_debug_config", "list_workflows"}:
        from blueprint_core.agents import workflows

        return getattr(workflows, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
