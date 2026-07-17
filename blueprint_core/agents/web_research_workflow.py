from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from blueprint_core.external_sources import ExternalSourceLibrary, build_external_source_provider
from blueprint_core.agents.orchestrator import (
    HardwarePipelineOrchestrator,
    build_mechanical_render_data,
    canonical_project_uuid,
    estimate_current_draw,
    extract_buses,
    extract_power_rails,
)
from blueprint_core.database import save_generated_project
from blueprint_core.job_source_usage import source_usage_for_workflow
from blueprint_core.llm import (
    LLMProviderConfigError,
    LLMRuntimeConfig,
    build_llm_provider,
    resolve_llm_runtime_config,
)
from blueprint_core.models import (
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
from blueprint_core.observability import serialize_for_langfuse, start_observation, update_observation
from blueprint_core.pipeline import agent_pipeline_step, emit_agent_note_event, emit_agent_pipeline_event
from blueprint_core.runtime import (
    AlphaGenerationUnavailableError,
    deployment_mode_enabled,
    generation_unavailable_message,
)
from blueprint_core.validation import (
    build_validation_summary,
    check_safety_violations,
    validate_circuit,
)


logger = logging.getLogger(__name__)

VISIBLE_WEB_AGENT_DECISION_NOTES = {
    "external_research": "I am gathering source material before committing to components or wiring.",
    "web_architect": "I am turning the source context into a sourced hardware architecture.",
    "web_component_sourcing": "I am weighing sourced components against requirements, availability, and pin compatibility.",
    "wiring_netlist": "I am about to connect the sourced components into safe power, ground, bus, and signal nets.",
    "validation_repair": "I am checking the sourced circuit for electrical issues before accepting it.",
    "mechanical_fabrication": "I am turning sourced parts and wiring into placement, enclosure, and fabrication decisions.",
    "assembly": "I am preparing build steps grounded in the selected parts and wiring.",
    "completeness_audit": "I am auditing the output for missing sourcing, protection, wiring, and assembly details.",
    "package_project": "I am packaging the sourced project artifacts and validation summary.",
}


def _visible_web_agent_decision_note(step_id: Optional[str], schema_name: str) -> str:
    if step_id and step_id in VISIBLE_WEB_AGENT_DECISION_NOTES:
        return VISIBLE_WEB_AGENT_DECISION_NOTES[step_id]
    return f"I am preparing a structured {schema_name} decision for this sourced workflow step."


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

    def __init__(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        runtime_config: Optional[LLMRuntimeConfig] = None,
        external_source_provider: Optional[str] = None,
    ):
        self.runtime_config = runtime_config or resolve_llm_runtime_config(
            provider_name=provider_name,
            model_name=model_name,
        )
        self.llm_provider = build_llm_provider(runtime_config=self.runtime_config)
        self.use_simulation = not self.llm_provider.is_configured
        self.model_name = self.llm_provider.model_name
        self.external_source_provider = external_source_provider
        self.research_client = build_external_source_provider(provider=external_source_provider)
        self._active_generation_metadata: Dict[str, Any] = {}

    def get_debug_config(self) -> Dict[str, Any]:
        validation = self.llm_provider.validate_configured_model(raise_on_strict=False)
        self.model_name = validation.actual_model or self.llm_provider.model_name
        return {
            **validation.as_debug_dict(),
            "runtime": self.runtime_config.as_debug_dict(),
            "workflow": self.workflow_id,
            "external_sources": self.research_client.get_debug_config(),
        }

    def _call_llm_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
        pipeline_step_id: Optional[str] = None,
    ) -> Any:
        if self.use_simulation:
            raise RuntimeError("Simulation mode is active; web research workflow needs a live structured LLM provider.")

        schema_name = getattr(schema_class, "__name__", "StructuredResponse")
        metadata = {
            "workflow": self.workflow_id,
            "llm_provider": self.llm_provider.provider_name,
            "runtime_provider": self.runtime_config.provider,
            "runtime_model": self.runtime_config.model,
            "requested_provider": self.runtime_config.requested_provider,
            "requested_model": self.runtime_config.requested_model,
            "response_schema": schema_name,
            "has_reference_image": bool(image_bytes),
            "image_mime_type": image_mime_type,
        }
        provider_event_details = {
            "provider": self.llm_provider.provider_name,
            "model": self.llm_provider.model_name,
            "runtime_provider": self.runtime_config.provider,
            "runtime_model": self.runtime_config.model,
            "schema": schema_name,
            "has_reference_image": bool(image_bytes),
        }
        with start_observation(
            name=f"blueprint.{self.workflow_id}.{schema_name}",
            as_type="generation",
            model=self.llm_provider.model_name,
            input={
                "prompt": prompt,
                "schema": schema_name,
                "has_reference_image": bool(image_bytes),
                "image_mime_type": image_mime_type,
            },
            metadata=metadata,
        ) as observation:
            try:
                if pipeline_step_id:
                    emit_agent_note_event(
                        self.workflow_id,
                        pipeline_step_id,
                        _visible_web_agent_decision_note(pipeline_step_id, schema_name),
                        details={**provider_event_details, "phase": "before_provider_request"},
                    )
                    emit_agent_pipeline_event(
                        self.workflow_id,
                        pipeline_step_id,
                        "provider_request_started",
                        details=provider_event_details,
                    )
                result = self.llm_provider.generate_structured(prompt, schema_class, image_bytes, image_mime_type)
                self.model_name = self.llm_provider.model_name
                update_observation(
                    observation,
                    output=serialize_for_langfuse(result),
                    metadata={**metadata, "actual_model": self.model_name},
                )
                if pipeline_step_id:
                    emit_agent_pipeline_event(
                        self.workflow_id,
                        pipeline_step_id,
                        "provider_response_received",
                        details={**provider_event_details, "actual_model": self.model_name},
                    )
                return result
            except Exception as exc:
                if pipeline_step_id:
                    emit_agent_pipeline_event(
                        self.workflow_id,
                        pipeline_step_id,
                        "provider_request_failed",
                        details={
                            **provider_event_details,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc)[:500],
                        },
                    )
                update_observation(
                    observation,
                    metadata={**metadata, "error_type": exc.__class__.__name__, "error": str(exc)[:1000]},
                )
                raise

    def generate_project(
        self,
        user_prompt: str,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
        generation_metadata: Optional[Dict[str, Any]] = None,
    ) -> HardwareIR:
        self._active_generation_metadata = {
            key: value
            for key, value in (generation_metadata or {}).items()
            if value is not None and value != ""
        }
        emit_agent_pipeline_event(self.workflow_id, "safety_guardrail", "started")
        safety_error = check_safety_violations(user_prompt)
        if safety_error:
            emit_agent_pipeline_event(self.workflow_id, "safety_guardrail", "failed", details={"reason": safety_error})
            logger.info("Web research workflow safety guardrail blocked request; delegating to safety response.")
            return HardwarePipelineOrchestrator(runtime_config=self.runtime_config).generate_project(
                user_prompt,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                generation_metadata=self._active_generation_metadata,
            )

        if self.use_simulation:
            if deployment_mode_enabled():
                raise AlphaGenerationUnavailableError(generation_unavailable_message(self.get_debug_config()))
            logger.info("Web research workflow is using simulation fallback because external generation is unavailable.")
            emit_agent_pipeline_event(self.workflow_id, "external_research", "skipped", details={"reason": self.research_client.config.reason})
            ir = HardwarePipelineOrchestrator(use_simulation=True, runtime_config=self.runtime_config).generate_project(
                user_prompt,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                generation_metadata=self._active_generation_metadata,
            )
            ir.assembly_metadata = {
                **(ir.assembly_metadata or {}),
                "workflow": self.workflow_id,
                "source_usage": source_usage_for_workflow(
                    self.workflow_id,
                    external_provider=self.research_client.provider_name,
                ),
                "workflow_fallback": "simulation",
                "external_research": {
                    "provider": self.research_client.provider_name,
                    "error": self.research_client.config.reason,
                },
            }
            return ir

        try:
            model_validation = self.llm_provider.validate_configured_model()
            self.model_name = model_validation.actual_model or self.llm_provider.model_name
        except LLMProviderConfigError as exc:
            if deployment_mode_enabled():
                raise AlphaGenerationUnavailableError(generation_unavailable_message(self.get_debug_config())) from exc
            raise

        emit_agent_pipeline_event(self.workflow_id, "safety_guardrail", "completed")
        logger.info("Invoking Context Clarifier Agent...")
        with agent_pipeline_step(self.workflow_id, "context_clarifier", details={
            "has_human_context": "HUMAN-IN-THE-LOOP CONTEXT:" in user_prompt,
        }):
            pass
        logger.info("Starting Web Research Pipeline Execution...")
        logger.info("Invoking External Source Research Agent...")
        research_queries = self._research_queries(user_prompt)
        with agent_pipeline_step(self.workflow_id, "external_research", details={
            "provider": self.research_client.provider_name,
            "query_count": len(research_queries),
            "timeout_seconds": self.research_client.config.timeout_seconds,
        }):
            research = self._research(research_queries)
            research_context = research.as_prompt_context()

        logger.info("Invoking Web Research Hardware Architect Agent...")
        with agent_pipeline_step(self.workflow_id, "web_architect"):
            plan = self._plan_project(user_prompt, research_context, image_bytes, image_mime_type)
        logger.info("Invoking Web Component Sourcing Agent...")
        with agent_pipeline_step(self.workflow_id, "web_component_sourcing"):
            selection = self._select_components(user_prompt, plan, research_context, image_bytes, image_mime_type)
            components = selection.components
            components_json = json.dumps([component.model_dump() for component in components], indent=2)

        logger.info("Invoking Wiring/Netlist Agent...")
        with agent_pipeline_step(self.workflow_id, "wiring_netlist"):
            wiring = self._wire_project(user_prompt, plan, components_json, image_bytes, image_mime_type)
            nets = wiring.nets
            pin_mappings = wiring.pin_mappings

        logger.info("Running circuit validation checks on web-researched netlist...")
        with agent_pipeline_step(self.workflow_id, "validation_repair"):
            validation_issues = validate_circuit(components, nets)
            is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in validation_issues)
            if not is_valid:
                logger.info("Invoking Validation + Auto-Correction Agent...")
                corrected = self._repair_wiring(plan, components_json, nets, validation_issues, image_bytes, image_mime_type)
                nets = corrected.nets
                pin_mappings = corrected.pin_mappings
                validation_issues = validate_circuit(components, nets)
                is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in validation_issues)

        total_cost = sum(component.unit_price * component.quantity for component in components)
        plan.overview.estimated_cost = round(total_cost, 2)

        logger.info("Invoking Mechanical/Fabrication Agent...")
        with agent_pipeline_step(self.workflow_id, "mechanical_fabrication"):
            mechanical = self._generate_mechanical(plan, components_json, research_context, image_bytes, image_mime_type)
        logger.info("Invoking Assembly Instruction Agent...")
        with agent_pipeline_step(self.workflow_id, "assembly"):
            assembly = self._generate_assembly(plan, components_json, nets, mechanical, image_bytes, image_mime_type)

        constraints = plan.requirements.physical_constraints + [f"Operating Voltage: {plan.requirements.operating_voltage}V"]
        fab_notes = mechanical.fabrication_details if mechanical else []
        power_rails = extract_power_rails(components, nets)
        buses = extract_buses(nets)
        current_draw = estimate_current_draw(components)

        logger.info("Invoking Hardware Output Completeness Auditor Agent...")
        with agent_pipeline_step(self.workflow_id, "completeness_audit"):
            audit = self._audit_output(plan, components, nets, mechanical, assembly, validation_issues)
            all_issues = [*validation_issues, *self._audit_to_validation_issues(audit)]

        logger.info("Packaging web research project artifacts...")
        with agent_pipeline_step(self.workflow_id, "package_project"):
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
                "requested_provider": self.runtime_config.requested_provider or self.runtime_config.provider,
                "runtime_provider": self.runtime_config.provider,
                "runtime_model": self.runtime_config.model,
                "provider_overridden": self.runtime_config.provider_overridden,
                "model_overridden": self.runtime_config.model_overridden,
                "workflow": self.workflow_id,
                "source_usage": source_usage_for_workflow(
                    self.workflow_id,
                    external_provider=research.provider,
                ),
                "pipeline": f"{research.provider.title()} external source research + sourced hardware agents",
                "component_source_policy": "web-sourced components; not constrained to seed_db.py",
                "architecture_notes": plan.architecture_notes,
                "recommended_component_roles": plan.recommended_component_roles,
                "sourcing_notes": selection.sourcing_notes,
                "external_research": research.source_metadata(),
                "firecrawl_research": research.source_metadata() if research.provider == "firecrawl" else None,
                "tavily_research": research.source_metadata() if research.provider == "tavily" else None,
                "completeness_audit": audit.model_dump(),
                "image_features": plan.architecture_notes + plan.recommended_component_roles,
                },
                project_version_history=[
                    {
                        "version": "0.1",
                        "description": f"Initial design compilation via {research.provider} external source research workflow",
                    }
                ],
                validation=build_validation_summary(all_issues),
                is_valid=not any(issue.severity.upper() == "CRITICAL" for issue in all_issues),
            )

            project_ir = build_mechanical_render_data(project_ir)
            self._save_project_to_db(user_prompt, project_ir)
        return project_ir

    def _research_queries(self, user_prompt: str) -> List[str]:
        return [
            f"{user_prompt} open source hardware schematic BOM",
            f"{user_prompt} maker project components wiring datasheet",
            f"{user_prompt} Arduino ESP32 module component reference design",
        ]

    def _research(self, queries: List[str]) -> ExternalSourceLibrary:
        emit_agent_note_event(
            self.workflow_id,
            "external_research",
            VISIBLE_WEB_AGENT_DECISION_NOTES["external_research"],
            details={
                "provider": self.research_client.provider_name,
                "query_count": len(queries),
                "queries": queries,
                "phase": "before_research_request",
            },
        )
        emit_agent_pipeline_event(
            self.workflow_id,
            "external_research",
            "provider_request_started",
            details={
                "provider": self.research_client.provider_name,
                "query_count": len(queries),
                "queries": queries,
                "timeout_seconds": self.research_client.config.timeout_seconds,
            },
        )
        research = self.research_client.research(queries)
        for index, source in enumerate(research.sources[:8], start=1):
            metadata = source.metadata or {}
            emit_agent_pipeline_event(
                self.workflow_id,
                "external_research",
                "source_found",
                details={
                    "provider": source.provider or research.provider,
                    "source_index": index,
                    "title": source.title,
                    "url": source.url,
                    "domain": metadata.get("domain"),
                    "source_type": source.source_type,
                    "score": source.score,
                    "relevance_reason": metadata.get("relevance_reason"),
                    "matched_query_terms": metadata.get("matched_query_terms"),
                    "content_preview": source.content[:360],
                },
            )
        emit_agent_pipeline_event(
            self.workflow_id,
            "external_research",
            "provider_response_received" if not research.error else "provider_response_failed",
            details={
                "provider": research.provider,
                "configured": research.configured,
                "searches_attempted": research.searches_attempted,
                "source_count": len(research.sources),
                "error": research.error,
            },
        )
        return research

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

        External source research context:
        {research_context}

        Return WebProjectPlan. Prefer concrete component roles that are supported by the research context.
        Keep the design in safe low-voltage DC maker-electronics scope.
        """
        return self._call_llm_structured(prompt, WebProjectPlan, image_bytes, image_mime_type, pipeline_step_id="web_architect")

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
        Select real, buildable components for this project using external source research and common datasheet-backed maker hardware.

        User request:
        {user_prompt}

        Project plan:
        {plan.model_dump_json()}

        External source research context:
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
        return self._call_llm_structured(prompt, WebComponentSelection, image_bytes, image_mime_type, pipeline_step_id="web_component_sourcing")

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
        return self._call_llm_structured(prompt, WiringWrapper, image_bytes, image_mime_type, pipeline_step_id="wiring_netlist")

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
        return self._call_llm_structured(prompt, WiringWrapper, image_bytes, image_mime_type, pipeline_step_id="validation_repair")

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
        return self._call_llm_structured(prompt, MechanicalNotes, image_bytes, image_mime_type, pipeline_step_id="mechanical_fabrication")

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
        wrapper: AssemblyWrapper = self._call_llm_structured(prompt, AssemblyWrapper, image_bytes, image_mime_type, pipeline_step_id="assembly")
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
            audit: CompletenessAudit = self._call_llm_structured(prompt, CompletenessAudit, pipeline_step_id="completeness_audit")
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
        generation_metadata = self._active_generation_metadata or {}
        public_generation_metadata = {
            key: value
            for key, value in generation_metadata.items()
            if key != "owner_user_id"
        }
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            **public_generation_metadata,
            "project_id": project_id,
        }
        try:
            save_generated_project(
                project_id=project_id,
                title=ir.overview.title if ir.overview else "Untitled Blueprint Project",
                prompt=prompt,
                hardware_ir=ir.model_dump(),
                created_at=datetime.utcnow().isoformat(),
                chat_id=generation_metadata.get("chat_id"),
                owner_user_id=generation_metadata.get("owner_user_id"),
                visibility="public",
            )
            logger.info("Web research workflow project saved to database with ID: %s", project_id)
            return project_id
        except Exception as exc:
            logger.error("Failed to save web research workflow project: %s", exc)
            return ""
