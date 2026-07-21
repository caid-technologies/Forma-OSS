#!/usr/bin/env python3
"""Exercise Forma Edge live streaming with three sample configurations."""

from __future__ import annotations

import argparse
import json
import select
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
RUST_DIR = ROOT_DIR / "rust"
DEFAULT_CONFIG = RUST_DIR / "blueprint-edge" / "config" / "example.toml"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / ".logs" / "rust-stream-configs"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
DEFAULT_LLAMA_CPP_MODEL = "local-model"


@dataclass(frozen=True)
class SampleConfig:
    name: str
    provider: str
    command: list[str]
    port: int
    artifact_paths: list[Path]
    readiness_url: str | None = None
    skip_reason: str | None = None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def http_json(url: str, timeout_seconds: float = 2.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def http_reachable(url: str, timeout_seconds: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def choose_ollama_model(base_url: str, preferred: str) -> tuple[str, str | None]:
    tags = http_json(f"{base_url.rstrip('/')}/api/tags")
    if tags is None:
        return preferred, f"Ollama is not reachable at {base_url}"

    models = [item.get("name") for item in tags.get("models", []) if item.get("name")]
    if preferred in models:
        return preferred, None
    if models:
        return models[0], f"Preferred Ollama model {preferred!r} not found; using {models[0]!r}"
    return preferred, "Ollama is reachable but returned no local models"


def llama_cpp_available(base_url: str) -> bool:
    base = base_url.rstrip("/")
    return http_reachable(f"{base}/v1/models") or http_reachable(f"{base}/health")


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def tail_text(value: str, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def wait_for_listener(proc: subprocess.Popen[str], timeout_seconds: float) -> tuple[str, list[str]]:
    deadline = time.monotonic() + timeout_seconds
    stderr_lines: list[str] = []
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"stream process exited before listener was ready: rc={proc.returncode}")
        if not proc.stderr:
            time.sleep(0.025)
            continue
        readable, _, _ = select.select([proc.stderr], [], [], 0.1)
        if not readable:
            continue
        line = proc.stderr.readline()
        if not line:
            continue
        stripped = line.rstrip()
        stderr_lines.append(stripped)
        if "live stream listening" in line:
            return stripped, stderr_lines
    raise TimeoutError("timed out waiting for live stream listener")


def config_cli_arg(config: Path) -> str:
    try:
        return str(config.relative_to(RUST_DIR))
    except ValueError:
        return str(config)


def read_first_live_event(port: int, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                sock.settimeout(max(1.0, deadline - time.monotonic()))
                data = b""
                while b"\n" not in data and time.monotonic() < deadline:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    raise TimeoutError("listener connection closed before receiving data")
                line = data.splitlines()[0].decode("utf-8", errors="replace")
                return json.loads(line)
        except (ConnectionRefusedError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.05)
    raise TimeoutError(f"did not receive a live JSONL event: {last_error}")


def run_sample(sample: SampleConfig, output_dir: Path, timeout_seconds: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": sample.name,
        "provider": sample.provider,
        "command": sample.command,
        "listen_tcp": f"127.0.0.1:{sample.port}",
        "artifact_paths": [str(path) for path in sample.artifact_paths],
    }
    if sample.skip_reason:
        result.update({"status": "skipped", "skip_reason": sample.skip_reason})
        return result

    started_at = time.monotonic()
    proc = subprocess.Popen(
        sample.command,
        cwd=RUST_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr_prefix: list[str] = []
    try:
        ready_line, stderr_prefix = wait_for_listener(proc, timeout_seconds=min(15.0, timeout_seconds))
        first_event = read_first_live_event(sample.port, timeout_seconds=min(30.0, timeout_seconds))
        received_before_exit = proc.poll() is None

        stdout, stderr_rest = proc.communicate(timeout=timeout_seconds)
        elapsed_seconds = time.monotonic() - started_at

        first_event_path = output_dir / f"{sample.name}-first-event.json"
        first_event_path.write_text(json.dumps(first_event, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        artifact_counts = {
            str(path): count_jsonl_lines(path)
            for path in sample.artifact_paths
            if path.suffix == ".jsonl"
        }
        status = "passed" if proc.returncode == 0 else "failed"
        result.update(
            {
                "status": status,
                "returncode": proc.returncode,
                "elapsed_seconds": elapsed_seconds,
                "listener_ready": ready_line,
                "received_before_process_exit": received_before_exit,
                "first_event_path": str(first_event_path),
                "first_event_kind": first_event.get("kind"),
                "first_event_provider": first_event.get("source", {}).get("provider"),
                "first_event_sequence": first_event.get("payload", {}).get("sequence"),
                "artifact_counts": artifact_counts,
                "stdout_tail": tail_text(stdout),
                "stderr_tail": tail_text("\n".join([*stderr_prefix, stderr_rest])),
            }
        )
        if proc.returncode != 0:
            result["error"] = f"stream process exited with {proc.returncode}"
    except Exception as exc:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stdout, stderr_rest = proc.communicate(timeout=5)
        result.update(
            {
                "status": "failed",
                "returncode": proc.returncode,
                "elapsed_seconds": time.monotonic() - started_at,
                "error": str(exc),
                "stdout_tail": tail_text(stdout),
                "stderr_tail": tail_text("\n".join([*stderr_prefix, stderr_rest])),
            }
        )
    return result


def build_samples(args: argparse.Namespace, run_dir: Path) -> list[SampleConfig]:
    config_arg = ["--config", config_cli_arg(args.config)]
    ollama_model, ollama_note = choose_ollama_model(args.ollama_base_url, args.ollama_model)
    ollama_skip = None if ollama_note is None or ollama_note.startswith("Preferred") else ollama_note
    llama_skip = None
    if not llama_cpp_available(args.llama_cpp_base_url):
        llama_skip = f"llama.cpp server is not reachable at {args.llama_cpp_base_url}"

    samples: list[SampleConfig] = []

    port = reserve_port()
    samples.append(
        SampleConfig(
            name="ollama-live-tcp",
            provider="ollama",
            port=port,
            readiness_url=f"{args.ollama_base_url.rstrip('/')}/api/tags",
            skip_reason=ollama_skip,
            artifact_paths=[],
            command=[
                "cargo",
                "run",
                "-q",
                "-p",
                "blueprint-edge",
                "--",
                "ollama-stream",
                *config_arg,
                "--base-url",
                args.ollama_base_url,
                "--model",
                ollama_model,
                "--prompt",
                "Reply with exactly: blue stream ok",
                "--stdout",
                "false",
                "--listen-tcp",
                f"127.0.0.1:{port}",
                "--live-replay",
                "32",
                "--wait-for-live-listener",
                "--live-wait-seconds",
                "15",
            ],
        )
    )

    port = reserve_port()
    planner_path = run_dir / "ollama-file-fanout" / "planner.jsonl"
    critic_path = run_dir / "ollama-file-fanout" / "critic.jsonl"
    samples.append(
        SampleConfig(
            name="ollama-live-tcp-file-fanout",
            provider="ollama",
            port=port,
            readiness_url=f"{args.ollama_base_url.rstrip('/')}/api/tags",
            skip_reason=ollama_skip,
            artifact_paths=[planner_path, critic_path],
            command=[
                "cargo",
                "run",
                "-q",
                "-p",
                "blueprint-edge",
                "--",
                "ollama-stream",
                *config_arg,
                "--base-url",
                args.ollama_base_url,
                "--model",
                ollama_model,
                "--prompt",
                "Stream three short words about a blue circuit board.",
                "--stdout",
                "false",
                "--listen-tcp",
                f"127.0.0.1:{port}",
                "--live-replay",
                "32",
                "--agent-output",
                f"planner={planner_path}",
                "--agent-output",
                f"critic={critic_path}",
            ],
        )
    )

    port = reserve_port()
    stream_id = f"stream-test-{utc_stamp().lower()}"
    spacebase_root = ROOT_DIR / ".spacebase" / "streams" / stream_id
    samples.append(
        SampleConfig(
            name="llama-cpp-live-tcp-spacebase",
            provider="llama.cpp",
            port=port,
            readiness_url=f"{args.llama_cpp_base_url.rstrip('/')}/v1/models",
            skip_reason=llama_skip,
            artifact_paths=[
                spacebase_root / "events.jsonl",
                spacebase_root / "agents" / "planner.jsonl",
                spacebase_root / "agents" / "critic.jsonl",
            ],
            command=[
                "cargo",
                "run",
                "-q",
                "-p",
                "blueprint-edge",
                "--",
                "llama-cpp-stream",
                *config_arg,
                "--base-url",
                args.llama_cpp_base_url,
                "--model",
                args.llama_cpp_model,
                "--prompt",
                "Stream one sentence about a blue robot.",
                "--stream-id",
                stream_id,
                "--listen-tcp",
                f"127.0.0.1:{port}",
                "--live-replay",
                "32",
            ],
        )
    )

    if ollama_note and ollama_note.startswith("Preferred"):
        for sample in samples:
            if sample.provider == "ollama":
                sample.artifact_paths.append(run_dir / f"{sample.name}-model-note.txt")
                sample.artifact_paths[-1].write_text(ollama_note + "\n", encoding="utf-8")

    return samples


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--llama-cpp-base-url", default=DEFAULT_LLAMA_CPP_BASE_URL)
    parser.add_argument("--llama-cpp-model", default=DEFAULT_LLAMA_CPP_MODEL)
    parser.add_argument("--require-all", action="store_true", help="Treat skipped provider configs as failures.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    args.config = args.config.resolve()
    if not args.config.exists():
        print(f"[rust-stream-test] missing config: {args.config}", file=sys.stderr)
        return 2
    if not RUST_DIR.exists():
        print(f"[rust-stream-test] missing rust workspace: {RUST_DIR}", file=sys.stderr)
        return 2

    run_dir = (args.output_dir or (DEFAULT_OUTPUT_ROOT / utc_stamp())).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    samples = build_samples(args, run_dir)

    print(f"[rust-stream-test] output_dir={run_dir}")
    print(f"[rust-stream-test] running {len(samples)} sample configuration(s)")

    results = []
    for sample in samples:
        print(f"[rust-stream-test] starting {sample.name} provider={sample.provider}")
        result = run_sample(sample, run_dir, args.timeout_seconds)
        results.append(result)
        status = result["status"].upper()
        detail = result.get("error") or result.get("skip_reason") or result.get("first_event_kind", "")
        print(f"[rust-stream-test] {status} {sample.name} {detail}")

    summary = {
        "created_at": utc_stamp(),
        "output_dir": str(run_dir),
        "config": str(args.config),
        "results": results,
        "totals": {
            "passed": sum(1 for item in results if item["status"] == "passed"),
            "failed": sum(1 for item in results if item["status"] == "failed"),
            "skipped": sum(1 for item in results if item["status"] == "skipped"),
            "total": len(results),
        },
    }
    summary_path = run_dir / "summary.json"
    latest_path = DEFAULT_OUTPUT_ROOT / "latest-summary.json"
    DEFAULT_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[rust-stream-test] summary={summary_path}")
    print(f"[rust-stream-test] latest={latest_path}")
    print(
        "[rust-stream-test] totals "
        f"passed={summary['totals']['passed']} "
        f"failed={summary['totals']['failed']} "
        f"skipped={summary['totals']['skipped']} "
        f"total={summary['totals']['total']}"
    )

    if summary["totals"]["failed"]:
        return 1
    if args.require_all and summary["totals"]["skipped"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
