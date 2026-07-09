#!/usr/bin/env python3
"""Run a Blueprint job and render the dashboard/3D view back into the terminal."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.terminal_dashboard import DashboardRenderConfig, render_dashboard_image
from blueprint_core.terminal_images import TerminalImageRenderConfig, render_images


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000/api"
DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000"
DEFAULT_PROMPT = "Blue Sentinel desktop environmental monitor with USB-C power, OLED display, I2C sensors, ESP32-S3, airflow module, and printable enclosure."
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_OUTPUT_DIR = ROOT_DIR / ".logs" / "terminal-dashboard"
DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 960


@dataclass(frozen=True)
class GenerateRequest:
    prompt: str
    workflow: str
    provider: str
    model: str
    generate_image: bool = False

    def to_json_obj(self) -> dict[str, object]:
        return {
            "prompt": self.prompt,
            "workflow": self.workflow,
            "provider": self.provider,
            "model": self.model,
            "generate_image": self.generate_image,
            "image_data": None,
        }


@dataclass(frozen=True)
class GeneratedProject:
    project_id: str
    job_id: str
    title: str
    provider: str
    model: str
    response: dict[str, Any]


@dataclass(frozen=True)
class SnapshotTarget:
    url: str
    label: str
    project_id: str = ""


class DashboardScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunContext:
    output_dir: Path
    backend_log_path: Path
    backend_log_start_offset: int


class ManagedProcessGroup:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []

    def add(self, process: subprocess.Popen[str]) -> None:
        self.processes.append(process)

    def terminate_all(self) -> None:
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            try:
                process.terminate()
            except ProcessLookupError:
                continue
        deadline = time.monotonic() + 8
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            remaining = max(0.1, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_backend_url(value: str) -> str:
    trimmed = value.strip().rstrip("/")
    if not trimmed:
        return DEFAULT_BACKEND_URL
    return trimmed if trimmed.endswith("/api") else f"{trimmed}/api"


def normalize_frontend_url(value: str) -> str:
    return value.strip().rstrip("/") or DEFAULT_FRONTEND_URL


def parse_host_port(url: str, *, default_port: int) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise DashboardScriptError(f"URL must include a host: {url}")
    return parsed.hostname, parsed.port or default_port


def http_ready(url: str, *, timeout_seconds: float = 2.0) -> bool:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def wait_for_url(url: str, *, label: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if http_ready(url):
            print(f"[terminal-dashboard] {label} ready at {url}", flush=True)
            return
        time.sleep(1)
    raise DashboardScriptError(f"{label} did not become ready at {url}")


def open_log(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def start_backend(backend_url: str, output_dir: Path, processes: ManagedProcessGroup) -> None:
    if http_ready(backend_url):
        print(f"[terminal-dashboard] backend already running at {backend_url}", flush=True)
        return

    host, port = parse_host_port(backend_url, default_port=8000)
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable
    command = [python_bin, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)]
    log_handle = open_log(output_dir / "backend.log")
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    env["BLUEPRINT_DEV_MODE"] = "true"
    env["DATABASE_BACKEND"] = "sqlite"
    env["JOB_METADATA_BACKEND"] = "sqlite"
    print(f"[terminal-dashboard] starting backend: {' '.join(command)}", flush=True)
    process = subprocess.Popen(command, cwd=ROOT_DIR, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    processes.add(process)
    wait_for_url(backend_url, label="backend", timeout_seconds=90)


def start_frontend(frontend_url: str, backend_url: str, output_dir: Path, processes: ManagedProcessGroup) -> None:
    if http_ready(frontend_url):
        print(f"[terminal-dashboard] frontend already running at {frontend_url}", flush=True)
        return

    host, port = parse_host_port(frontend_url, default_port=3000)
    command = ["npm", "run", "dev", "--", "--hostname", host, "--port", str(port)]
    log_handle = open_log(output_dir / "frontend.log")
    env = dict(os.environ)
    env["NEXT_PUBLIC_API_URL"] = backend_url
    print(f"[terminal-dashboard] starting frontend: {' '.join(command)}", flush=True)
    process = subprocess.Popen(command, cwd=ROOT_DIR / "frontend", env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    processes.add(process)
    wait_for_url(frontend_url, label="frontend", timeout_seconds=120)


def decode_http_error(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    if not body.strip():
        return f"HTTP {exc.code}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"HTTP {exc.code}: {body[:1200]}"
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    if isinstance(detail, dict):
        code = str(detail.get("code") or "").strip()
        message = detail.get("message") or detail.get("detail") or detail.get("reason") or json.dumps(detail, sort_keys=True)
        if code and code not in str(message):
            message = f"{code}: {message}"
    else:
        message = str(detail)
    return f"HTTP {exc.code}: {message}"


def backend_failure_excerpt(path: Path, *, start_offset: int, max_lines: int = 24, max_chars: int = 5000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            if start_offset > 0:
                handle.seek(start_offset)
            text = handle.read()
    except OSError:
        return ""
    if not text.strip():
        return ""

    markers = (
        " ERROR ",
        " WARNING ",
        "LLM structured call failed",
        "Pipeline execution",
        "Generation failed",
        "Generation unavailable",
        "validation error",
        "Invalid JSON",
    )
    lines = text.splitlines()
    interesting = [line for line in lines if any(marker in line for marker in markers)]
    excerpt_lines = (interesting or lines)[-max_lines:]
    return "\n".join(excerpt_lines)[-max_chars:]


def print_failure_context(context: RunContext) -> None:
    excerpt = backend_failure_excerpt(context.backend_log_path, start_offset=context.backend_log_start_offset)
    if excerpt:
        print(f"[terminal-dashboard] backend_log={context.backend_log_path}", file=sys.stderr)
        print("[terminal-dashboard] backend_failure_excerpt:", file=sys.stderr)
        print(excerpt, file=sys.stderr)


def post_json(url: str, payload: dict[str, object], *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DashboardScriptError(decode_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise DashboardScriptError(f"request failed: {exc.reason}") from exc


def get_json(url: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DashboardScriptError(decode_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise DashboardScriptError(f"request failed: {exc.reason}") from exc


def run_generate_job(backend_url: str, request: GenerateRequest, *, timeout_seconds: float, output_dir: Path, run_id: str) -> GeneratedProject:
    print(f"[terminal-dashboard] running real job provider={request.provider} model={request.model}", flush=True)
    print(f"[terminal-dashboard] prompt={request.prompt!r}", flush=True)
    response = post_json(
        f"{backend_url}/generate",
        request.to_json_obj(),
        timeout_seconds=timeout_seconds,
    )
    project_ir = response.get("project_ir") if isinstance(response.get("project_ir"), dict) else {}
    overview = project_ir.get("overview") if isinstance(project_ir.get("overview"), dict) else {}
    metadata = project_ir.get("assembly_metadata") if isinstance(project_ir.get("assembly_metadata"), dict) else {}
    project_id = str(response.get("project_id") or metadata.get("project_id") or "")
    if not project_id:
        raise DashboardScriptError("Generation succeeded but did not return a project_id.")
    response_path = output_dir / f"{run_id}-generate-response.json"
    response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[terminal-dashboard] job_id={response.get('job_id') or ''}", flush=True)
    print(f"[terminal-dashboard] project_id={project_id}", flush=True)
    print(f"[terminal-dashboard] title={overview.get('title') or 'Untitled'}", flush=True)
    print(f"[terminal-dashboard] generation_response={response_path}", flush=True)
    return GeneratedProject(
        project_id=project_id,
        job_id=str(response.get("job_id") or ""),
        title=str(overview.get("title") or ""),
        provider=request.provider,
        model=request.model,
        response=response,
    )


def load_project_ir_from_backend(backend_url: str, project_id: str) -> dict[str, Any]:
    payload = get_json(f"{backend_url}/projects/{urllib.parse.quote(project_id, safe='')}")
    project_ir = payload.get("project_ir")
    if not isinstance(project_ir, dict):
        raise DashboardScriptError(f"Project {project_id!r} did not return project_ir.")
    return project_ir


def load_example_ir(example: str) -> dict[str, Any]:
    filename = example if example.endswith(".json") else f"{example}.json"
    path = ROOT_DIR / "frontend" / "public" / "examples" / filename
    if not path.exists():
        raise DashboardScriptError(f"Example not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DashboardScriptError(f"Example did not contain a JSON object: {path}")
    metadata = payload.get("assembly_metadata") if isinstance(payload.get("assembly_metadata"), dict) else {}
    payload["assembly_metadata"] = {
        **metadata,
        "project_id": metadata.get("project_id") or f"example-{path.stem}",
        "runtime_provider": metadata.get("runtime_provider") or "local-example",
        "runtime_model": metadata.get("runtime_model") or path.name,
    }
    return payload


def build_project_snapshot_target(frontend_url: str, project_id: str, *, tab: str) -> SnapshotTarget:
    encoded = urllib.parse.quote(project_id, safe="")
    url = f"{frontend_url}/project/{encoded}?tab={urllib.parse.quote(tab, safe='')}"
    return SnapshotTarget(url=url, label=f"project:{project_id}:{tab}", project_id=project_id)


def build_example_snapshot_target(frontend_url: str, example: str, *, tab: str) -> SnapshotTarget:
    name = example[:-5] if example.endswith(".json") else example
    query = urllib.parse.urlencode({"example": name, "tab": tab})
    return SnapshotTarget(url=f"{frontend_url}/?{query}", label=f"example:{name}:{tab}")


def find_chromium(explicit: Optional[str] = None) -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"])
    for candidate in candidates:
        if not candidate:
            continue
        if Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser())
        found = shutil.which(candidate)
        if found:
            return found
    raise DashboardScriptError("Could not find chromium/google-chrome. Install Chromium or pass --chromium /path/to/chromium.")


def capture_screenshot(
    *,
    target: SnapshotTarget,
    output_path: Path,
    chromium: str,
    width: int,
    height: int,
    virtual_time_budget_ms: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        chromium,
        "--headless",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={virtual_time_budget_ms}",
        f"--screenshot={output_path}",
        target.url,
    ]
    print(f"[terminal-dashboard] snapshot_url={target.url}", flush=True)
    print(f"[terminal-dashboard] chromium={chromium}", flush=True)
    completed = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=max(30, virtual_time_budget_ms / 1000 + 30))
    if completed.returncode != 0:
        raise DashboardScriptError(f"Chromium screenshot failed with code {completed.returncode}:\n{completed.stdout[-4000:]}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise DashboardScriptError(f"Chromium did not write a screenshot to {output_path}")
    print(f"[terminal-dashboard] screenshot={output_path}", flush=True)


def render_pillow_dashboard(
    *,
    project_ir: dict[str, Any],
    output_path: Path,
    subtitle: str,
    width: int,
    height: int,
) -> None:
    render_dashboard_image(
        project_ir,
        output_path,
        subtitle=subtitle,
        config=DashboardRenderConfig(width=width, height=height),
    )
    print(f"[terminal-dashboard] rendered={output_path}", flush=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--start-services", action="store_true", help="Start backend and frontend if they are not already responding.")
    parser.add_argument("--project-id", default=None, help="Existing project id to render instead of running /api/generate.")
    parser.add_argument("--example", default=None, help="Render a frontend public example, e.g. plant_watering. Skips real generation.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--workflow", default="default")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--generate-image", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--tab", default="mechanical", choices=("overview", "bom", "mechanical", "assembly", "video", "jobs"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--renderer", choices=("pillow", "browser"), default="pillow", help="pillow renders a no-browser terminal dashboard. browser screenshots the live frontend with Chromium.")
    parser.add_argument("--chromium", default=None)
    parser.add_argument("--viewport-width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--viewport-height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--virtual-time-budget-ms", type=int, default=9000)
    parser.add_argument("--no-terminal-image", action="store_true")
    parser.add_argument("--terminal-width", type=int, default=None)
    parser.add_argument("--terminal-max-height", type=int, default=48)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_log_path = output_dir / "backend.log"
    run_context = RunContext(
        output_dir=output_dir,
        backend_log_path=backend_log_path,
        backend_log_start_offset=file_size(backend_log_path),
    )
    run_id = utc_run_id()
    backend_url = normalize_backend_url(args.backend_url)
    frontend_url = normalize_frontend_url(args.frontend_url)
    processes = ManagedProcessGroup()
    atexit.register(processes.terminate_all)

    try:
        needs_backend = not args.example
        needs_frontend = args.renderer == "browser"

        if args.start_services:
            if needs_backend:
                start_backend(backend_url, output_dir, processes)
            if needs_frontend:
                start_frontend(frontend_url, backend_url, output_dir, processes)
        else:
            if needs_backend and not http_ready(backend_url):
                raise DashboardScriptError(f"Backend is not ready at {backend_url}. Start it or rerun with --start-services.")
            if needs_frontend and not http_ready(frontend_url):
                raise DashboardScriptError(f"Frontend is not ready at {frontend_url}. Start it or rerun with --start-services.")

        project_ir: dict[str, Any] | None = None
        if args.example:
            target = build_example_snapshot_target(frontend_url, args.example, tab=args.tab)
            project_ir = load_example_ir(args.example)
        elif args.project_id:
            target = build_project_snapshot_target(frontend_url, args.project_id, tab=args.tab)
            if args.renderer == "pillow":
                project_ir = load_project_ir_from_backend(backend_url, args.project_id)
        else:
            request = GenerateRequest(
                prompt=args.prompt,
                workflow=args.workflow,
                provider=args.provider,
                model=args.model,
                generate_image=bool(args.generate_image),
            )
            generated = run_generate_job(backend_url, request, timeout_seconds=args.request_timeout_seconds, output_dir=output_dir, run_id=run_id)
            target = build_project_snapshot_target(frontend_url, generated.project_id, tab=args.tab)
            project_ir = generated.response.get("project_ir") if isinstance(generated.response.get("project_ir"), dict) else None

        safe_label = target.label.replace(":", "-")
        if args.renderer == "pillow":
            if project_ir is None:
                raise DashboardScriptError("No project IR was available for Pillow rendering.")
            screenshot_path = output_dir / f"{run_id}-{safe_label}-terminal-dashboard.png"
            render_pillow_dashboard(
                project_ir=project_ir,
                output_path=screenshot_path,
                subtitle=target.label,
                width=args.viewport_width,
                height=args.viewport_height,
            )
        else:
            if not args.start_services and not http_ready(frontend_url):
                raise DashboardScriptError(f"Frontend is not ready at {frontend_url}. Start it or rerun with --start-services.")
            chromium = find_chromium(args.chromium)
            screenshot_path = output_dir / f"{run_id}-{safe_label}.png"
            capture_screenshot(
                target=target,
                output_path=screenshot_path,
                chromium=chromium,
                width=args.viewport_width,
                height=args.viewport_height,
                virtual_time_budget_ms=args.virtual_time_budget_ms,
            )

        if not args.no_terminal_image:
            config = TerminalImageRenderConfig(width=args.terminal_width, max_height=args.terminal_max_height)
            print(render_images([screenshot_path], config), flush=True)

        print(f"[terminal-dashboard] done image={screenshot_path}", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\n[terminal-dashboard] interrupted", file=sys.stderr)
        processes.terminate_all()
        return 130
    except (DashboardScriptError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"[terminal-dashboard] error: {exc}", file=sys.stderr)
        print_failure_context(run_context)
        processes.terminate_all()
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
