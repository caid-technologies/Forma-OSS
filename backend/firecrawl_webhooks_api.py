from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.job_store import JOB_STORE
from blueprint_core.external_sources import source_domain, source_relevance_metadata


router = APIRouter()


def _webhook_secret() -> Optional[str]:
    value = os.getenv("FIRECRAWL_WEBHOOK_SECRET") or os.getenv("BLUEPRINT_FIRECRAWL_WEBHOOK_SECRET")
    return value.strip() if value and value.strip() else None


def _header_secret(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    for header in (
        "x-blueprint-webhook-secret",
        "x-firecrawl-webhook-secret",
        "x-webhook-secret",
    ):
        value = request.headers.get(header)
        if value and value.strip():
            return value.strip()
    return None


def _require_webhook_secret(request: Request) -> None:
    expected = _webhook_secret()
    if not expected:
        return
    if _header_secret(request) != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firecrawl webhook secret.")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        current = _as_dict(current).get(key)
    return _as_dict(current)


def extract_firecrawl_job_id(payload: dict[str, Any], query_job_id: Optional[str] = None) -> str:
    metadata = _as_dict(payload.get("metadata"))
    data_metadata = _nested(payload, "data", "metadata")
    page_metadata = _nested(payload, "page", "metadata")
    document_metadata = _nested(payload, "document", "metadata")
    return _first_string(
        query_job_id,
        payload.get("blueprint_job_id"),
        payload.get("job_id"),
        payload.get("jobId"),
        metadata.get("blueprint_job_id"),
        metadata.get("job_id"),
        metadata.get("jobId"),
        data_metadata.get("blueprint_job_id"),
        data_metadata.get("job_id"),
        data_metadata.get("jobId"),
        page_metadata.get("blueprint_job_id"),
        page_metadata.get("job_id"),
        document_metadata.get("blueprint_job_id"),
        document_metadata.get("job_id"),
    )


def _event_kind(payload: dict[str, Any]) -> str:
    return _first_string(
        payload.get("type"),
        payload.get("event"),
        payload.get("event_type"),
        payload.get("status"),
        payload.get("webhookType"),
    ).lower()


def _source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "page", "document", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _search_queries(payload: dict[str, Any], job: Optional[dict[str, Any]]) -> list[str]:
    raw_queries = (
        _as_dict(payload.get("metadata")).get("queries")
        or _nested(payload, "data", "metadata").get("queries")
        or payload.get("queries")
    )
    if isinstance(raw_queries, list):
        return [str(item) for item in raw_queries if str(item).strip()]
    if isinstance(raw_queries, str) and raw_queries.strip():
        return [raw_queries.strip()]
    prompt = _as_dict(job or {}).get("payload", {}).get("prompt") if isinstance(_as_dict(job or {}).get("payload"), dict) else None
    return [prompt] if isinstance(prompt, str) and prompt.strip() else []


def firecrawl_webhook_event(payload: dict[str, Any], job: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    kind = _event_kind(payload)
    source = _source_payload(payload)
    title = _first_string(source.get("title"), source.get("name"), payload.get("title"))
    url = _first_string(source.get("url"), source.get("sourceURL"), source.get("sourceUrl"), payload.get("url"))
    content = _first_string(
        source.get("markdown"),
        source.get("content"),
        source.get("description"),
        source.get("text"),
        payload.get("content"),
    )

    status_name = "firecrawl_webhook_event"
    if "page" in kind or url:
        status_name = "source_found"
    if "started" in kind:
        status_name = "provider_request_started"
    elif "completed" in kind or "done" in kind:
        status_name = "provider_response_received"
    elif "failed" in kind or "error" in kind:
        status_name = "provider_request_failed"

    queries = _search_queries(payload, job)
    relevance = source_relevance_metadata(title, url, content, queries)
    return {
        "workflow": "web_research",
        "step_id": "external_research",
        "status": status_name,
        "agent": "External Source Research Agent",
        "label": "Gathering source context",
        "description": "Receiving Firecrawl async crawl or batch scrape webhook progress.",
        "details": {
            "provider": "firecrawl",
            "webhook_event": kind or None,
            "firecrawl_job_id": _first_string(payload.get("id"), payload.get("crawlId"), payload.get("batchScrapeId")),
            "title": title,
            "url": url,
            "domain": relevance.get("domain") or source_domain(url),
            "source_type": "web",
            "relevance_reason": relevance.get("relevance_reason"),
            "matched_query_terms": relevance.get("matched_query_terms"),
            "content_preview": content[:360],
            "error": _first_string(payload.get("error"), source.get("error")),
        },
    }


@router.post("/webhooks/firecrawl")
async def firecrawl_webhook_endpoint(
    request: Request,
    job_id: Optional[str] = Query(None, description="Optional Blueprint job id when not present in Firecrawl metadata."),
):
    _require_webhook_secret(request)
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Firecrawl webhook payload must be a JSON object.")

    blueprint_job_id = extract_firecrawl_job_id(payload, job_id)
    if not blueprint_job_id:
        raise HTTPException(status_code=400, detail="Firecrawl webhook payload is missing blueprint_job_id metadata.")

    job = JOB_STORE.get_job(blueprint_job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Blueprint job not found for Firecrawl webhook.")

    event = firecrawl_webhook_event(payload, job)
    JOB_STORE.append_progress_event(blueprint_job_id, event)
    return {
        "accepted": True,
        "job_id": blueprint_job_id,
        "event_status": event["status"],
        "step_id": event["step_id"],
    }

