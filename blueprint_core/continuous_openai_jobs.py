from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol

from blueprint_core.continuous_agents import (
    ContinuousAgentCoordinator,
    ContinuousAgentCycleReport,
    ContinuousAgentState,
    JsonlStreamStore,
)
from blueprint_core.openai_streams import (
    OpenAICompatibleChatConfig,
    OpenAIStreamConfig,
    OpenAIStreamEventWriter,
    OpenAIStreamRequestError,
    OpenAITextStreamChunk,
)
from blueprint_core.providers import (
    ProviderConfigurationError,
    ProviderEvent,
    ProviderRegistry,
    ProviderRequest,
    model_name_for_provider,
    normalize_provider_name,
)


class OpenAIStreamerProtocol(Protocol):
    def stream_text(self) -> Iterable[OpenAITextStreamChunk]:
        ...


OpenAIStreamerFactory = Callable[[OpenAIStreamConfig], OpenAIStreamerProtocol]
OpenAICompatibleChatStreamerFactory = Callable[[OpenAICompatibleChatConfig], OpenAIStreamerProtocol]
OpenAIChunkCallback = Callable[[OpenAITextStreamChunk], None]
OpenAIJobCallback = Callable[["ContinuousOpenAIJobReport"], None]


def now_seconds() -> float:
    return time.time()


def chunk_from_provider_event(event: ProviderEvent) -> OpenAITextStreamChunk:
    return OpenAITextStreamChunk(
        sequence=event.sequence,
        content=event.content,
        done=event.done,
        response_event_type=event.event_type,
        response_id=event.response_id,
        error_message=event.error_message,
    )


@dataclass(frozen=True)
class FirecrawlJobSourceRecord:
    title: str = ""
    url: str = ""
    content_preview: str = ""

    @classmethod
    def from_dict(cls, value: Any) -> "FirecrawlJobSourceRecord":
        data = value if isinstance(value, dict) else {}
        return cls(
            title=str(data.get("title") or ""),
            url=str(data.get("url") or ""),
            content_preview=str(data.get("content_preview") or data.get("content") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "content_preview": self.content_preview,
        }


@dataclass(frozen=True)
class FirecrawlJobSourceUsage:
    configured: bool
    searches_attempted: int = 0
    source_count: int = 0
    tool_name: str = ""
    error: str = ""
    records: tuple[FirecrawlJobSourceRecord, ...] = ()

    @classmethod
    def from_dict(cls, value: Any) -> "FirecrawlJobSourceUsage":
        data = value if isinstance(value, dict) else {}
        records = data.get("records")
        if records is None:
            records = data.get("hits")
        record_items = records if isinstance(records, list) else []
        return cls(
            configured=bool(data.get("configured")),
            searches_attempted=int(data.get("searches_attempted") or 0),
            source_count=int(data.get("source_count") or len(record_items)),
            tool_name=str(data.get("tool_name") or ""),
            error=str(data.get("error") or ""),
            records=tuple(FirecrawlJobSourceRecord.from_dict(item) for item in record_items),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": "firecrawl",
            "configured": self.configured,
            "searches_attempted": self.searches_attempted,
            "source_count": self.source_count,
            "tool_name": self.tool_name,
            "error": self.error,
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True)
class ContinuousOpenAIJobMetadata:
    process_id: str = ""
    batch_id: str = ""
    prompt_index: Optional[int] = None
    total_prompts: Optional[int] = None
    stage: str = ""
    objective: str = ""
    continuity_anchor: str = ""
    continuity_revision: int = 0
    continuity_findings: tuple[str, ...] = ()
    source_queries: tuple[str, ...] = ()
    source_context_preview: str = ""
    firecrawl: Optional[FirecrawlJobSourceUsage] = None

    @classmethod
    def from_dict(cls, value: Any) -> "ContinuousOpenAIJobMetadata":
        data = value if isinstance(value, dict) else {}
        firecrawl_value = data.get("firecrawl")
        return cls(
            process_id=str(data.get("process_id") or ""),
            batch_id=str(data.get("batch_id") or ""),
            prompt_index=int(data["prompt_index"]) if data.get("prompt_index") is not None else None,
            total_prompts=int(data["total_prompts"]) if data.get("total_prompts") is not None else None,
            stage=str(data.get("stage") or ""),
            objective=str(data.get("objective") or ""),
            continuity_anchor=str(data.get("continuity_anchor") or ""),
            continuity_revision=int(data.get("continuity_revision") or 0),
            continuity_findings=tuple(str(item) for item in data.get("continuity_findings", []) if item),
            source_queries=tuple(str(item) for item in data.get("source_queries", []) if item),
            source_context_preview=str(data.get("source_context_preview") or ""),
            firecrawl=FirecrawlJobSourceUsage.from_dict(firecrawl_value) if firecrawl_value is not None else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "batch_id": self.batch_id,
            "prompt_index": self.prompt_index,
            "total_prompts": self.total_prompts,
            "stage": self.stage,
            "objective": self.objective,
            "continuity_anchor": self.continuity_anchor,
            "continuity_revision": self.continuity_revision,
            "continuity_findings": list(self.continuity_findings),
            "source_queries": list(self.source_queries),
            "source_context_preview": self.source_context_preview,
            "firecrawl": self.firecrawl.to_dict() if self.firecrawl else None,
        }

    def with_review(self, findings: tuple[str, ...], *, source_context_preview: str | None = None) -> "ContinuousOpenAIJobMetadata":
        return replace(
            self,
            continuity_revision=self.continuity_revision + 1,
            continuity_findings=findings,
            source_context_preview=source_context_preview if source_context_preview is not None else self.source_context_preview,
        )


@dataclass(frozen=True)
class ContinuousOpenAIJobSpec:
    job_id: str
    prompt: str
    model: str
    provider: str = "openai"
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = None
    parent_job_id: Optional[str] = None
    clone_of_job_id: Optional[str] = None
    generation: int = 0
    created_by: str = "manual"
    created_at_unix_seconds: float = 0.0
    reason: str = ""
    metadata: ContinuousOpenAIJobMetadata = field(default_factory=ContinuousOpenAIJobMetadata)

    @classmethod
    def create(
        cls,
        *,
        prompt: str,
        model: str,
        provider: str = "openai",
        instructions: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        parent_job_id: Optional[str] = None,
        clone_of_job_id: Optional[str] = None,
        generation: int = 0,
        created_by: str = "manual",
        reason: str = "",
        metadata: ContinuousOpenAIJobMetadata | None = None,
    ) -> "ContinuousOpenAIJobSpec":
        resolved_provider = normalize_provider_name(provider)
        return cls(
            job_id=f"{resolved_provider}-job-{uuid.uuid4().hex}",
            prompt=prompt,
            model=model,
            provider=resolved_provider,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
            parent_job_id=parent_job_id,
            clone_of_job_id=clone_of_job_id,
            generation=generation,
            created_by=created_by,
            created_at_unix_seconds=now_seconds(),
            reason=reason,
            metadata=metadata or ContinuousOpenAIJobMetadata(),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ContinuousOpenAIJobSpec":
        return cls(
            job_id=str(value.get("job_id") or f"openai-job-{uuid.uuid4().hex}"),
            prompt=str(value.get("prompt") or ""),
            model=str(value.get("model") or "gpt-5.5"),
            provider=normalize_provider_name(str(value.get("provider") or "openai")),
            instructions=str(value["instructions"]) if value.get("instructions") is not None else None,
            max_output_tokens=int(value["max_output_tokens"]) if value.get("max_output_tokens") is not None else None,
            parent_job_id=str(value["parent_job_id"]) if value.get("parent_job_id") is not None else None,
            clone_of_job_id=str(value["clone_of_job_id"]) if value.get("clone_of_job_id") is not None else None,
            generation=int(value.get("generation") or 0),
            created_by=str(value.get("created_by") or "manual"),
            created_at_unix_seconds=float(value.get("created_at_unix_seconds") or 0.0),
            reason=str(value.get("reason") or ""),
            metadata=ContinuousOpenAIJobMetadata.from_dict(value.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": self.job_id,
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "instructions": self.instructions,
            "max_output_tokens": self.max_output_tokens,
            "parent_job_id": self.parent_job_id,
            "clone_of_job_id": self.clone_of_job_id,
            "generation": self.generation,
            "created_by": self.created_by,
            "created_at_unix_seconds": self.created_at_unix_seconds,
            "reason": self.reason,
            "metadata": self.metadata.to_dict(),
        }

    def child(
        self,
        *,
        prompt: str,
        created_by: str,
        reason: str,
        clone: bool = False,
        metadata: ContinuousOpenAIJobMetadata | None = None,
    ) -> "ContinuousOpenAIJobSpec":
        return ContinuousOpenAIJobSpec.create(
            prompt=prompt,
            model=self.model,
            provider=self.provider,
            instructions=self.instructions,
            max_output_tokens=self.max_output_tokens,
            parent_job_id=self.job_id,
            clone_of_job_id=self.job_id if clone else self.clone_of_job_id,
            generation=self.generation + 1,
            created_by=created_by,
            reason=reason,
            metadata=metadata or self.metadata,
        )


@dataclass(frozen=True)
class ContinuousOpenAIJobResult:
    job_id: str
    status: str
    event_count: int
    character_count: int
    duration_seconds: float
    agent_output_names: tuple[str, ...]
    provider: str = "openai"
    model: str = ""
    child_job_id: Optional[str] = None
    error_message: Optional[str] = None
    completed_at_unix_seconds: float = 0.0

    @classmethod
    def from_report(
        cls,
        report: "ContinuousOpenAIJobReport",
        *,
        child_job_id: Optional[str] = None,
    ) -> "ContinuousOpenAIJobResult":
        return cls(
            job_id=report.job_id,
            status="failed" if report.error_message else "succeeded",
            provider=report.provider,
            model=report.model,
            event_count=report.event_count,
            character_count=report.character_count,
            duration_seconds=report.duration_seconds,
            agent_output_names=tuple(report.agent_report.output_agent_names),
            child_job_id=child_job_id,
            error_message=report.error_message,
            completed_at_unix_seconds=now_seconds(),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ContinuousOpenAIJobResult":
        return cls(
            job_id=str(value.get("job_id") or ""),
            status=str(value.get("status") or "unknown"),
            provider=str(value.get("provider") or "openai"),
            model=str(value.get("model") or ""),
            event_count=int(value.get("event_count") or 0),
            character_count=int(value.get("character_count") or 0),
            duration_seconds=float(value.get("duration_seconds") or 0.0),
            agent_output_names=tuple(str(item) for item in value.get("agent_output_names", []) if item),
            child_job_id=str(value["child_job_id"]) if value.get("child_job_id") is not None else None,
            error_message=str(value["error_message"]) if value.get("error_message") is not None else None,
            completed_at_unix_seconds=float(value.get("completed_at_unix_seconds") or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": self.job_id,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "event_count": self.event_count,
            "character_count": self.character_count,
            "duration_seconds": self.duration_seconds,
            "agent_output_names": list(self.agent_output_names),
            "child_job_id": self.child_job_id,
            "error_message": self.error_message,
            "completed_at_unix_seconds": self.completed_at_unix_seconds,
        }


@dataclass(frozen=True)
class ContinuousOpenAIJobReport:
    job_index: int
    job_id: str
    provider: str
    model: str
    prompt_revision: int
    prompt_preview: str
    event_count: int
    character_count: int
    duration_seconds: float
    agent_report: ContinuousAgentCycleReport
    error_message: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.error_message is None


class ContinuousOpenAIJobQueue:
    def __init__(self, store: JsonlStreamStore) -> None:
        self.store = store
        self.jobs_path = store.stream_dir / "jobs.jsonl"
        self.results_path = store.stream_dir / "job-results.jsonl"

    def ensure(self) -> None:
        self.store.ensure()
        if not self.jobs_path.exists():
            self.jobs_path.touch()
        if not self.results_path.exists():
            self.results_path.touch()

    def append_job(self, job: ContinuousOpenAIJobSpec) -> None:
        self.ensure()
        with self.jobs_path.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(job.to_dict(), sort_keys=True) + "\n")
            handle.flush()

    def append_result(self, result: ContinuousOpenAIJobResult) -> None:
        self.ensure()
        with self.results_path.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
            handle.flush()

    def jobs(self) -> tuple[ContinuousOpenAIJobSpec, ...]:
        self.ensure()
        import json

        parsed: list[ContinuousOpenAIJobSpec] = []
        with self.jobs_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    parsed.append(ContinuousOpenAIJobSpec.from_dict(json.loads(line)))
        return tuple(parsed)

    def results(self) -> tuple[ContinuousOpenAIJobResult, ...]:
        self.ensure()
        import json

        parsed: list[ContinuousOpenAIJobResult] = []
        with self.results_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    parsed.append(ContinuousOpenAIJobResult.from_dict(json.loads(line)))
        return tuple(parsed)

    def processed_job_ids(self) -> set[str]:
        return {result.job_id for result in self.results() if result.job_id}

    def next_pending_job(self) -> Optional[ContinuousOpenAIJobSpec]:
        processed = self.processed_job_ids()
        for job in self.jobs():
            if job.job_id not in processed:
                return job
        return None


class ContinuousOpenAIJobRunner:
    def __init__(
        self,
        *,
        store: JsonlStreamStore,
        config: OpenAIStreamConfig,
        image_paths: Iterable[Path] = (),
        video_paths: Iterable[Path] = (),
        sleep_seconds: float = 5.0,
        env_file: Path | None = None,
        streamer_factory: OpenAIStreamerFactory | None = None,
        chat_streamer_factory: OpenAICompatibleChatStreamerFactory | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.sleep_seconds = sleep_seconds
        self.env_file = env_file or Path(".env")
        self.streamer_factory = streamer_factory
        self.chat_streamer_factory = chat_streamer_factory
        self.provider_registry = provider_registry or ProviderRegistry.default(
            env_file=self.env_file,
            openai_config=self.config,
            openai_streamer_factory=streamer_factory,
            openai_compatible_streamer_factory=chat_streamer_factory,
        )
        self.writer = OpenAIStreamEventWriter(store)
        self.queue = ContinuousOpenAIJobQueue(store)
        self.coordinator = ContinuousAgentCoordinator(
            store,
            image_paths=image_paths,
            video_paths=video_paths,
            poll_interval_seconds=sleep_seconds,
        )
        self.stop_event = threading.Event()

    def ensure_state(self) -> None:
        self.store.ensure()
        self.queue.ensure()
        if not self.store.state_path.exists():
            self.store.save_state(ContinuousAgentState(current_prompt=self.config.prompt))

    def current_prompt(self) -> tuple[str, int]:
        state = self.store.load_state()
        prompt = state.current_prompt.strip() or self.config.prompt
        return prompt, state.prompt_revision

    def _writer_for_provider(self, provider: str, *, endpoint_path: str = "responses") -> OpenAIStreamEventWriter:
        resolved_provider = normalize_provider_name(provider)
        if resolved_provider == "baseten":
            return OpenAIStreamEventWriter(
                self.store,
                provider_name="baseten",
                event_provider_name="baseten",
                endpoint_path=endpoint_path,
            )
        if resolved_provider == "openai":
            if endpoint_path == "responses":
                return self.writer
            return OpenAIStreamEventWriter(
                self.store,
                provider_name="openai",
                event_provider_name="openai",
                endpoint_path=endpoint_path,
            )
        return OpenAIStreamEventWriter(
            self.store,
            provider_name=resolved_provider,
            event_provider_name=resolved_provider,
            endpoint_path=endpoint_path,
        )

    def _default_base_url_for_provider(self, provider: str) -> str:
        try:
            return self.provider_registry.spec(provider).base_url
        except ProviderConfigurationError:
            return self.config.base_url

    def _request_for_job(self, job: ContinuousOpenAIJobSpec) -> ProviderRequest:
        provider = normalize_provider_name(job.provider)
        instructions = job.instructions if job.instructions is not None else self.config.instructions
        max_output_tokens = job.max_output_tokens if job.max_output_tokens is not None else self.config.max_output_tokens
        return ProviderRequest(
            provider=provider,
            model=model_name_for_provider(provider, job.model or self.config.model),
            prompt=job.prompt,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
        )

    def run_job(
        self,
        *,
        job_index: int,
        job: ContinuousOpenAIJobSpec | None = None,
        on_chunk: OpenAIChunkCallback | None = None,
    ) -> ContinuousOpenAIJobReport:
        self.ensure_state()
        fallback_prompt, prompt_revision = self.current_prompt()
        job = job or ContinuousOpenAIJobSpec.create(prompt=fallback_prompt, model=self.config.model, instructions=self.config.instructions)
        provider = normalize_provider_name(job.provider)
        report_model = model_name_for_provider(provider, job.model or self.config.model)
        writer = self._writer_for_provider(provider)
        base_url = self._default_base_url_for_provider(provider)
        started_at = time.monotonic()
        event_count = 0
        character_count = 0
        error_message: str | None = None

        try:
            request = self._request_for_job(job)
            prepared = self.provider_registry.prepare(request)
            provider = prepared.provider
            report_model = prepared.model_name
            writer = self._writer_for_provider(provider, endpoint_path=prepared.endpoint_path)
            base_url = prepared.base_url
            for event in self.provider_registry.stream_text(prepared):
                chunk = chunk_from_provider_event(event)
                writer.append(
                    chunk,
                    model=report_model,
                    base_url=base_url,
                    job_id=job.job_id,
                    job_index=job_index,
                    prompt_revision=prompt_revision,
                )
                event_count += 1
                character_count += len(chunk.content)
                if on_chunk:
                    on_chunk(chunk)
                if chunk.error_message:
                    error_message = chunk.error_message
        except (ProviderConfigurationError, OpenAIStreamRequestError, RuntimeError, ValueError) as exc:
            error_message = str(exc)
            failure_chunk = OpenAITextStreamChunk(
                sequence=event_count + 1,
                content="",
                done=True,
                response_event_type="request.error",
                error_message=error_message,
            )
            writer.append(
                failure_chunk,
                model=report_model,
                base_url=base_url,
                job_id=job.job_id,
                job_index=job_index,
                prompt_revision=prompt_revision,
            )
            event_count += 1
            if on_chunk:
                on_chunk(failure_chunk)

        state = self.store.load_state()
        agent_report = self.coordinator.run_cycle_report(state, cycle_index=job_index)
        return ContinuousOpenAIJobReport(
            job_index=job_index,
            job_id=job.job_id,
            provider=provider,
            model=report_model,
            prompt_revision=prompt_revision,
            prompt_preview=job.prompt[:500],
            event_count=event_count,
            character_count=character_count,
            duration_seconds=time.monotonic() - started_at,
            agent_report=agent_report,
            error_message=error_message,
        )

    def run_pending_job(
        self,
        *,
        job_index: int,
        iterate_on_findings: bool = True,
        clone_on_pass: bool = False,
        on_chunk: OpenAIChunkCallback | None = None,
    ) -> Optional[ContinuousOpenAIJobReport]:
        self.ensure_state()
        job = self.queue.next_pending_job()
        if job is None:
            return None
        report = self.run_job(job_index=job_index, job=job, on_chunk=on_chunk)
        child_job_id: str | None = None
        if report.error_message is None:
            state = self.store.load_state()
            if iterate_on_findings and "prompt-iterator" in report.agent_report.output_agent_names and state.current_prompt.strip():
                child = job.child(
                    prompt=state.current_prompt,
                    created_by="prompt-iterator",
                    reason="reviewer findings produced a prompt iteration",
                )
                self.queue.append_job(child)
                child_job_id = child.job_id
            elif clone_on_pass:
                child = job.child(
                    prompt=job.prompt,
                    created_by="clone-agent",
                    reason="clone_on_pass requested after a successful review",
                    clone=True,
                )
                self.queue.append_job(child)
                child_job_id = child.job_id
        self.queue.append_result(ContinuousOpenAIJobResult.from_report(report, child_job_id=child_job_id))
        return report

    def run(
        self,
        *,
        max_jobs: int | None = None,
        continue_on_error: bool = False,
        on_chunk: OpenAIChunkCallback | None = None,
        on_job: OpenAIJobCallback | None = None,
    ) -> None:
        self.ensure_state()
        job_index = 0
        while not self.stop_event.is_set():
            job_index += 1
            report = self.run_job(job_index=job_index, on_chunk=on_chunk)
            if on_job:
                on_job(report)
            if report.error_message and not continue_on_error:
                break
            if max_jobs is not None and job_index >= max_jobs:
                break
            if self.sleep_seconds > 0:
                self.stop_event.wait(self.sleep_seconds)

    def run_queue(
        self,
        *,
        max_jobs: int | None = None,
        continue_on_error: bool = False,
        iterate_on_findings: bool = True,
        clone_on_pass: bool = False,
        on_chunk: OpenAIChunkCallback | None = None,
        on_job: OpenAIJobCallback | None = None,
        on_idle: Callable[[], None] | None = None,
    ) -> None:
        self.ensure_state()
        processed_count = 0
        while not self.stop_event.is_set():
            if self.queue.next_pending_job() is None:
                if on_idle:
                    on_idle()
                if self.sleep_seconds > 0:
                    self.stop_event.wait(self.sleep_seconds)
                continue
            report = self.run_pending_job(
                job_index=processed_count + 1,
                iterate_on_findings=iterate_on_findings,
                clone_on_pass=clone_on_pass,
                on_chunk=on_chunk,
            )
            if report is None:
                if on_idle:
                    on_idle()
                if self.sleep_seconds > 0:
                    self.stop_event.wait(self.sleep_seconds)
                continue
            processed_count += 1
            if on_job:
                on_job(report)
            if report.error_message and not continue_on_error:
                break
            if max_jobs is not None and processed_count >= max_jobs:
                break
            if self.sleep_seconds > 0:
                self.stop_event.wait(self.sleep_seconds)

    def stop(self) -> None:
        self.stop_event.set()


__all__ = [
    "ContinuousOpenAIJobQueue",
    "ContinuousOpenAIJobReport",
    "ContinuousOpenAIJobResult",
    "ContinuousOpenAIJobRunner",
    "ContinuousOpenAIJobSpec",
    "OpenAIChunkCallback",
    "OpenAIJobCallback",
    "OpenAIStreamerFactory",
    "OpenAIStreamerProtocol",
]
