from __future__ import annotations

import re
from typing import List

from blueprint_core.job_source_usage import normalize_generation_workflow_id
from blueprint_core.models import (
    ClarifyingQuestion,
    ClarifyingQuestionsRequest,
    ClarifyingQuestionsResponse,
)


class ContextClarifierAgent:
    """Asks focused pre-generation questions so hardware context is explicit."""

    agent_name = "Context Clarifier Agent"

    def ask(self, request: ClarifyingQuestionsRequest) -> ClarifyingQuestionsResponse:
        prompt = (request.prompt or "").strip()
        workflow = normalize_generation_workflow_id(request.workflow, strict=False)
        if request.max_questions <= 0:
            return self._response(False, "Question limit is zero.", [], workflow)
        if self._already_has_context(prompt):
            return self._response(False, "Human context has already been supplied.", [], workflow)
        if self._user_requested_no_questions(prompt):
            return self._response(False, "User asked to skip clarification.", [], workflow)

        questions = self._questions_for_prompt(prompt, request.has_image)
        limited = questions[: request.max_questions]
        should_ask = bool(limited and (request.force or self._looks_under_specified(prompt, request.has_image)))
        reason = "Ask for missing build context before generation." if should_ask else "Prompt has enough context to generate."
        return self._response(should_ask, reason, limited if should_ask else [], workflow)

    def _response(
        self,
        should_ask: bool,
        reason: str,
        questions: List[ClarifyingQuestion],
        workflow: str,
    ) -> ClarifyingQuestionsResponse:
        return ClarifyingQuestionsResponse(
            agent=self.agent_name,
            should_ask=should_ask,
            reason=reason,
            questions=questions,
            workflow=workflow,
        )

    def _already_has_context(self, prompt: str) -> bool:
        return "human-in-the-loop context:" in prompt.lower()

    def _user_requested_no_questions(self, prompt: str) -> bool:
        lowered = prompt.lower()
        return any(
            marker in lowered
            for marker in (
                "don't ask questions",
                "do not ask questions",
                "no questions",
                "skip questions",
                "generate immediately",
                "build immediately",
            )
        )

    def _looks_under_specified(self, prompt: str, has_image: bool) -> bool:
        if has_image and len(prompt.split()) < 12:
            return True
        signals = (
            "voltage",
            "battery",
            "usb",
            "esp32",
            "arduino",
            "sensor",
            "display",
            "enclosure",
            "weather",
            "budget",
            "cost",
            "validate",
            "success",
        )
        signal_count = sum(1 for signal in signals if signal in prompt.lower())
        return len(prompt.split()) < 18 or signal_count < 2

    def _questions_for_prompt(self, prompt: str, has_image: bool) -> List[ClarifyingQuestion]:
        lower = prompt.lower()
        if re.search(r"(lab[-\s]?on[-\s]?a[-\s]?chip|microfluid|assay|cartridge|diagnostic|reagent|sample)", lower):
            return [
                ClarifyingQuestion(
                    id="sample_assay",
                    label="Sample / Assay",
                    question="What sample, analyte, or assay workflow should this support?",
                    placeholder="Example: water sample, colorimetric nitrate assay, 3 reagent chambers...",
                    suggestions=["Water quality", "Colorimetric assay", "Fluorescence readout"],
                ),
                ClarifyingQuestion(
                    id="instrumentation",
                    label="Reader / Detection",
                    question="What detection and control method should the reader use?",
                    placeholder="Example: LED + photodiode absorbance, heater, pressure sensor, peristaltic pump...",
                    suggestions=["Optical absorbance", "Fluorescence", "Pressure-driven flow"],
                ),
                ClarifyingQuestion(
                    id="validation",
                    label="Validation",
                    question="What needs to be validated first?",
                    placeholder="Example: leak test, limit of detection, repeatability, contamination control...",
                    suggestions=["Leak testing", "Repeatability", "Research-only prototype"],
                ),
            ]

        if re.search(r"(tent|deploy|self[-\s]?assembl|fold|frame|shelter|weatherproof|structure)", lower):
            return [
                ClarifyingQuestion(
                    id="environment",
                    label="Environment",
                    question="Where will this operate, and what weather or load should it survive?",
                    placeholder="Example: camping rain/wind, sandy soil, one-person field setup, 35 mph gust target...",
                    suggestions=["Rain and wind", "Field work", "Portable camping"],
                ),
                ClarifyingQuestion(
                    id="motion_power",
                    label="Motion / Power",
                    question="How should deployment be powered and limited for safety?",
                    placeholder="Example: 12V battery, low-force servos, clutch release, manual crank fallback...",
                    suggestions=["12V battery", "Low-force actuators", "Manual release"],
                ),
                ClarifyingQuestion(
                    id="success",
                    label="Success Criteria",
                    question="What makes version one successful?",
                    placeholder="Example: deploys in under 2 minutes, self-tensions guy lines, never pinches fabric or fingers...",
                    suggestions=["Fast deployment", "Self-tensioning", "Emergency release"],
                ),
            ]

        if re.search(r"(wire|wiring|schematic|pcb|sensor|relay|motor|driver|esp32|arduino|pin|gpio)", lower):
            return [
                ClarifyingQuestion(
                    id="controller_modules",
                    label="Controller / Modules",
                    question="Which controller and major modules should be treated as fixed?",
                    placeholder="Example: ESP32-S3, SSD1306 OLED, SHT41, 5V relay module...",
                    suggestions=["ESP32", "Arduino", "Use generated choice"],
                ),
                ClarifyingQuestion(
                    id="power",
                    label="Power",
                    question="What power rails, battery, or adapter constraints matter?",
                    placeholder="Example: USB-C 5V only, 3S LiPo, no mains, separate motor rail...",
                    suggestions=["USB-C 5V", "Battery powered", "No mains"],
                ),
                ClarifyingQuestion(
                    id="outputs",
                    label="Outputs",
                    question="What should the system control or display?",
                    placeholder="Example: fan PWM, warning LED, buzzer, OLED status, pump relay...",
                    suggestions=["Display status", "Drive actuator", "Log sensor data"],
                ),
            ]

        first_label = "Reference Image" if has_image and not prompt else "Use Case"
        first_question = (
            "What should Forma infer from the attached reference image?"
            if has_image and not prompt
            else "Who uses it, and where does it operate?"
        )
        first_placeholder = (
            "Example: copy the layout, preserve the enclosure shape, identify visible modules..."
            if has_image and not prompt
            else "Example: bench prototype, outdoor field tool, wearable, classroom demo..."
        )
        return [
            ClarifyingQuestion(
                id="use_case",
                label=first_label,
                question=first_question,
                placeholder=first_placeholder,
                suggestions=["Bench prototype", "Field tool", "Consumer device"],
            ),
            ClarifyingQuestion(
                id="constraints",
                label="Constraints",
                question="What hard constraints should the design preserve?",
                placeholder="Example: USB-C only, under $100, waterproof, no enclosure, safe low voltage...",
                suggestions=["Low voltage", "Low cost", "Weatherproof"],
            ),
            ClarifyingQuestion(
                id="outputs",
                label="Artifacts",
                question="What should Forma optimize in the first version?",
                placeholder="Example: wiring accuracy, mechanical concept, product images, validation, BOM...",
                suggestions=["Wiring accuracy", "Mechanical design", "Product images"],
            ),
        ]


def ask_clarifying_questions(request: ClarifyingQuestionsRequest) -> ClarifyingQuestionsResponse:
    return ContextClarifierAgent().ask(request)
