from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.agents.firecrawl_mcp import FirecrawlMCPResearchClient, FirecrawlResearchResult
from backend.agents.orchestrator import (
    HardwarePipelineOrchestrator,
    build_mechanical_render_data,
    canonical_project_uuid,
    estimate_current_draw,
    extract_buses,
    extract_power_rails,
)
from backend.database import save_generated_project
from backend.llm_providers import LLMProviderConfigError, build_llm_provider
from backend.models import (
    AssemblyStep,
    ComponentInstance,
    ConnectionNet,
    FunctionalRequirements,
    HardwareIR,
    MechanicalNotes,
    PinMappingEntry,
    ProjectOverview,
    ValidationIssue,
)
from backend.runtime_config import (
    ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
    AlphaGenerationUnavailableError,
    deployment_mode_enabled,
)
from backend.validation import (
    build_validation_summary,
    check_safety_violations,
    validate_circuit,
)


logger = logging.getLogger(__name__)


class WebProjectPlan(BaseModel):
    overview: ProjectOverview
    requirements: FunctionalRequirements
    architecture_notes: List[str] = Field(default_factory=list)
    recommended_component_roles: List[str] = Field(default_factory=list)
    research_keywords: List[str] = Field(default_factory=list)


class WebComponentSelection(BaseModel):
    components: List[ComponentInstance]
    sourcing_notes: List[str] = Field(default_factory=list)
    rejected_options: List[str] = Field(default_factory=list)


class WiringWrapper(BaseModel):
    nets: List[ConnectionNet]
    pin_mappings: List[PinMappingEntry]


class AssemblyWrapper(BaseModel):
    steps: List[AssemblyStep]


class CompletenessAudit(BaseModel):
    completeness_score: float = Field(0.0, ge=0.0, le=1.0)
    missing_items: List[str] = Field(default_factory=list)
    possible_risks: List[str] = Field(default_factory=list)
    recommended_next_checks: List[str] = Field(default_factory=list)
    summary: str = ""


class WebResearchHardwarePipeline:
    """Internet-researched hardware workflow that keeps the same HardwareIR output contract."""

    workflow_id = "web_research"

    def __init__(self):
        self.llm_provider = build_llm_provider()
        self.use_simulation = not self.llm_provider.is_configured
        self.model_name = self.llm_provider.model_name
        self.research_client = FirecrawlMCPResearchClient()

    def get_debug_config(self) -> Dict[str, Any]:
        validation = self.llm_provider.validate_configured_model(raise_on_strict=False)
        return {
            **validation.as_debug_dict(),
            "workflow": self.workflow_id,
            "firecrawl_mcp": {
                "enabled": self.research_client.config.enabled,
                "command": self.research_client.config.command,
                "search_limit": self.research_client.config.search_limit,
                "reason": self.research_client.config.reason,
            },
        }

    def _call_llm_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        if self.use_simulation:
            raise RuntimeError("Simulation mode is active; web research workflow needs a live structured LLM provider.")

        result = self.llm_provider.generate_structured(prompt, schema_class, image_bytes, image_mime_type)
        self.model_name = self.llm_provider.model_name
        return result

    def generate_project(
        self,
        user_prompt: str,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> HardwareIR:
        safety_error = check_safety_violations(user_prompt)
        if safety_error:
            return HardwarePipelineOrchestrator().generate_project(
                user_prompt,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
            )

        if self.use_simulation:
            if deployment_mode_enabled():
                raise AlphaGenerationUnavailableError(ALPHA_GENERATION_UNAVAILABLE_MESSAGE)
            ir = HardwarePipelineOrchestrator(use_simulation=True).generate_project(
                user_prompt,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
            )
            ir.assembly_metadata = {
                **(ir.assembly_metadata or {}),
                "workflow": self.workflow_id,
                "workflow_fallback": "simulation",
                "firecrawl_research": self.research_client.config.reason,
            }
            return ir

        try:
            model_validation = self.llm_provider.validate_configured_model()
        except LLMProviderConfigError as exc:
            if deployment_mode_enabled():
                raise AlphaGenerationUnavailableError(ALPHA_GENERATION_UNAVAILABLE_MESSAGE) from exc
            raise

        research = self._research(user_prompt)
        research_context = research.as_prompt_context()

        plan = self._plan_project(user_prompt, research_context, image_bytes, image_mime_type)
        selection = self._select_components(user_prompt, plan, research_context, image_bytes, image_mime_type)
        components = selection.components
        components_json = json.dumps([component.model_dump() for component in components], indent=2)

        wiring = self._wire_project(user_prompt, plan, components_json, image_bytes, image_mime_type)
        nets = wiring.nets
        pin_mappings = wiring.pin_mappings

        validation_issues = validate_circuit(components, nets)
        is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in validation_issues)
        if not is_valid:
            corrected = self._repair_wiring(plan, components_json, nets, validation_issues, image_bytes, image_mime_type)
            nets = corrected.nets
            pin_mappings = corrected.pin_mappings
            validation_issues = validate_circuit(components, nets)
            is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in validation_issues)

        total_cost = sum(component.unit_price * component.quantity for component in components)
        plan.overview.estimated_cost = round(total_cost, 2)

        mechanical = self._generate_mechanical(plan, components_json, research_context, image_bytes, image_mime_type)
        assembly = self._generate_assembly(plan, components_json, nets, mechanical, image_bytes, image_mime_type)

        constraints = plan.requirements.physical_constraints + [f"Operating Voltage: {plan.requirements.operating_voltage}V"]
        fab_notes = mechanical.fabrication_details if mechanical else []
        power_rails = extract_power_rails(components, nets)
        buses = extract_buses(nets)
        current_draw = estimate_current_draw(components)

        audit = self._audit_output(plan, components, nets, mechanical, assembly, validation_issues)
        all_issues = [*validation_issues, *self._audit_to_validation_issues(audit)]

        project_ir = HardwareIR(
            hardware_ir_version="0.1",
            overview=plan.overview,
            requirements=plan.requirements,
            components=components,
            nets=nets,
            buses=buses,
            pin_mappings=pin_mappings,
            assembly=assembly,
            mechanical=mechanical,
            constraints=constraints,
            power_rails=power_rails,
            estimated_current_draw_ma=current_draw,
            fabrication_notes=fab_notes,
            assembly_metadata={
                "generated_at": datetime.utcnow().isoformat(),
                "revision": 1,
                "model_name": self.model_name,
                "fallback_mode": model_validation.fallback_active,
                "requested_model": model_validation.requested_model,
                "actual_model": model_validation.actual_model,
                "llm_provider": model_validation.provider,
                "workflow": self.workflow_id,
                "pipeline": "Firecrawl MCP web research + sourced hardware agents",
                "component_source_policy": "web-sourced components; not constrained to seed_db.py",
                "architecture_notes": plan.architecture_notes,
                "recommended_component_roles": plan.recommended_component_roles,
                "sourcing_notes": selection.sourcing_notes,
                "firecrawl_research": research.metadata(),
                "completeness_audit": audit.model_dump(),
                "image_features": plan.architecture_notes + plan.recommended_component_roles,
            },
            project_version_history=[
                {
                    "version": "0.1",
                    "description": "Initial design compilation via Firecrawl MCP web research workflow",
                }
            ],
            validation=build_validation_summary(all_issues),
            is_valid=not any(issue.severity.upper() == "CRITICAL" for issue in all_issues),
        )

        project_ir = build_mechanical_render_data(project_ir)
        self._save_project_to_db(user_prompt, project_ir)
        return project_ir

    def _research(self, user_prompt: str) -> FirecrawlResearchResult:
        queries = [
            f"{user_prompt} open source hardware schematic BOM",
            f"{user_prompt} maker project components wiring datasheet",
            f"{user_prompt} Arduino ESP32 module component reference design",
        ]
        return self.research_client.research(queries)

    def _plan_project(
        self,
        user_prompt: str,
        research_context: str,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> WebProjectPlan:
        prompt = f"""
        You are a Web Research Hardware Architect Agent.
        Turn the user request into a buildable low-voltage maker electronics architecture.

        User request:
        {user_prompt}

        Firecrawl MCP research context:
        {research_context}

        Return WebProjectPlan. Prefer concrete component roles that are supported by the research context.
        Keep the design in safe low-voltage DC maker-electronics scope.
        """
        return self._call_llm_structured(prompt, WebProjectPlan, image_bytes, image_mime_type)

    def _select_components(
        self,
        user_prompt: str,
        plan: WebProjectPlan,
        research_context: str,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> WebComponentSelection:
        prompt = f"""
        You are a Web Component Sourcing Agent.
        Select real, buildable components for this project using Firecrawl MCP research and common datasheet-backed maker hardware.

        User request:
        {user_prompt}

        Project plan:
        {plan.model_dump_json()}

        Firecrawl MCP research context:
        {research_context}

        Important rules:
        - Do not constrain yourself to the local seed database.
        - Use real components or modules that a maker could plausibly buy.
        - Prefer source URLs from the research context. Leave sourcing_url null if the URL is unknown; do not invent URLs.
        - Include one microcontroller or SBC unless the project clearly does not need compute.
        - Include a realistic low-voltage power source/regulator path.
        - Include complete relevant pins for each selected component: power, ground, interfaces, control, analog, and outputs.
        - Give each project instance a unique ref_des such as U1, SEN1, DIS1, PWR1, REG1, ACT1, SW1, R1.
        - For complex boards, include the pins needed for this build rather than every package pin.

        Return WebComponentSelection.
        """
        return self._call_llm_structured(prompt, WebComponentSelection, image_bytes, image_mime_type)

    def _wire_project(
        self,
        user_prompt: str,
        plan: WebProjectPlan,
        components_json: str,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> WiringWrapper:
        prompt = f"""
        You are a Wiring/Netlist Agent for sourced web components.
        Create safe low-voltage nets and MCU pin mappings.

        User request:
        {user_prompt}

        Requirements:
        {plan.requirements.model_dump_json()}

        Components:
        {components_json}

        Rules:
        - Every power pin must connect to a compatible power rail.
        - Every ground pin must connect to a ground net.
        - Do not short power to ground or mix incompatible logic voltages.
        - Use level shifting or voltage-compatible parts when needed.
        - A physical pin must appear in only one net.
        - Passive components bridge nets with one passive pin per net.
        - Keep pin_mappings focused on controller pins and human-readable functions.

        Return WiringWrapper.
        """
        return self._call_llm_structured(prompt, WiringWrapper, image_bytes, image_mime_type)

    def _repair_wiring(
        self,
        plan: WebProjectPlan,
        components_json: str,
        nets: List[ConnectionNet],
        issues: List[ValidationIssue],
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> WiringWrapper:
        prompt = f"""
        You are a Wiring/Netlist Auto-Correction Agent.
        Correct the netlist using the validation report.

        Requirements:
        {plan.requirements.model_dump_json()}

        Components:
        {components_json}

        Previous nets:
        {json.dumps([net.model_dump() for net in nets], indent=2)}

        Validation issues:
        {json.dumps([issue.model_dump() for issue in issues], indent=2)}

        Return corrected WiringWrapper.
        """
        return self._call_llm_structured(prompt, WiringWrapper, image_bytes, image_mime_type)

    def _generate_mechanical(
        self,
        plan: WebProjectPlan,
        components_json: str,
        research_context: str,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> MechanicalNotes:
        prompt = f"""
        You are a Mechanical/Fabrication and CAD Sourcing Agent.
        Produce enclosure, mounting, fabrication, CAD source, and 3D render placement details.

        Project plan:
        {plan.model_dump_json()}

        Components:
        {components_json}

        Research context:
        {research_context}

        Use CAD/enclosure URLs only when present in research or well-known source data. If no source exists, keep cad_sources empty.
        Return MechanicalNotes.
        """
        return self._call_llm_structured(prompt, MechanicalNotes, image_bytes, image_mime_type)

    def _generate_assembly(
        self,
        plan: WebProjectPlan,
        components_json: str,
        nets: List[ConnectionNet],
        mechanical: MechanicalNotes,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> List[AssemblyStep]:
        prompt = f"""
        You are an Assembly Instruction Agent.
        Produce concrete step-by-step build instructions.

        Project:
        {plan.overview.model_dump_json()}

        Components:
        {components_json}

        Nets:
        {json.dumps([net.model_dump() for net in nets], indent=2)}

        Mechanical guide:
        {mechanical.model_dump_json()}

        Mention safety flags for batteries, motors, relays, soldering, heat, moving parts, and polarity.
        Return AssemblyWrapper.
        """
        wrapper: AssemblyWrapper = self._call_llm_structured(prompt, AssemblyWrapper, image_bytes, image_mime_type)
        return wrapper.steps

    def _audit_output(
        self,
        plan: WebProjectPlan,
        components: List[ComponentInstance],
        nets: List[ConnectionNet],
        mechanical: MechanicalNotes,
        assembly: List[AssemblyStep],
        validation_issues: List[ValidationIssue],
    ) -> CompletenessAudit:
        deterministic_missing = self._deterministic_missing_checks(components, nets, mechanical, assembly)
        prompt = f"""
        You are a Hardware Output Completeness Auditor Agent.
        Check whether this generated Hardware IR is likely missing anything important.
        Do not rewrite the design. Only audit it.

        Requirements:
        {plan.requirements.model_dump_json()}

        Components:
        {json.dumps([component.model_dump() for component in components], indent=2)}

        Nets:
        {json.dumps([net.model_dump() for net in nets], indent=2)}

        Mechanical:
        {mechanical.model_dump_json()}

        Assembly steps:
        {json.dumps([step.model_dump() for step in assembly], indent=2)}

        Validation issues:
        {json.dumps([issue.model_dump() for issue in validation_issues], indent=2)}

        Deterministic missing checks already found:
        {json.dumps(deterministic_missing, indent=2)}

        Look for missing power conversion, protection parts, required sensors, connectors, level shifting,
        pullups, current limiting, mounting details, firmware/programming notes, and unclear sourcing.
        Return CompletenessAudit.
        """
        try:
            audit: CompletenessAudit = self._call_llm_structured(prompt, CompletenessAudit)
        except Exception as exc:
            logger.warning("Completeness audit LLM call failed: %s", exc)
            audit = CompletenessAudit(
                completeness_score=0.0 if deterministic_missing else 0.65,
                missing_items=deterministic_missing,
                possible_risks=[],
                recommended_next_checks=[],
                summary="Deterministic completeness checks ran; LLM audit was unavailable.",
            )

        audit.missing_items = [*deterministic_missing, *audit.missing_items]
        return audit

    def _deterministic_missing_checks(
        self,
        components: List[ComponentInstance],
        nets: List[ConnectionNet],
        mechanical: MechanicalNotes,
        assembly: List[AssemblyStep],
    ) -> List[str]:
        missing: List[str] = []
        categories = {component.category.lower() for component in components}
        if not any("microcontroller" in category or "sbc" in category for category in categories):
            missing.append("No controller-class component is present.")
        if not any("power" in category or "battery" in category or "regulator" in category for category in categories):
            missing.append("No explicit power source or regulator component is present.")
        if not nets:
            missing.append("No electrical nets were generated.")
        if not any(net.net_type.lower() == "ground" for net in nets):
            missing.append("No ground net was generated.")
        if not any(net.net_type.lower() == "power" for net in nets):
            missing.append("No power rail net was generated.")
        if any(not component.pins for component in components):
            missing.append("One or more components have no pin definitions.")
        if not assembly:
            missing.append("No assembly steps were generated.")
        if not mechanical.fabrication_details:
            missing.append("Mechanical fabrication details are sparse.")
        return missing

    def _audit_to_validation_issues(self, audit: CompletenessAudit) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for item in audit.missing_items:
            issues.append(
                ValidationIssue(
                    severity="WARNING",
                    category="Completeness Audit",
                    description=item,
                    troubleshooting="Review the generated design and add or source this item before building.",
                )
            )
        for risk in audit.possible_risks:
            issues.append(
                ValidationIssue(
                    severity="INFO",
                    category="Completeness Audit",
                    description=risk,
                    troubleshooting="Verify this detail against datasheets and real hardware constraints.",
                )
            )
        return issues

    def _save_project_to_db(self, prompt: str, ir: HardwareIR) -> str:
        project_id = canonical_project_uuid((ir.assembly_metadata or {}).get("project_id"))
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "project_id": project_id,
        }
        try:
            save_generated_project(
                project_id=project_id,
                title=ir.overview.title if ir.overview else "Untitled Blueprint Project",
                prompt=prompt,
                hardware_ir=ir.model_dump(),
                created_at=datetime.utcnow().isoformat(),
            )
            logger.info("Web research workflow project saved to database with ID: %s", project_id)
            return project_id
        except Exception as exc:
            logger.error("Failed to save web research workflow project: %s", exc)
            return ""
