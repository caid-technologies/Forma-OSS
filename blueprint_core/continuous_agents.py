from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class StreamEvent:
    schema_version: int
    event_id: str
    observed_at_unix_ms: int
    kind: str
    source_provider: str
    source_type: str
    source_name: str
    payload: dict[str, Any]
    metadata: dict[str, Any]

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "StreamEvent":
        source = value.get("source") if isinstance(value.get("source"), dict) else {}
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        return cls(
            schema_version=int(value.get("schema_version") or 1),
            event_id=str(value.get("event_id") or ""),
            observed_at_unix_ms=int(value.get("observed_at_unix_ms") or 0),
            kind=str(value.get("kind") or ""),
            source_provider=str(source.get("provider") or ""),
            source_type=str(source.get("source_type") or ""),
            source_name=str(source.get("name") or ""),
            payload=dict(payload),
            metadata=dict(metadata),
        )

    def content_text(self) -> str:
        value = self.payload.get("content")
        return value if isinstance(value, str) else ""

    def is_done(self) -> bool:
        return bool(self.payload.get("done"))


@dataclass(frozen=True)
class AgentOutputEvent:
    agent_name: str
    kind: str
    payload: dict[str, Any]
    source_event_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now)

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "created_at": self.created_at,
                "agent_name": self.agent_name,
                "kind": self.kind,
                "source_event_id": self.source_event_id,
                "payload": self.payload,
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class MediaFinding:
    severity: str
    code: str
    message: str
    path: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass(frozen=True)
class ImageInspection:
    path: Path
    exists: bool
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    mode: Optional[str] = None
    byte_size: Optional[int] = None
    findings: tuple[MediaFinding, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "mode": self.mode,
            "byte_size": self.byte_size,
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class VideoInspection:
    path: Path
    exists: bool
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frame_rate: Optional[str] = None
    byte_size: Optional[int] = None
    findings: tuple[MediaFinding, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "frame_rate": self.frame_rate,
            "byte_size": self.byte_size,
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class PromptIterationProposal:
    revision: int
    prompt: str
    reason: str
    findings: tuple[MediaFinding, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "prompt": self.prompt,
            "reason": self.reason,
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass
class ContinuousAgentState:
    input_offset: int = 0
    source_event_ids: set[str] = field(default_factory=set)
    prompt_revision: int = 0
    current_prompt: str = ""


@dataclass(frozen=True)
class ContinuousAgentCycleReport:
    cycle_index: int
    new_event_count: int
    output_count: int
    output_agent_names: tuple[str, ...]
    input_offset: int
    prompt_revision: int

    def has_activity(self) -> bool:
        return self.new_event_count > 0 or self.output_count > 0


class JsonlStreamStore:
    def __init__(self, root_dir: Path, stream_id: str) -> None:
        self.root_dir = root_dir
        self.stream_id = stream_id
        self.stream_dir = root_dir / "streams" / stream_id
        self.events_path = self.stream_dir / "events.jsonl"
        self.agents_dir = self.stream_dir / "agents"
        self.state_path = self.stream_dir / "continuous-agent-state.json"
        self.lock = threading.Lock()

    def ensure(self) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        if not self.events_path.exists():
            self.events_path.touch()

    def agent_path(self, agent_name: str) -> Path:
        return self.agents_dir / f"{agent_name}.jsonl"

    def append_agent_output(self, event: AgentOutputEvent) -> None:
        self.ensure()
        path = self.agent_path(event.agent_name)
        with self.lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(event.to_json_line() + "\n")

    def load_state(self) -> ContinuousAgentState:
        if not self.state_path.exists():
            return ContinuousAgentState()
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        return ContinuousAgentState(
            input_offset=int(raw.get("input_offset") or 0),
            source_event_ids=set(str(item) for item in raw.get("source_event_ids", [])),
            prompt_revision=int(raw.get("prompt_revision") or 0),
            current_prompt=str(raw.get("current_prompt") or ""),
        )

    def save_state(self, state: ContinuousAgentState) -> None:
        self.ensure()
        payload = {
            "input_offset": state.input_offset,
            "source_event_ids": sorted(state.source_event_ids),
            "prompt_revision": state.prompt_revision,
            "current_prompt": state.current_prompt,
            "saved_at": utc_now(),
        }
        with self.lock:
            self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def read_new_events(self, state: ContinuousAgentState) -> list[StreamEvent]:
        self.ensure()
        events: list[StreamEvent] = []
        with self.events_path.open("r", encoding="utf-8") as handle:
            handle.seek(state.input_offset)
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                parsed = json.loads(stripped)
                event = StreamEvent.from_json(parsed)
                if event.event_id and event.event_id in state.source_event_ids:
                    continue
                events.append(event)
                if event.event_id:
                    state.source_event_ids.add(event.event_id)
            state.input_offset = handle.tell()
        return events


class MediaInspector:
    def inspect_images(self, paths: Iterable[Path]) -> list[ImageInspection]:
        return [self.inspect_image(path) for path in paths]

    def inspect_videos(self, paths: Iterable[Path]) -> list[VideoInspection]:
        return [self.inspect_video(path) for path in paths]

    def inspect_image(self, path: Path) -> ImageInspection:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not path.exists():
            return ImageInspection(
                path=path,
                exists=False,
                mime_type=mime_type,
                findings=(MediaFinding("error", "image_missing", "Image file does not exist.", str(path)),),
            )
        findings: list[MediaFinding] = []
        byte_size = path.stat().st_size
        width = height = None
        mode = None
        try:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size
                mode = image.mode
        except Exception as exc:
            findings.append(MediaFinding("error", "image_unreadable", f"Image could not be decoded: {exc}", str(path)))
        if byte_size == 0:
            findings.append(MediaFinding("error", "image_empty", "Image file is empty.", str(path)))
        if width is not None and height is not None:
            if width < 256 or height < 256:
                findings.append(MediaFinding("warning", "image_low_resolution", "Image resolution is below 256px on one axis.", str(path)))
            aspect_ratio = width / max(1, height)
            if aspect_ratio < 0.2 or aspect_ratio > 5:
                findings.append(MediaFinding("warning", "image_extreme_aspect_ratio", "Image aspect ratio looks extreme.", str(path)))
        return ImageInspection(path=path, exists=True, mime_type=mime_type, width=width, height=height, mode=mode, byte_size=byte_size, findings=tuple(findings))

    def inspect_video(self, path: Path) -> VideoInspection:
        if not path.exists():
            return VideoInspection(
                path=path,
                exists=False,
                findings=(MediaFinding("error", "video_missing", "Video file does not exist.", str(path)),),
            )
        findings: list[MediaFinding] = []
        byte_size = path.stat().st_size
        if byte_size == 0:
            findings.append(MediaFinding("error", "video_empty", "Video file is empty.", str(path)))
        duration = width = height = None
        frame_rate = None
        try:
            completed = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if completed.returncode != 0:
                findings.append(MediaFinding("error", "video_probe_failed", completed.stderr.strip() or "ffprobe failed.", str(path)))
            else:
                data = json.loads(completed.stdout or "{}")
                format_info = data.get("format") if isinstance(data.get("format"), dict) else {}
                if format_info.get("duration") is not None:
                    duration = float(format_info["duration"])
                streams = data.get("streams") if isinstance(data.get("streams"), list) else []
                video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
                width = int(video_stream["width"]) if video_stream.get("width") is not None else None
                height = int(video_stream["height"]) if video_stream.get("height") is not None else None
                frame_rate = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
        except FileNotFoundError:
            findings.append(MediaFinding("warning", "ffprobe_missing", "ffprobe is not installed, so video understanding is metadata-limited.", str(path)))
        except Exception as exc:
            findings.append(MediaFinding("error", "video_unreadable", f"Video could not be inspected: {exc}", str(path)))
        if duration is not None and duration <= 0:
            findings.append(MediaFinding("error", "video_zero_duration", "Video duration is zero.", str(path)))
        if width is not None and height is not None and (width < 256 or height < 256):
            findings.append(MediaFinding("warning", "video_low_resolution", "Video resolution is below 256px on one axis.", str(path)))
        return VideoInspection(path=path, exists=True, duration_seconds=duration, width=width, height=height, frame_rate=frame_rate, byte_size=byte_size, findings=tuple(findings))


class ReaderAgent:
    name = "reader"

    def process(self, events: list[StreamEvent]) -> Optional[AgentOutputEvent]:
        if not events:
            return None
        text = "".join(event.content_text() for event in events)
        return AgentOutputEvent(
            agent_name=self.name,
            kind="agent.reader.batch",
            source_event_id=events[-1].event_id,
            payload={
                "event_count": len(events),
                "done_count": sum(1 for event in events if event.is_done()),
                "text_preview": text[:2000],
                "source_event_ids": [event.event_id for event in events if event.event_id],
            },
        )


class WriterAgent:
    name = "writer"

    def process(self, events: list[StreamEvent]) -> Optional[AgentOutputEvent]:
        if not events:
            return None
        completed = [event for event in events if event.is_done()]
        return AgentOutputEvent(
            agent_name=self.name,
            kind="agent.writer.summary",
            source_event_id=events[-1].event_id,
            payload={
                "received_events": len(events),
                "completed": bool(completed),
                "last_content": events[-1].content_text(),
            },
        )


class ReviewerAgent:
    name = "reviewer"

    def __init__(self, inspector: Optional[MediaInspector] = None) -> None:
        self.inspector = inspector or MediaInspector()

    def process(self, events: list[StreamEvent], image_paths: Iterable[Path], video_paths: Iterable[Path]) -> Optional[AgentOutputEvent]:
        image_reports = self.inspector.inspect_images(image_paths)
        video_reports = self.inspector.inspect_videos(video_paths)
        findings = [
            *[finding for report in image_reports for finding in report.findings],
            *[finding for report in video_reports for finding in report.findings],
        ]
        text = "".join(event.content_text() for event in events)
        for event in events:
            error_message = event.metadata.get("error_message")
            if error_message:
                findings.append(MediaFinding("error", "llm_stream_error", str(error_message)[:1000]))
            if "failed" in event.kind.lower():
                findings.append(MediaFinding("error", "llm_stream_failed", f"Stream event failed: {event.kind}"))
        if "unknown" in text.lower():
            findings.append(MediaFinding("warning", "placeholder_text", "Stream output contains placeholder text."))
        if not text.strip() and events:
            findings.append(MediaFinding("warning", "empty_stream_content", "Stream events were received but content was empty."))
        if not events and not findings:
            return None
        return AgentOutputEvent(
            agent_name=self.name,
            kind="agent.reviewer.findings",
            source_event_id=events[-1].event_id if events else None,
            payload={
                "event_count": len(events),
                "image_reports": [report.as_dict() for report in image_reports],
                "video_reports": [report.as_dict() for report in video_reports],
                "findings": [finding.as_dict() for finding in findings],
            },
        )


class PromptIteratorAgent:
    name = "prompt-iterator"

    def process(self, state: ContinuousAgentState, review: Optional[AgentOutputEvent]) -> Optional[AgentOutputEvent]:
        if review is None:
            return None
        findings = [
            MediaFinding(
                severity=str(item.get("severity") or "info"),
                code=str(item.get("code") or "finding"),
                message=str(item.get("message") or ""),
                path=item.get("path"),
            )
            for item in review.payload.get("findings", [])
            if isinstance(item, dict)
        ]
        actionable = [finding for finding in findings if finding.severity in {"warning", "error"}]
        if not actionable:
            return None
        state.prompt_revision += 1
        base_prompt = state.current_prompt or "Generate a precise Blueprint project output."
        correction = "; ".join(f"{finding.code}: {finding.message}" for finding in actionable[:6])
        proposal = PromptIterationProposal(
            revision=state.prompt_revision,
            prompt=f"{base_prompt}\n\nRevision {state.prompt_revision}: Correct these observed issues: {correction}",
            reason="Reviewer found imperfections that should be corrected in the next prompt iteration.",
            findings=tuple(actionable),
        )
        state.current_prompt = proposal.prompt
        return AgentOutputEvent(
            agent_name=self.name,
            kind="agent.prompt_iteration.proposal",
            source_event_id=review.source_event_id,
            payload=proposal.as_dict(),
        )


class ContinuousAgentCoordinator:
    def __init__(
        self,
        store: JsonlStreamStore,
        *,
        image_paths: Iterable[Path] = (),
        video_paths: Iterable[Path] = (),
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.image_paths = tuple(image_paths)
        self.video_paths = tuple(video_paths)
        self.poll_interval_seconds = poll_interval_seconds
        self.reader = ReaderAgent()
        self.writer = WriterAgent()
        self.reviewer = ReviewerAgent()
        self.iterator = PromptIteratorAgent()
        self.stop_event = threading.Event()

    def run_cycle_report(self, state: ContinuousAgentState, *, cycle_index: int = 0) -> ContinuousAgentCycleReport:
        events = self.store.read_new_events(state)
        outputs: list[AgentOutputEvent] = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            reader_future = executor.submit(self.reader.process, events)
            writer_future = executor.submit(self.writer.process, events)
            review_future = executor.submit(self.reviewer.process, events, self.image_paths, self.video_paths)

            reader_output = reader_future.result()
            writer_output = writer_future.result()
            review_output = review_future.result()

        if reader_output:
            outputs.append(reader_output)
        if writer_output:
            outputs.append(writer_output)
        if review_output:
            outputs.append(review_output)

        iterator_output = self.iterator.process(state, review_output)
        if iterator_output:
            outputs.append(iterator_output)
        for output in outputs:
            self.store.append_agent_output(output)
        self.store.save_state(state)
        return ContinuousAgentCycleReport(
            cycle_index=cycle_index,
            new_event_count=len(events),
            output_count=len(outputs),
            output_agent_names=tuple(output.agent_name for output in outputs),
            input_offset=state.input_offset,
            prompt_revision=state.prompt_revision,
        )

    def run_cycle(self, state: ContinuousAgentState) -> int:
        return self.run_cycle_report(state).output_count

    def run(
        self,
        *,
        max_cycles: Optional[int] = None,
        on_cycle: Optional[Callable[[ContinuousAgentCycleReport], None]] = None,
    ) -> None:
        self.store.ensure()
        state = self.store.load_state()
        cycle = 0
        while not self.stop_event.is_set():
            cycle += 1
            report = self.run_cycle_report(state, cycle_index=cycle)
            if on_cycle:
                on_cycle(report)
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        self.stop_event.set()


def paths_from_env(name: str) -> tuple[Path, ...]:
    value = os.getenv(name, "")
    return tuple(Path(item).expanduser() for item in value.split(os.pathsep) if item.strip())
