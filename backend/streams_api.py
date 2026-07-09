from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from blueprint_core.logs import redact_log_line


ROOT_DIR = Path(__file__).resolve().parents[1]
SPACEBASE_ROOT = ROOT_DIR / ".spacebase"
STREAMS_DIR = SPACEBASE_ROOT / "streams"
ROOT_STREAM_ID = "__root__"
STREAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

router = APIRouter()


class ContinuousStreamSummary(BaseModel):
    stream_id: str
    path: str
    updated_at: Optional[str] = None
    job_count: int = 0
    result_count: int = 0
    event_count: int = 0
    pending_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    latest_job_id: Optional[str] = None
    latest_provider: Optional[str] = None
    latest_model: Optional[str] = None
    latest_status: Optional[str] = None
    latest_output_preview: str = ""


class ContinuousStreamJobResult(BaseModel):
    status: str = "pending"
    duration_seconds: Optional[float] = None
    character_count: int = 0
    event_count: int = 0
    error_message: Optional[str] = None
    completed_at: Optional[str] = None
    agent_output_names: list[str] = Field(default_factory=list)


class ContinuousStreamJob(BaseModel):
    stream_id: str
    job_id: str
    provider: str = ""
    model: str = ""
    status: str = "pending"
    prompt: str = ""
    reason: str = ""
    created_by: str = ""
    created_at: Optional[str] = None
    max_output_tokens: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    result: Optional[ContinuousStreamJobResult] = None
    output_text: str = ""
    output_preview: str = ""
    output_truncated: bool = False


class ContinuousStreamEvent(BaseModel):
    stream_id: str
    event_id: str = ""
    kind: str = ""
    job_id: Optional[str] = None
    provider: str = ""
    model: str = ""
    observed_at: Optional[str] = None
    sequence: Optional[int] = None
    done: bool = False
    content: str = ""
    error_message: Optional[str] = None


class ContinuousStreamAgentOutput(BaseModel):
    stream_id: str
    agent_name: str
    kind: str = ""
    created_at: Optional[str] = None
    source_event_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _iso_from_unix_seconds(value: Any) -> Optional[str]:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso_from_unix_ms(value: Any) -> Optional[str]:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return None
    return _iso_from_unix_seconds(milliseconds / 1000.0)


def _iso_from_mtime(path: Path) -> Optional[str]:
    try:
        return _iso_from_unix_seconds(path.stat().st_mtime)
    except OSError:
        return None


def _stream_path(stream_id: str) -> Path:
    normalized = stream_id.strip()
    if normalized == ROOT_STREAM_ID:
        return STREAMS_DIR
    if not normalized or not STREAM_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="Invalid stream_id. Use letters, numbers, dot, dash, or underscore.")
    return STREAMS_DIR / normalized


def _stream_id_from_path(path: Path) -> str:
    return ROOT_STREAM_ID if path == STREAMS_DIR else path.name


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def _tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                lines.append(line)
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _redact_text(value: Any) -> str:
    return redact_log_line(str(value or ""))


def _payload_content(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return _redact_text(payload.get("content"))
    return ""


def _payload_done(event: dict[str, Any]) -> bool:
    payload = event.get("payload")
    return bool(payload.get("done")) if isinstance(payload, dict) else False


def _event_job_id(event: dict[str, Any]) -> Optional[str]:
    metadata = event.get("metadata")
    if isinstance(metadata, dict) and metadata.get("job_id"):
        return str(metadata["job_id"])
    return None


def _event_model(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("model"):
        return str(payload["model"])
    source = event.get("source")
    if isinstance(source, dict) and source.get("name"):
        return str(source["name"])
    return ""


def _event_provider(event: dict[str, Any]) -> str:
    source = event.get("source")
    if isinstance(source, dict) and source.get("provider"):
        return str(source["provider"])
    kind = str(event.get("kind") or "")
    parts = kind.split(".")
    return parts[1] if len(parts) > 2 and parts[0] == "llm" else ""


def _events_by_job(events: Iterable[dict[str, Any]], *, max_chars: int) -> dict[str, tuple[str, bool]]:
    outputs: dict[str, str] = {}
    truncated: dict[str, bool] = {}
    for event in events:
        job_id = _event_job_id(event)
        if not job_id:
            continue
        content = _payload_content(event)
        if not content:
            continue
        current = outputs.get(job_id, "")
        remaining = max_chars - len(current)
        if remaining <= 0:
            truncated[job_id] = True
            continue
        outputs[job_id] = current + content[:remaining]
        if len(content) > remaining:
            truncated[job_id] = True
    return {job_id: (text, truncated.get(job_id, False)) for job_id, text in outputs.items()}


def _result_from_record(value: dict[str, Any]) -> ContinuousStreamJobResult:
    return ContinuousStreamJobResult(
        status=str(value.get("status") or ("failed" if value.get("error_message") else "succeeded")),
        duration_seconds=float(value["duration_seconds"]) if value.get("duration_seconds") is not None else None,
        character_count=int(value.get("character_count") or 0),
        event_count=int(value.get("event_count") or 0),
        error_message=_redact_text(value.get("error_message")) if value.get("error_message") else None,
        completed_at=_iso_from_unix_seconds(value.get("completed_at_unix_seconds")),
        agent_output_names=[str(item) for item in value.get("agent_output_names", []) if item],
    )


def _job_from_record(
    stream_id: str,
    value: dict[str, Any],
    *,
    result: Optional[ContinuousStreamJobResult],
    output_text: str,
    output_truncated: bool,
) -> ContinuousStreamJob:
    prompt = _redact_text(value.get("prompt"))
    status = result.status if result else "pending"
    return ContinuousStreamJob(
        stream_id=stream_id,
        job_id=str(value.get("job_id") or ""),
        provider=str(value.get("provider") or ""),
        model=str(value.get("model") or ""),
        status=status,
        prompt=prompt,
        reason=str(value.get("reason") or ""),
        created_by=str(value.get("created_by") or ""),
        created_at=_iso_from_unix_seconds(value.get("created_at_unix_seconds")),
        max_output_tokens=int(value["max_output_tokens"]) if value.get("max_output_tokens") is not None else None,
        metadata=value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
        result=result,
        output_text=output_text,
        output_preview=output_text[:600],
        output_truncated=output_truncated,
    )


def _stream_dirs() -> list[Path]:
    if not STREAMS_DIR.exists():
        return []
    stream_file_names = {"jobs.jsonl", "job-results.jsonl", "events.jsonl", "continuous-agent-state.json"}
    dirs = [
        path
        for path in STREAMS_DIR.iterdir()
        if path.is_dir() and any((path / name).exists() for name in stream_file_names)
    ]
    if any((STREAMS_DIR / name).exists() for name in ("jobs.jsonl", "job-results.jsonl", "events.jsonl")):
        dirs.append(STREAMS_DIR)
    return sorted(set(dirs), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)


def _stream_summary(path: Path, *, preview_chars: int) -> ContinuousStreamSummary:
    stream_id = _stream_id_from_path(path)
    jobs_path = path / "jobs.jsonl"
    results_path = path / "job-results.jsonl"
    events_path = path / "events.jsonl"
    jobs = _read_jsonl(jobs_path)
    results = _read_jsonl(results_path)
    events = _tail_jsonl(events_path, 200)
    result_by_job = {str(item.get("job_id") or ""): item for item in results if item.get("job_id")}
    processed = set(result_by_job)
    succeeded = sum(1 for item in results if str(item.get("status") or "").lower() in {"succeeded", "success", "passed", "pass"})
    failed = sum(1 for item in results if str(item.get("status") or "").lower() in {"failed", "fail", "error"})
    latest_job = jobs[-1] if jobs else {}
    latest_result = results[-1] if results else {}
    latest_job_id = str(latest_result.get("job_id") or latest_job.get("job_id") or "") or None
    outputs = _events_by_job(events, max_chars=preview_chars)
    latest_output = outputs.get(latest_job_id or "", ("", False))[0] if latest_job_id else ""
    mtimes = [_iso_from_mtime(path) for path in (jobs_path, results_path, events_path) if path.exists()]
    return ContinuousStreamSummary(
        stream_id=stream_id,
        path=str(path.relative_to(ROOT_DIR)),
        updated_at=max((item for item in mtimes if item), default=None),
        job_count=len(jobs),
        result_count=len(results),
        event_count=_count_jsonl(events_path),
        pending_count=sum(1 for item in jobs if str(item.get("job_id") or "") not in processed),
        succeeded_count=succeeded,
        failed_count=failed,
        latest_job_id=latest_job_id,
        latest_provider=str(latest_result.get("provider") or latest_job.get("provider") or "") or None,
        latest_model=str(latest_result.get("model") or latest_job.get("model") or "") or None,
        latest_status=str(latest_result.get("status") or ("pending" if latest_job else "")) or None,
        latest_output_preview=latest_output[:preview_chars],
    )


@router.get("/streams")
def list_continuous_streams(
    limit: int = Query(50, ge=1, le=200),
    preview_chars: int = Query(600, ge=0, le=4000),
):
    """Lists local continuous LLM/agent streams stored under .spacebase."""
    return [_stream_summary(path, preview_chars=preview_chars).model_dump() for path in _stream_dirs()[:limit]]


@router.get("/streams/{stream_id}")
def get_continuous_stream(stream_id: str):
    path = _stream_path(stream_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stream not found.")
    return _stream_summary(path, preview_chars=1200).model_dump()


@router.get("/streams/{stream_id}/jobs")
def list_continuous_stream_jobs(
    stream_id: str,
    status: str = Query("all"),
    limit: int = Query(100, ge=1, le=500),
    max_output_chars: int = Query(12000, ge=0, le=50000),
):
    path = _stream_path(stream_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stream not found.")

    jobs = _read_jsonl(path / "jobs.jsonl")
    results = _read_jsonl(path / "job-results.jsonl")
    events = _read_jsonl(path / "events.jsonl")
    result_by_job = {
        str(item.get("job_id") or ""): _result_from_record(item)
        for item in results
        if item.get("job_id")
    }
    outputs = _events_by_job(events, max_chars=max_output_chars)
    normalized_status = status.strip().lower()
    records: list[ContinuousStreamJob] = []
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        result = result_by_job.get(job_id)
        output_text, output_truncated = outputs.get(job_id, ("", False))
        record = _job_from_record(
            stream_id,
            job,
            result=result,
            output_text=output_text,
            output_truncated=output_truncated,
        )
        if normalized_status != "all" and record.status != normalized_status:
            continue
        records.append(record)
    records.sort(key=lambda item: item.created_at or "", reverse=True)
    return [record.model_dump() for record in records[:limit]]


@router.get("/streams/{stream_id}/events")
def list_continuous_stream_events(
    stream_id: str,
    limit: int = Query(100, ge=1, le=1000),
):
    path = _stream_path(stream_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stream not found.")

    records: list[ContinuousStreamEvent] = []
    for event in _tail_jsonl(path / "events.jsonl", limit):
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        records.append(
            ContinuousStreamEvent(
                stream_id=stream_id,
                event_id=str(event.get("event_id") or ""),
                kind=str(event.get("kind") or ""),
                job_id=_event_job_id(event),
                provider=_event_provider(event),
                model=_event_model(event),
                observed_at=_iso_from_unix_ms(event.get("observed_at_unix_ms")),
                sequence=int(payload["sequence"]) if payload.get("sequence") is not None else None,
                done=_payload_done(event),
                content=_payload_content(event),
                error_message=_redact_text(metadata.get("error_message")) if metadata.get("error_message") else None,
            )
        )
    return [record.model_dump() for record in records]


@router.get("/streams/{stream_id}/agents")
def list_continuous_stream_agents(
    stream_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    path = _stream_path(stream_id)
    agents_dir = path / "agents"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stream not found.")
    if not agents_dir.exists():
        return []

    outputs: list[ContinuousStreamAgentOutput] = []
    for agent_path in sorted(agents_dir.glob("*.jsonl")):
        agent_name = agent_path.stem
        for item in _tail_jsonl(agent_path, limit):
            outputs.append(
                ContinuousStreamAgentOutput(
                    stream_id=stream_id,
                    agent_name=str(item.get("agent_name") or agent_name),
                    kind=str(item.get("kind") or ""),
                    created_at=str(item.get("created_at") or "") or None,
                    source_event_id=str(item.get("source_event_id") or "") or None,
                    payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
                )
            )
    outputs.sort(key=lambda item: item.created_at or "", reverse=True)
    return [record.model_dump() for record in outputs[:limit]]
