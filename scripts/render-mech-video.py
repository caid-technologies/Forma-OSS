#!/usr/bin/env python3
"""Render a mechanical dashboard turntable MP4 without opening a browser."""

from __future__ import annotations

import argparse
import atexit
import importlib.util
import json
import math
import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.terminal_dashboard import DashboardRenderConfig, render_dashboard_image
from blueprint_core.terminal_images import TerminalImageRenderConfig, render_images


DEFAULT_OUTPUT_DIR = ROOT_DIR / ".logs" / "terminal-dashboard"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 900


class MechVideoScriptError(RuntimeError):
    pass


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_dashboard_cli() -> ModuleType:
    path = ROOT_DIR / "scripts" / "run-terminal-dashboard.py"
    spec = importlib.util.spec_from_file_location("run_terminal_dashboard_for_video", path)
    if spec is None or spec.loader is None:
        raise MechVideoScriptError(f"Could not load dashboard helper script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "mechanical"


def project_ir_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MechVideoScriptError("Input JSON must contain a JSON object.")
    for key in ("project_ir", "hardware_ir", "ir"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def load_input_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MechVideoScriptError(f"Input JSON not found: {path}")
    return project_ir_from_payload(json.loads(path.read_text(encoding="utf-8")))


def frame_count(seconds: float, fps: int) -> int:
    return max(1, int(math.ceil(max(0.1, seconds) * max(1, fps))))


def render_frames(
    *,
    project_ir: dict[str, Any],
    frames_dir: Path,
    frame_total: int,
    width: int,
    height: int,
    start_yaw_degrees: float,
) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index in range(frame_total):
        yaw = start_yaw_degrees + (360.0 * index / max(frame_total, 1))
        output_path = frames_dir / f"frame-{index:04d}.png"
        render_dashboard_image(
            project_ir,
            output_path,
            config=DashboardRenderConfig(
                width=width,
                height=height,
                scene_yaw_degrees=yaw,
                scene_label=f"MECH TURNTABLE {index + 1:03d}/{frame_total:03d}",
            ),
        )
        frames.append(output_path)
        if index == 0 or index == frame_total - 1 or (index + 1) % max(1, frame_total // 4) == 0:
            print(f"[mech-video] rendered_frame={index + 1}/{frame_total}", flush=True)
    return frames


def encode_mp4(*, frames_dir: Path, fps: int, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MechVideoScriptError("ffmpeg is required to encode MP4 output.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame-%04d.png"),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    print(f"[mech-video] encoding={' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    if completed.returncode != 0:
        raise MechVideoScriptError(f"ffmpeg failed with code {completed.returncode}:\n{completed.stdout[-4000:]}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise MechVideoScriptError(f"ffmpeg did not write MP4 output: {output_path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--example", default=None, help="Render a frontend public example, e.g. plant_watering.")
    source.add_argument("--project-id", default=None, help="Load an existing project from the backend.")
    source.add_argument("--input-json", type=Path, default=None, help="Load a project IR or generate-response JSON file.")
    source.add_argument("--generate-job", action="store_true", help="Run /api/generate first, then render that project to MP4.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--start-services", action="store_true")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--workflow", default="default")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--generate-image", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=18)
    parser.add_argument("--viewport-width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--viewport-height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--start-yaw-degrees", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--no-terminal-preview", action="store_true")
    parser.add_argument("--terminal-width", type=int, default=80)
    parser.add_argument("--terminal-max-height", type=int, default=24)
    return parser.parse_args(argv)


def resolve_project_ir(args: argparse.Namespace, dashboard_cli: ModuleType, output_dir: Path, run_id: str) -> tuple[dict[str, Any], str]:
    if args.example:
        return dashboard_cli.load_example_ir(args.example), f"example-{args.example}"
    if args.input_json:
        return load_input_json(args.input_json.expanduser().resolve()), args.input_json.stem

    processes = dashboard_cli.ManagedProcessGroup()
    atexit.register(processes.terminate_all)
    backend_url = dashboard_cli.normalize_backend_url(args.backend_url)
    backend_log_path = output_dir / "backend.log"
    run_context = dashboard_cli.RunContext(
        output_dir=output_dir,
        backend_log_path=backend_log_path,
        backend_log_start_offset=dashboard_cli.file_size(backend_log_path),
    )
    try:
        if args.start_services:
            dashboard_cli.start_backend(backend_url, output_dir, processes)
        elif not dashboard_cli.http_ready(backend_url):
            raise MechVideoScriptError(f"Backend is not ready at {backend_url}. Start it or rerun with --start-services.")

        if args.project_id:
            return dashboard_cli.load_project_ir_from_backend(backend_url, args.project_id), f"project-{args.project_id}"

        if args.generate_job:
            prompt = args.prompt or dashboard_cli.DEFAULT_PROMPT
            request = dashboard_cli.GenerateRequest(
                prompt=prompt,
                workflow=args.workflow,
                provider=args.provider,
                model=args.model,
                generate_image=bool(args.generate_image),
            )
            generated = dashboard_cli.run_generate_job(
                backend_url,
                request,
                timeout_seconds=args.request_timeout_seconds,
                output_dir=output_dir,
                run_id=run_id,
            )
            project_ir = generated.response.get("project_ir")
            if not isinstance(project_ir, dict):
                raise MechVideoScriptError("Generated response did not include project_ir.")
            return project_ir, f"project-{generated.project_id}"
    except Exception as exc:
        dashboard_cli.print_failure_context(run_context)
        raise MechVideoScriptError(str(exc)) from exc

    return dashboard_cli.load_example_ir("plant_watering"), "example-plant_watering"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = utc_run_id()
    dashboard_cli = load_dashboard_cli()

    try:
        project_ir, label = resolve_project_ir(args, dashboard_cli, output_dir, run_id)
        total_frames = frame_count(args.seconds, args.fps)
        name = safe_name(label)
        frames_dir = output_dir / "video-frames" / f"{run_id}-{name}"
        output_path = args.output.expanduser().resolve() if args.output else output_dir / f"{run_id}-{name}-mechanical-turntable.mp4"
        preview_path = output_dir / f"{run_id}-{name}-mechanical-turntable-preview.png"

        print(f"[mech-video] source={label}", flush=True)
        print(f"[mech-video] frames={total_frames} fps={args.fps} seconds={args.seconds}", flush=True)
        frames = render_frames(
            project_ir=project_ir,
            frames_dir=frames_dir,
            frame_total=total_frames,
            width=args.viewport_width,
            height=args.viewport_height,
            start_yaw_degrees=args.start_yaw_degrees,
        )
        shutil.copyfile(frames[len(frames) // 2], preview_path)
        encode_mp4(frames_dir=frames_dir, fps=args.fps, output_path=output_path)

        if not args.no_terminal_preview:
            config = TerminalImageRenderConfig(width=args.terminal_width, max_height=args.terminal_max_height)
            print(render_images([preview_path], config), flush=True)

        if not args.keep_frames:
            shutil.rmtree(frames_dir, ignore_errors=True)

        print(f"[mech-video] preview={preview_path}", flush=True)
        print(f"[mech-video] mp4={output_path}", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\n[mech-video] interrupted", file=sys.stderr)
        return 130
    except (MechVideoScriptError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"[mech-video] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
