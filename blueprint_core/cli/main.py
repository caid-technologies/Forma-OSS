from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
import sys
from typing import Any

from blueprint_core import __version__
from blueprint_core.selectors import split_llm_selector


def _provider_and_model(args: argparse.Namespace) -> tuple[str | None, str | None]:
    selected_provider, selected_model = split_llm_selector(args.llm)
    return args.provider or selected_provider, args.model or selected_model


def _read_json(path_value: str) -> Any:
    if path_value == "-":
        return json.load(sys.stdin)
    with Path(path_value).open(encoding="utf-8") as file:
        return json.load(file)


def _hardware_ir_payload(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("project_ir", "hardware_ir"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    response = value.get("response")
    if isinstance(response, dict) and isinstance(response.get("project_ir"), dict):
        return response["project_ir"]
    return value


def _write_json(value: Any, output: str | None) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output in (None, "-"):
        sys.stdout.write(payload)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _image_payload(path_value: str | None) -> tuple[bytes | None, str | None]:
    if not path_value:
        return None, None
    path = Path(path_value)
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return path.read_bytes(), mime_type


def cmd_workflows(args: argparse.Namespace) -> int:
    from blueprint_core.generation import list_workflows

    workflows = list_workflows()
    if args.json:
        _write_json(workflows, None)
    else:
        for workflow in workflows:
            print(f"{workflow['id']}: {workflow['label']} — {workflow['description']}")
    return 0


def cmd_namespaces(args: argparse.Namespace) -> int:
    from blueprint_core.generation import list_project_namespaces

    namespaces = [descriptor.__dict__ for descriptor in list_project_namespaces()]
    if args.json:
        _write_json(namespaces, None)
    else:
        for namespace in namespaces:
            print(f"{namespace['name']}: {namespace['label']} — {namespace['description']}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    from blueprint_core.generation import generate_project_with_workflow

    provider, model = _provider_and_model(args)
    if args.simulation:
        provider, model = "simulation", None
    image_bytes, image_mime_type = _image_payload(args.image_file)
    project = generate_project_with_workflow(
        args.workflow,
        args.prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        provider_name=provider,
        model_name=model,
        external_source_provider=args.external_source_provider,
    )
    _write_json(project, args.output)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from blueprint_core.validation import build_validation_summary, validate_circuit
    from blueprint_core.workspaces.projects.models import HardwareIR

    project = HardwareIR.model_validate(_hardware_ir_payload(_read_json(args.project)))
    summary = build_validation_summary(validate_circuit(project.components, project.nets))
    result = {
        "is_valid": not summary.critical,
        "validation": summary.model_dump(mode="json"),
    }
    _write_json(result, args.output)
    return 0 if result["is_valid"] else 1


def cmd_iterate(args: argparse.Namespace) -> int:
    from blueprint_core.workspaces.projects.iteration import iterate_project
    from blueprint_core.workspaces.projects.models import HardwareIR

    provider, model = _provider_and_model(args)
    current_project = HardwareIR.model_validate(_hardware_ir_payload(_read_json(args.project)))
    revised_project = iterate_project(
        current_project,
        args.instruction,
        original_prompt=args.original_prompt,
        project_id=args.project_id,
        target_namespace=args.namespace,
        provider_name=provider,
        model_name=model,
        use_simulation=args.simulation,
    )
    _write_json(revised_project, args.output)
    return 0


def _add_runtime_selector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llm", help="LLM selector in provider/model form, for example openai/gpt-5.5.")
    parser.add_argument("--provider", help="LLM provider override.")
    parser.add_argument("--model", help="LLM model override.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blueprint-core",
        description="Run Blueprint Core operations directly, without a backend server.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    workflows = subparsers.add_parser("workflows", help="List available generation workflows.")
    workflows.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    workflows.set_defaults(func=cmd_workflows)

    namespaces = subparsers.add_parser("namespaces", help="List project object namespaces.")
    namespaces.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    namespaces.set_defaults(func=cmd_namespaces)

    generate = subparsers.add_parser("generate", help="Generate a HardwareIR directly through Blueprint Core.")
    generate.add_argument("prompt", help="Hardware idea to generate.")
    generate.add_argument("--workflow", default="default", choices=("default", "web_research"))
    generate.add_argument("--external-source-provider", choices=("firecrawl",))
    generate.add_argument("--image-file", help="Optional reference image.")
    generate.add_argument("--simulation", action="store_true", help="Use the deterministic built-in generator.")
    generate.add_argument("--output", help="Write HardwareIR JSON to this path; defaults to stdout.")
    _add_runtime_selector_arguments(generate)
    generate.set_defaults(func=cmd_generate)

    validate = subparsers.add_parser("validate", help="Validate a HardwareIR JSON document.")
    validate.add_argument("project", help="HardwareIR JSON path, or - for stdin.")
    validate.add_argument("--output", help="Write validation JSON to this path; defaults to stdout.")
    validate.set_defaults(func=cmd_validate)

    iterate = subparsers.add_parser("iterate", help="Revise a HardwareIR directly through Blueprint Core.")
    iterate.add_argument("project", help="HardwareIR JSON path, or - for stdin.")
    iterate.add_argument("instruction", help="Natural-language revision instruction.")
    iterate.add_argument("--namespace", help="Target namespace, for example product.mech.")
    iterate.add_argument("--original-prompt")
    iterate.add_argument("--project-id")
    iterate.add_argument("--simulation", action="store_true", help="Apply a metadata-only simulated iteration.")
    iterate.add_argument("--output", help="Write revised HardwareIR JSON to this path; defaults to stdout.")
    _add_runtime_selector_arguments(iterate)
    iterate.set_defaults(func=cmd_iterate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
