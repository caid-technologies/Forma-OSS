#!/usr/bin/env python3
"""Fabricator CLI using Forma for LLM and MCP integration.

Generate a local plan:
    python -m fabricator plan --material "cellulose acetate offcuts"

Generate through the configured Forma LLM provider:
    python -m fabricator plan --live --provider runpod --material "cellulose acetate offcuts"

Inspect Forma MCP tools:
    python -m fabricator mcp-tools
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.lattice import (  # noqa: E402
    LatticeAgentCard,
    LatticeCapability,
    LatticeRunRecord,
    LatticeSchemaContract,
)
from blueprint_core.llm import build_llm_provider  # noqa: E402


DEFAULT_MATERIAL = "cellulose fiber and mycelium biomass"
DEFAULT_AMOUNT = "25 kg"
DEFAULT_GOAL = "find feasible, non-hazardous product families and the workflows needed to evaluate them"
DEFAULT_EQUIPMENT = (
    "inventory database",
    "balance",
    "humidity chamber",
    "compression press",
    "3D printer",
    "optical microscope",
)
DEFAULT_MCP_URL = "in-process"
FABRICATOR_AGENT_ID = "fabricator"
FABRICATOR_PLANNING_CONTRACT_ID = "fabricator.plan.v0"


class PrimitiveInventory(BaseModel):
    material: str = Field(description="Primitive or surplus input material available to the user.")
    amount: str = Field(description="Approximate amount, batch size, or inventory level.")
    form: str = Field(description="Physical, biological, or chemical form of the primitive.")
    known_constraints: list[str] = Field(default_factory=list)


class DeviceInterfaceNeed(BaseModel):
    device_or_system: str
    role_in_workflow: str
    interface_type: Literal["blueprint_mcp", "manual", "external_api", "file_import", "unknown"]
    mcp_tool_hint: str | None = None
    human_review_required: bool = True


class CandidateWorkflow(BaseModel):
    product_family: str
    candidate_product: str
    why_it_fits_the_primitives: str
    missing_primitives_or_data: list[str] = Field(default_factory=list)
    high_level_steps: list[str] = Field(default_factory=list)
    device_interfaces: list[DeviceInterfaceNeed] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    safety_or_compliance_notes: list[str] = Field(default_factory=list)
    next_blueprint_mcp_action: str


class FabricatorQuestion(BaseModel):
    inventory: PrimitiveInventory
    goal: str
    available_equipment: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class FabricatorPlan(BaseModel):
    question: FabricatorQuestion
    interpretation: str
    candidate_workflows: list[CandidateWorkflow]
    recommended_clarifying_questions: list[str] = Field(default_factory=list)
    blueprint_mcp_handoff: list[dict[str, Any]] = Field(default_factory=list)


class FabricatorRun(BaseModel):
    mode: Literal["local", "live", "live_fallback"]
    fabricator_plan: FabricatorPlan
    lattice_run: LatticeRunRecord | None = None
    blueprint_llm: dict[str, Any] | None = None
    blueprint_mcp_tools: Any | None = None
    warnings: list[str] = Field(default_factory=list)


def csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_question(args: argparse.Namespace) -> FabricatorQuestion:
    return FabricatorQuestion(
        inventory=PrimitiveInventory(
            material=args.material,
            amount=args.amount,
            form=args.form,
            known_constraints=csv_values(args.constraints),
        ),
        goal=args.goal,
        available_equipment=csv_values(args.available_equipment),
        constraints=csv_values(args.constraints),
    )


def build_prompt(question: FabricatorQuestion) -> str:
    return (
        "You are Fabricator, a Forma-powered fabrication planning assistant. "
        "Given available primitive materials, propose high-level product families, "
        "candidate workflows, and device or software systems that Forma MCP may need to interface with. "
        "Keep the plan conceptual and review-oriented. Do not provide hazardous, regulated, or executable wet-lab protocols.\n\n"
        "User question:\n"
        f"We have excess {question.inventory.amount} of {question.inventory.material} "
        f"in this form: {question.inventory.form}. What can we use it for, and what devices or systems "
        "do we need to interface with in these workflows?\n\n"
        "Available equipment and systems:\n"
        f"{json.dumps(question.available_equipment, indent=2)}\n\n"
        "Constraints:\n"
        f"{json.dumps(question.constraints, indent=2)}\n\n"
        f"Goal: {question.goal}\n"
    )


def mcp_handoff_requests() -> list[dict[str, Any]]:
    return [
        {
            "jsonrpc": "2.0",
            "id": "fabricator-initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "fabricator-sample", "version": "0.1.0"},
                "capabilities": {},
            },
        },
        {"jsonrpc": "2.0", "id": "fabricator-tools", "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": "fabricator-debug-config",
            "method": "tools/call",
            "params": {"name": "blueprint.debug_config", "arguments": {}},
        },
    ]


def local_heuristic_plan(question: FabricatorQuestion) -> FabricatorPlan:
    material_text = question.inventory.material.lower()
    form_text = question.inventory.form.lower()
    primitive_text = f"{material_text} {form_text}"
    device_interfaces = [
        DeviceInterfaceNeed(
            device_or_system="inventory database",
            role_in_workflow="confirm batch amount, age, storage conditions, and traceability",
            interface_type="blueprint_mcp",
            mcp_tool_hint="inventory lookup",
        ),
    ]
    if any(term in material_text for term in ("salt", "oxide", "metal", "ceramic", "powder")):
        product_family = "functional material formulations"
        candidate_product = "coatings, fillers, test coupons, or process additives"
        fit = (
            "The available primitive appears suitable for formulation search, coupon fabrication, or material "
            "property exploration after compatibility checks."
        )
        validation_checks = [
            "purity and particle-size review",
            "compatibility screening",
            "thermal or mechanical property check",
            "safety data sheet review",
        ]
    elif any(term in primitive_text for term in ("fiber", "cellulose", "biomass", "mycelium", "polymer", "resin")):
        product_family = "bio-composite materials"
        candidate_product = "pressed packaging inserts, acoustic panels, or non-structural device enclosures"
        fit = (
            "The available primitive can be screened as a reinforcement, filler, binder, or printable feedstock "
            "for low-risk material applications."
        )
        validation_checks = [
            "moisture and density measurement",
            "mechanical screening",
            "surface inspection",
            "contamination and storage-condition review",
        ]
    else:
        product_family = "screening candidates"
        candidate_product = "prototype samples, fixtures, consumables, or formulation inputs"
        fit = (
            "The primitive needs characterization before choosing a route, so the first useful output is a ranked "
            "screening plan tied to available devices and validation checks."
        )
        validation_checks = [
            "identity and quality check",
            "compatibility review",
            "small-sample feasibility screen",
            "human safety review",
        ]

    equipment_text = " ".join(question.available_equipment).lower()
    if "press" in equipment_text:
        device_interfaces.append(
            DeviceInterfaceNeed(
                device_or_system="compression press",
                role_in_workflow="check whether available tooling can produce the target sample geometry",
                interface_type="blueprint_mcp",
                mcp_tool_hint="device capability discovery",
            )
        )
    if "printer" in equipment_text or "cad" in equipment_text or "cam" in equipment_text:
        device_interfaces.append(
            DeviceInterfaceNeed(
                device_or_system="CAD/CAM or 3D printer",
                role_in_workflow="translate candidate product geometry into a reviewable prototype workflow",
                interface_type="blueprint_mcp",
                mcp_tool_hint="fabrication job planning",
            )
        )
    if "microscope" in equipment_text or "camera" in equipment_text:
        device_interfaces.append(
            DeviceInterfaceNeed(
                device_or_system="inspection device",
                role_in_workflow="capture surface, morphology, or defect evidence during validation",
                interface_type="manual",
            )
        )

    return FabricatorPlan(
        question=question,
        interpretation=(
            "Treat the surplus primitive as an inventory and capability-discovery problem: first identify safe "
            "product families, then ask Forma MCP which tools, devices, and external systems can support each route."
        ),
        candidate_workflows=[
            CandidateWorkflow(
                product_family=product_family,
                candidate_product=candidate_product,
                why_it_fits_the_primitives=fit,
                missing_primitives_or_data=[
                    "moisture content",
                    "particle size distribution",
                    "binder compatibility",
                    "mechanical strength target",
                ],
                high_level_steps=[
                    "characterize the surplus material",
                    "compare candidate product families",
                    "select a low-risk prototype format",
                    "run mechanical and environmental validation",
                ],
                device_interfaces=device_interfaces,
                validation_checks=validation_checks,
                safety_or_compliance_notes=[
                    "keep outputs non-medical and non-food-contact until reviewed",
                    "require human approval before any physical fabrication job is started",
                ],
                next_blueprint_mcp_action="List available inventory, device, validation, and job-creation tools.",
            )
        ],
        recommended_clarifying_questions=[
            "What product category matters most: packaging, filtration, insulation, lab consumables, or device parts?",
            "Do these primitives have contamination, sterility, allergen, or regulatory constraints?",
            "Which devices are actually connected to Forma MCP today?",
        ],
        blueprint_mcp_handoff=mcp_handoff_requests(),
    )


def generate_live_plan(args: argparse.Namespace, question: FabricatorQuestion) -> tuple[FabricatorPlan, dict[str, Any], list[str]]:
    provider = build_llm_provider(provider_name=args.provider, model_name=args.model)
    validation = provider.validate_configured_model(raise_on_strict=False)
    debug_config = validation.as_debug_dict()
    warnings: list[str] = []
    if not validation.live_generation_enabled:
        warnings.append(f"Forma live LLM is unavailable: {validation.validation_error}")
        return local_heuristic_plan(question), debug_config, warnings

    try:
        plan = provider.generate_structured(build_prompt(question), FabricatorPlan)
    except Exception as exc:
        warnings.append(f"Forma live LLM failed; using local heuristic plan: {exc}")
        return local_heuristic_plan(question), debug_config, warnings

    if not plan.blueprint_mcp_handoff:
        plan.blueprint_mcp_handoff = mcp_handoff_requests()
    return plan, debug_config, warnings


def fabricator_lattice_card() -> LatticeAgentCard:
    planning_contract = LatticeSchemaContract.from_models(
        id=FABRICATOR_PLANNING_CONTRACT_ID,
        name="Fabricator Planning Contract",
        purpose=(
            "Convert primitive materials, constraints, and available equipment into conceptual fabrication "
            "options that another agent or human can inspect before any physical execution."
        ),
        input_model=FabricatorQuestion,
        output_model=FabricatorPlan,
        induction_prompt=(
            "Given domain examples, refine the planning schema for fabrication primitives, candidate workflows, "
            "device-interface needs, validation checks, and review gates."
        ),
        extraction_prompt=(
            "Extract the user's primitives, goal, constraints, and equipment into FabricatorQuestion, then produce "
            "FabricatorPlan without executable wet-lab or hazardous protocols."
        ),
        metadata={
            "declared_input_model": "FabricatorQuestion",
            "declared_output_model": "FabricatorPlan",
        },
    )

    return LatticeAgentCard(
        agent_id=FABRICATOR_AGENT_ID,
        namespace="product.fabricator",
        name="Fabricator",
        version="0.1.0",
        domain="fabrication planning from primitive material inputs",
        summary=(
            "A domain agent for turning surplus materials, constraints, and equipment access into conceptual "
            "fabrication workflows, missing-data questions, and Forma MCP handoff actions."
        ),
        capabilities=[
            LatticeCapability(
                id="fabricator.plan",
                label="Primitive-to-product planning",
                description=(
                    "Rank safe candidate product families and high-level workflows from material primitives, "
                    "available equipment, and user constraints."
                ),
                inputs=["material", "amount", "form", "goal", "constraints", "available_equipment"],
                outputs=[
                    "candidate_workflows",
                    "device_interfaces",
                    "validation_checks",
                    "clarifying_questions",
                    "blueprint_mcp_handoff",
                ],
                actions=["fabricator.plan", "fabricator.prompt", "fabricator.mcp-tools"],
            ),
            LatticeCapability(
                id="fabricator.schema",
                label="Fabrication schema contract",
                description=(
                    "Expose the declared input and output JSON Schemas so other agents can call Fabricator "
                    "without prompt-shape guessing."
                ),
                inputs=["agent_discovery_request"],
                outputs=["lattice_agent_card", "lattice_schema_contract"],
                actions=["fabricator.card", "blueprint.lattice.get_agent_card"],
            ),
        ],
        contracts=[planning_contract],
        runtime_boundary=(
            "Fabricator owns fabrication-domain reasoning and schema shape; Forma owns model routing, MCP/tool "
            "execution, logging, validation, and provider configuration."
        ),
        tools_needed=[
            "inventory lookup",
            "device capability discovery",
            "literature or reference search",
            "simulation",
            "schema validation",
            "fabrication job planning",
            "status monitoring",
        ],
        handoff_actions=[
            "blueprint.debug_config",
            "blueprint.lattice.get_agent_card",
            "blueprint.lattice.list_agents",
            "tools/list",
            "inventory lookup",
            "device capability discovery",
            "simulation",
            "job creation",
        ],
        safety_limits=[
            "Conceptual and review-oriented planning only.",
            "No executable hazardous, regulated, or wet-lab protocols.",
            "No physical fabrication job should start without explicit human approval.",
        ],
        human_review_triggers=[
            "biological growth or organism handling",
            "chemical synthesis or regulated materials",
            "medical, food-contact, or human-contact products",
            "irreversible physical actions",
            "unknown contamination or traceability",
        ],
        tags=["domain-agent", "fabrication", "materials", "mcp", "schema-contract"],
        metadata={"runtime": "Forma", "layer": "Lattice"},
    )


def call_in_process_mcp(payload: dict[str, Any] | list[dict[str, Any]]) -> Any:
    try:
        from backend.a2a import handle_mcp_json_rpc
    except ModuleNotFoundError as exc:
        venv_python = ROOT_DIR / ".venv" / "bin" / "python"
        if venv_python.exists() and Path(sys.executable).absolute() != venv_python.absolute():
            return call_in_process_mcp_with_python(venv_python, payload)
        raise RuntimeError(
            "Forma backend dependencies are unavailable. Run backend dependency setup or pass --mcp-url "
            "to a running Forma server."
        ) from exc

    return asyncio.run(handle_mcp_json_rpc(payload))


def call_in_process_mcp_with_python(python_path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> Any:
    helper = """
import asyncio
import json
import sys
from pathlib import Path

root_dir = Path(sys.argv[1])
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.a2a import handle_mcp_json_rpc

payload = json.loads(sys.stdin.read())
result = asyncio.run(handle_mcp_json_rpc(payload))
print(json.dumps(result))
"""
    completed = subprocess.run(
        [str(python_path), "-c", helper, str(ROOT_DIR)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown subprocess error"
        raise RuntimeError(f"Forma in-process MCP failed under {python_path}: {message}")
    return json.loads(completed.stdout)


def post_mcp_json_rpc(mcp_url: str, payload: dict[str, Any] | list[dict[str, Any]]) -> Any:
    if mcp_url == "in-process":
        return call_in_process_mcp(payload)

    try:
        request = urllib.request.Request(
            mcp_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Could not reach Forma MCP server at {mcp_url}: {reason}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Invalid Forma MCP URL {mcp_url!r}: {exc}") from exc


def add_question_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--material", default=DEFAULT_MATERIAL)
    parser.add_argument("--amount", default=DEFAULT_AMOUNT)
    parser.add_argument("--form", default="as supplied surplus material")
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--constraints", default="non-hazardous, human review before execution")
    parser.add_argument("--available-equipment", default=", ".join(DEFAULT_EQUIPMENT))


def add_model_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default=None, help="Forma LLM provider override, such as runpod or openai.")
    parser.add_argument("--model", default=None, help="Forma LLM model override.")
    parser.add_argument("--live", action="store_true", help="Use Forma's configured LLM provider instead of the dry-run sample.")


def add_mcp_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mcp-url",
        default=DEFAULT_MCP_URL,
        help="Forma MCP endpoint URL, or 'in-process' to use Forma's handler directly.",
    )


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", help="Write JSON output to this file path.")
    parser.add_argument("--quiet", action="store_true", help="Do not print JSON to stdout when --output is set.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fabricator",
        description="Fabricator fabrication-planning CLI backed by Forma.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a fabrication plan from primitives and constraints.")
    add_question_arguments(plan_parser)
    add_model_arguments(plan_parser)
    add_mcp_arguments(plan_parser)
    add_output_arguments(plan_parser)
    plan_parser.add_argument(
        "--include-mcp-tools",
        "--list-mcp-tools",
        dest="include_mcp_tools",
        action="store_true",
        help="Include Forma MCP tool discovery in the plan output.",
    )
    plan_parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the prompt that would be sent to Forma's LLM layer.",
    )

    prompt_parser = subparsers.add_parser("prompt", help="Print the model prompt for a fabrication question.")
    add_question_arguments(prompt_parser)
    prompt_parser.add_argument("--output", help="Write the prompt to this file path.")
    prompt_parser.add_argument("--quiet", action="store_true", help="Do not print the prompt to stdout when --output is set.")

    tools_parser = subparsers.add_parser("mcp-tools", help="List tools exposed by Forma MCP.")
    add_mcp_arguments(tools_parser)
    add_output_arguments(tools_parser)

    card_parser = subparsers.add_parser("card", help="Print Fabricator's Lattice agent card.")
    add_output_arguments(card_parser)
    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return ["plan"]
    if argv[0] in {"-h", "--help", "plan", "prompt", "mcp-tools", "card"}:
        return argv
    return ["plan", *argv]


def write_text_output(text: str, output_path: str | None, *, quiet: bool = False) -> None:
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if not quiet or not output_path:
        print(text, end="" if text.endswith("\n") else "\n")


def write_json_output(payload: Any, output_path: str | None, *, quiet: bool = False) -> None:
    write_text_output(json.dumps(payload, indent=2) + "\n", output_path, quiet=quiet)


def build_run(args: argparse.Namespace, question: FabricatorQuestion) -> FabricatorRun:
    warnings: list[str] = []
    blueprint_llm: dict[str, Any] | None = None
    mode: Literal["local", "live", "live_fallback"] = "local"

    if args.live:
        plan, blueprint_llm, warnings = generate_live_plan(args, question)
        mode = "live_fallback" if warnings else "live"
    else:
        plan = local_heuristic_plan(question)

    lattice_run = LatticeRunRecord.completed(
        agent_card=fabricator_lattice_card(),
        action="fabricator.plan",
        contract_id=FABRICATOR_PLANNING_CONTRACT_ID,
        mode=mode,
        input_payload=question.model_dump(mode="json"),
        output_payload=plan.model_dump(mode="json"),
        warnings=warnings,
        handoff_actions=plan.blueprint_mcp_handoff,
        metadata={"output_ref": "fabricator_plan"},
    )

    run = FabricatorRun(
        mode=mode,
        fabricator_plan=plan,
        lattice_run=lattice_run,
        blueprint_llm=blueprint_llm,
        warnings=warnings,
    )

    if args.include_mcp_tools:
        run.blueprint_mcp_tools = post_mcp_json_rpc(
            args.mcp_url,
            {"jsonrpc": "2.0", "id": "fabricator-tools", "method": "tools/list", "params": {}},
        )

    return run


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(normalize_argv(argv if argv is not None else sys.argv[1:]))

    if args.command == "card":
        write_json_output(fabricator_lattice_card().model_dump(mode="json"), args.output, quiet=args.quiet)
        return 0

    if args.command == "mcp-tools":
        payload = post_mcp_json_rpc(
            args.mcp_url,
            {"jsonrpc": "2.0", "id": "fabricator-tools", "method": "tools/list", "params": {}},
        )
        write_json_output({"blueprint_mcp_tools": payload}, args.output, quiet=args.quiet)
        return 0

    question = build_question(args)

    if args.command == "prompt" or args.print_prompt:
        write_text_output(build_prompt(question), args.output, quiet=args.quiet)
        return 0

    run = build_run(args, question)
    write_json_output(run.model_dump(mode="json", exclude_none=True), args.output, quiet=args.quiet)
    return 0


FibricatorQuestion = FabricatorQuestion
FibricatorPlan = FabricatorPlan
FibricatorRun = FabricatorRun


if __name__ == "__main__":
    raise SystemExit(main())
