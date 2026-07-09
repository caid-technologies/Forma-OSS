from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_WORKFLOW_ID = "default"
WEB_RESEARCH_WORKFLOW_ID = "web_research"

WORKFLOW_ALIASES = {
    "catalog": DEFAULT_WORKFLOW_ID,
    "seed": DEFAULT_WORKFLOW_ID,
    "seed_db": DEFAULT_WORKFLOW_ID,
    "legacy": DEFAULT_WORKFLOW_ID,
    "firecrawl": WEB_RESEARCH_WORKFLOW_ID,
    "web": WEB_RESEARCH_WORKFLOW_ID,
    "web_search": WEB_RESEARCH_WORKFLOW_ID,
    "websearch": WEB_RESEARCH_WORKFLOW_ID,
    "internet": WEB_RESEARCH_WORKFLOW_ID,
    "research": WEB_RESEARCH_WORKFLOW_ID,
}

VALID_WORKFLOW_IDS = {DEFAULT_WORKFLOW_ID, WEB_RESEARCH_WORKFLOW_ID}


def normalize_generation_workflow_id(value: Optional[str], *, strict: bool = True) -> str:
    normalized = (value or DEFAULT_WORKFLOW_ID).strip().lower().replace("-", "_")
    normalized = WORKFLOW_ALIASES.get(normalized, normalized)
    if strict and normalized not in VALID_WORKFLOW_IDS:
        valid = ", ".join(sorted(VALID_WORKFLOW_IDS))
        raise ValueError(f"Unsupported generation workflow '{value}'. Valid workflows: {valid}.")
    return normalized


def source_usage_for_workflow(
    workflow_id: Optional[str],
    *,
    strict: bool = False,
    external_provider: Optional[str] = None,
) -> Dict[str, Any]:
    workflow = normalize_generation_workflow_id(workflow_id, strict=strict)
    uses_catalog = workflow == DEFAULT_WORKFLOW_ID
    uses_web_research = workflow == WEB_RESEARCH_WORKFLOW_ID
    normalized_provider = (external_provider or "").strip().lower()
    if normalized_provider not in {"tavily", "firecrawl"}:
        normalized_provider = ""
    return _source_usage_payload(
        workflow,
        uses_catalog=uses_catalog,
        uses_web_research=uses_web_research,
        external_provider=normalized_provider or None,
    )


def infer_source_usage(
    *,
    action: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    result_summary: Optional[Dict[str, Any]] = None,
    current: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _as_dict(payload)
    result = _as_dict(result)
    result_summary = _as_dict(result_summary)
    current = _as_dict(current)
    project_ir = _as_dict(result.get("project_ir"))
    metadata = _as_dict(project_ir.get("assembly_metadata"))

    embedded_usage = metadata.get("source_usage")
    workflow = (
        metadata.get("workflow")
        or result_summary.get("workflow")
        or _as_dict(current.get("source_usage")).get("workflow")
        or payload.get("workflow")
    )

    if isinstance(embedded_usage, dict):
        return normalize_source_usage(embedded_usage, fallback_workflow=workflow)

    if not workflow and _is_generation_action(action):
        workflow = DEFAULT_WORKFLOW_ID

    if not workflow:
        existing = _as_dict(current.get("source_usage"))
        return normalize_source_usage(existing) if existing else {}

    usage = source_usage_for_workflow(str(workflow), strict=False)
    pipeline = str(metadata.get("pipeline") or result_summary.get("pipeline") or "").lower()
    component_source_policy = str(metadata.get("component_source_policy") or "").lower()
    external_research = _as_dict(metadata.get("external_research"))
    external_provider = str(
        external_research.get("provider")
        or payload.get("external_source_provider")
        or ""
    ).strip().lower() or None
    if external_provider == "auto":
        external_provider = None
    if metadata.get("tavily_research") is not None or "tavily" in pipeline:
        external_provider = "tavily"
    elif metadata.get("firecrawl_research") is not None or "firecrawl" in pipeline:
        external_provider = "firecrawl"

    has_external_metadata = bool(external_provider) or "external source" in pipeline
    if has_external_metadata:
        usage = _source_usage_payload(
            usage["workflow"],
            uses_catalog=usage["catalog"],
            uses_web_research=True,
            external_provider=external_provider,
        )
    if "not constrained to seed_db.py" in component_source_policy:
        usage = _source_usage_payload(
            usage["workflow"],
            uses_catalog=False,
            uses_web_research=usage["web_research"],
            external_provider=external_provider,
        )
    return usage


def normalize_source_usage(value: Dict[str, Any], *, fallback_workflow: Optional[Any] = None) -> Dict[str, Any]:
    source_usage = _as_dict(value)
    workflow = source_usage.get("workflow") or fallback_workflow
    usage = source_usage_for_workflow(str(workflow) if workflow else None, strict=False)

    catalog = _optional_bool(
        source_usage.get("catalog", source_usage.get("used_catalog", source_usage.get("data_warehouse")))
    )
    web_research = _optional_bool(
        source_usage.get(
            "web_research",
            source_usage.get(
                "used_web_research",
                source_usage.get("external_sources", source_usage.get("tavily", source_usage.get("firecrawl"))),
            ),
        )
    )
    external_provider = source_usage.get("external_provider")
    if not external_provider and source_usage.get("tavily"):
        external_provider = "tavily"
    if not external_provider and source_usage.get("firecrawl"):
        external_provider = "firecrawl"
    return _source_usage_payload(
        usage["workflow"],
        uses_catalog=usage["catalog"] if catalog is None else catalog,
        uses_web_research=usage["web_research"] if web_research is None else web_research,
        external_provider=str(external_provider) if external_provider else None,
    )


def _source_usage_payload(
    workflow: str,
    *,
    uses_catalog: bool,
    uses_web_research: bool,
    external_provider: Optional[str] = None,
) -> Dict[str, Any]:
    sources = []
    source_labels = []
    if uses_catalog:
        sources.append("catalog")
        source_labels.append("Catalog")
    if uses_web_research:
        sources.append("web_research")
        normalized_provider = (external_provider or "").strip().lower()
        if normalized_provider in {"tavily", "firecrawl"}:
            sources.append(normalized_provider)
            source_labels.append(normalized_provider.title())
        else:
            source_labels.append("Web Research")
    return {
        "workflow": workflow,
        "catalog": uses_catalog,
        "web_research": uses_web_research,
        "external_sources": uses_web_research,
        "external_provider": external_provider,
        "data_warehouse": uses_catalog,
        "firecrawl": uses_web_research if external_provider in (None, "firecrawl") else False,
        "tavily": external_provider == "tavily",
        "sources": sources,
        "source_labels": source_labels,
    }


def _is_generation_action(action: Optional[str]) -> bool:
    if not action:
        return False
    normalized = action.removeprefix("blueprint.")
    return normalized == "generate_project"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)
