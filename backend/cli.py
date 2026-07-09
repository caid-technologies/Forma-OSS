from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from blueprint_core.selectors import split_llm_selector


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_GENERATE_TIMEOUT_SECONDS = 1200


def _api_url(value: str) -> str:
    return value.rstrip("/")


def _fetch_json(url: str) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def _post_json(url: str, payload: dict[str, Any], timeout: int = DEFAULT_GENERATE_TIMEOUT_SECONDS) -> tuple[int, Any]:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = body
        return exc.code, payload


def _parse_llm_selector(value: str | None) -> tuple[str | None, str | None]:
    return split_llm_selector(value)


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _format_cell(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > width:
        text = text[: max(0, width - 3)] + "..."
    return text.ljust(width)


def _job_source_label(job: dict[str, Any]) -> str:
    summary = job.get("result_summary") if isinstance(job.get("result_summary"), dict) else {}
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    source_usage = job.get("source_usage") or summary.get("source_usage") or {}
    if not isinstance(source_usage, dict):
        source_usage = {}
    workflow = str(source_usage.get("workflow") or summary.get("workflow") or payload.get("workflow") or "")
    workflow = workflow.strip().lower().replace("-", "_")
    labels = source_usage.get("source_labels")
    if isinstance(labels, list) and labels:
        return " + ".join(str(label) for label in labels)
    if source_usage.get("web_research") or source_usage.get("firecrawl") or workflow in {"web_research", "firecrawl"}:
        return "Web Research"
    if source_usage.get("catalog") or source_usage.get("data_warehouse") or workflow in {"default", "catalog"}:
        return "Catalog"
    return "-"


def _print_jobs_table(jobs: list[dict[str, Any]]) -> None:
    if not jobs:
        print("No jobs found.")
        return

    columns = [
        ("status", 10),
        ("sender", 12),
        ("action", 28),
        ("source", 16),
        ("job_id", 34),
        ("updated_at", 24),
        ("error", 32),
    ]
    header = "  ".join(_format_cell(name, width) for name, width in columns)
    print(header)
    print("  ".join("-" * width for _, width in columns))
    for job in jobs:
        row = {**job, "source": _job_source_label(job)}
        print("  ".join(_format_cell(row.get(name), width) for name, width in columns))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    api_url = _api_url(args.api_url)
    checks = {
        "root": f"{api_url}/api",
        "jobs": f"{api_url}/api/a2a/jobs?limit=1",
        "components": f"{api_url}/api/components",
    }
    results: dict[str, Any] = {"api_url": api_url, "checks": {}}
    ok = True

    for name, url in checks.items():
        try:
            status, payload = _fetch_json(url)
            check_ok = 200 <= status < 300
            ok = ok and check_ok
            results["checks"][name] = {
                "ok": check_ok,
                "status": status,
                "summary": _summarize_payload(payload),
            }
        except urllib.error.URLError as exc:
            ok = False
            results["checks"][name] = {
                "ok": False,
                "error": str(exc.reason),
            }

    _print_json(results)
    return 0 if ok else 1


def cmd_jobs(args: argparse.Namespace) -> int:
    if args.local:
        from backend.job_store import JobMetadataStore

        jobs = JobMetadataStore(args.db_path, backend="sqlite").list_jobs(
            sender=args.sender,
            status=args.status,
            limit=args.limit,
        )
    else:
        api_url = _api_url(args.api_url)
        params = {"limit": str(args.limit)}
        if args.sender:
            params["sender"] = args.sender
        if args.status:
            params["status"] = args.status
        url = f"{api_url}/api/a2a/jobs?{urllib.parse.urlencode(params)}"
        try:
            status, payload = _fetch_json(url)
        except urllib.error.URLError as exc:
            print(f"Could not reach backend at {api_url}: {exc.reason}", file=sys.stderr)
            return 1
        if status < 200 or status >= 300:
            print(f"Jobs endpoint returned HTTP {status}: {payload}", file=sys.stderr)
            return 1
        jobs = payload if isinstance(payload, list) else []

    if args.json:
        _print_json(jobs)
    else:
        _print_jobs_table(jobs)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    api_url = _api_url(args.api_url)
    try:
        llm_provider, llm_model = _parse_llm_selector(args.llm)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    provider = args.provider or llm_provider
    model = args.model or llm_model
    image_data = args.image_data
    if args.image_file:
        import base64
        import mimetypes

        mime_type = mimetypes.guess_type(args.image_file)[0] or "image/png"
        with open(args.image_file, "rb") as file:
            encoded = base64.b64encode(file.read()).decode("ascii")
        image_data = f"data:{mime_type};base64,{encoded}"

    payload = {
        "prompt": args.prompt,
        "workflow": args.workflow,
        "external_source_provider": args.external_source_provider,
        "image_data": image_data,
        "generate_image": args.generate_image,
        "provider": provider,
        "model": model,
    }
    try:
        status, response = _post_json(f"{api_url}/api/generate", payload, timeout=args.timeout)
    except urllib.error.URLError as exc:
        print(f"Could not reach backend at {api_url}: {exc.reason}", file=sys.stderr)
        return 1

    if status < 200 or status >= 300:
        print(f"Generate endpoint returned HTTP {status}:", file=sys.stderr)
        _print_json(response)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(response, file, indent=2, sort_keys=True)
            file.write("\n")
    else:
        _print_json(response)
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    from backend.seed_db import seed_database

    seed_database()
    return 0


def _summarize_payload(payload: Any) -> Any:
    if isinstance(payload, list):
        return {"items": len(payload)}
    if isinstance(payload, dict):
        if "status" in payload or "service" in payload:
            return {key: payload.get(key) for key in ("status", "service", "version") if key in payload}
        return {"keys": sorted(payload.keys())[:12]}
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blueprint-backend",
        description="Backend utility CLI for the Blueprint FastAPI service.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the FastAPI backend with uvicorn.")
    serve.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to 127.0.0.1.")
    serve.add_argument("--port", default=8000, type=int, help="Port to bind. Defaults to 8000.")
    serve.add_argument("--reload", action="store_true", help="Enable uvicorn reload.")
    serve.set_defaults(func=cmd_serve)

    health = subparsers.add_parser("health", help="Check backend root, jobs, and component endpoints.")
    health.add_argument("--api-url", default=DEFAULT_API_URL, help=f"Backend URL. Defaults to {DEFAULT_API_URL}.")
    health.set_defaults(func=cmd_health)

    jobs = subparsers.add_parser("jobs", help="List A2A job metadata.")
    jobs.add_argument("--api-url", default=DEFAULT_API_URL, help=f"Backend URL. Defaults to {DEFAULT_API_URL}.")
    jobs.add_argument("--status", choices=["queued", "running", "routed", "succeeded", "failed"], help="Filter by job status.")
    jobs.add_argument("--sender", help="Filter by sender.")
    jobs.add_argument("--limit", default=50, type=int, help="Maximum jobs to show, from 1 to 200.")
    jobs.add_argument("--json", action="store_true", help="Print raw JSON.")
    jobs.add_argument("--local", action="store_true", help="Read directly from the local SQLite job store.")
    jobs.add_argument("--db-path", help="SQLite job database path for --local. Defaults to JOB_METADATA_DB_PATH.")
    jobs.set_defaults(func=cmd_jobs)

    generate = subparsers.add_parser("generate", help="Generate a project through the backend API.")
    generate.add_argument("prompt", help="Hardware idea to generate.")
    generate.add_argument("--api-url", default=DEFAULT_API_URL, help=f"Backend URL. Defaults to {DEFAULT_API_URL}.")
    generate.add_argument(
        "--workflow",
        default="default",
        choices=["default", "web_research"],
        help="Generation workflow to use.",
    )
    generate.add_argument("--image-data", help="Optional data URL or base64 image string.")
    generate.add_argument("--image-file", help="Optional local reference image file.")
    generate.add_argument("--generate-image", action="store_true", help="Request a product concept image.")
    generate.add_argument(
        "--external-source-provider",
        choices=["auto", "tavily", "firecrawl"],
        help="Provider for the web_research workflow.",
    )
    generate.add_argument("--llm", help="Runtime LLM selector in provider/model form, for example openai/gpt-5.5.")
    generate.add_argument("--provider", help="Runtime LLM provider override, for example openai or runpod.")
    generate.add_argument("--model", help="Runtime LLM model override.")
    generate.add_argument("--timeout", default=DEFAULT_GENERATE_TIMEOUT_SECONDS, type=int, help="HTTP timeout in seconds.")
    generate.add_argument("--output", help="Write response JSON to a file.")
    generate.set_defaults(func=cmd_generate)

    seed = subparsers.add_parser("seed", help="Initialize and seed the component database.")
    seed.set_defaults(func=cmd_seed)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
