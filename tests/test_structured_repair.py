"""Gate tests for truncation-aware structured-output handling.

These reproduce the production failure "Generation failed: 1 validation error
for MechanicalNotes / Invalid JSON: EOF while parsing a string" - the fine-tuned
parti-base model hits its token budget mid-string on the largest structured
record (MechanicalNotes) and the JSON never closes.

They cover the layers of the fix in blueprint_core/llm_providers.py:
  A - a token budget is always sent, with a floor for large schemas
  B - truncated JSON is salvaged (structure closed, trailing item pruned) and
      still fully validated, so salvage can never invent content
  C - one bounded retry with a larger budget, then LLMProviderOutputError
  D - json_schema response_format is emitted when configured
  E - submodel fields emitted flat at the root are deterministically re-nested
      (the "2 validation errors for WebProjectPlan: overview/requirements Field
      required" production failure), never inventing content
  F - runpod defaults to response_format=json_schema, with a one-shot fallback
      to json_object when the endpoint rejects it, and a guided_json escape
      hatch for older worker-vllm images

Runnable via pytest (the tests are a package, so the isolated_llm_env fixture is
imported from tests.test_llm_runtime).
"""
from __future__ import annotations

import copy
import json
import unittest
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from tests.test_llm_runtime import isolated_llm_env

from blueprint_core import llm_providers as lp
from blueprint_core.agents.web_research_workflow import WebProjectPlan
from blueprint_core.llm import build_llm_provider, resolve_llm_runtime_config
from blueprint_core.llm_providers import (
    LLMProviderOutputError,
    ProviderHTTPStatusError,
    _try_validate_object,
    _validate_structured_json,
)
from blueprint_core.models import (
    MechanicalNotes,
    MechanicalPlacement,
    MechanicalRotation3,
    MechanicalSource,
    MechanicalSpatialRelationship,
    MechanicalVector3,
    ProjectOverview,
)


_LONG = (
    "Leave 2mm clearance around every connector, route the ribbon cable to the "
    "left wall so the lid closes flush without pinching, and keep the standoff "
    "bosses at least 3mm from the board edge to avoid cracking the PETG under "
    "fastener torque during final assembly and field service."
)


def _placement(ref_des: str, label: str) -> MechanicalPlacement:
    return MechanicalPlacement(
        ref_des=ref_des,
        label=label,
        category="Microcontroller",
        layer="electrical",
        position=MechanicalVector3(x_mm=1.5, y_mm=2.5, z_mm=3.5),
        size=MechanicalVector3(x_mm=10.0, y_mm=20.0, z_mm=5.0),
        orientation_deg=MechanicalRotation3(x_deg=0.0, y_deg=0.0, z_deg=90.0),
        mounting_face="floor",
        notes=_LONG,
    )


def _relationship(source: str, target: str, relation: str, axis: str, offset: float) -> MechanicalSpatialRelationship:
    return MechanicalSpatialRelationship(
        source_ref_des=source,
        target_ref_des=target,
        relation=relation,
        axis=axis,
        offset_mm=offset,
        notes=_LONG,
    )


# Ref designators for the placements, in emit order. The LAST one is the item the
# production truncation cuts in half.
_REFS: List[Tuple[str, str]] = [
    ("U1", "ESP32 Development Board"),
    ("D1", "SSD1306 OLED Display"),
    ("SEN1", "DHT22 Temperature Sensor"),
    ("BAT1", "LiPo Battery Pack"),
    ("SW1", "Panel Slide Switch"),
    ("J1", "USB-C Power Jack"),
    ("LED1", "Status Indicator LED"),
]


def build_mechanical_notes() -> MechanicalNotes:
    """A realistic MechanicalNotes whose model_dump_json() is a large record."""
    return MechanicalNotes(
        enclosure_type="3D Printed",
        mounting_guidance=(
            "Use four M3 brass standoffs at 5mm height on the floor plate; secure "
            "the lid with self-tapping screws into printed bosses. " + _LONG
        ),
        fabrication_details=[_LONG, _LONG, _LONG],
        fabrication_cost_estimate_usd=12.5,
        cad_sources=[
            MechanicalSource(
                name="Parametric Enclosure",
                source_type="Open STL",
                url="https://example.com/enclosure.stl",
                file_formats=["STL", "STEP"],
                license="CC-BY-4.0",
                estimated_unit_price_usd=0.0,
                notes=_LONG,
            )
        ],
        manufacturability_rating="Moderate",
        render_dimensions=MechanicalVector3(x_mm=80.0, y_mm=60.0, z_mm=30.0),
        component_placements=[_placement(ref, label) for ref, label in _REFS],
        spatial_relationships=[
            _relationship("D1", "U1", "centered-above", "Z", 6.0),
            _relationship("SEN1", "U1", "adjacent-to", "X", 15.0),
            _relationship("BAT1", "U1", "mounted-on", "Z", -8.0),
        ],
    )


def truncated_tail_json() -> str:
    """Full record cut mid-string inside the LAST placement.

    The trailing placement is left with only a subset of keys, exactly the
    truncation debris the pruner removes; every earlier placement is intact and
    the record still validates after salvage.
    """
    full = build_mechanical_notes().model_dump_json()
    label = _REFS[-1][1]
    cut_at = full.rfind(label) + len(label) // 2
    return full[:cut_at]


def truncated_before_required_json() -> str:
    """Full record cut BEFORE the required manufacturability_rating field.

    Salvage can close the structure but cannot invent the missing required
    field, so full validation must still fail.
    """
    full = build_mechanical_notes().model_dump_json()
    cut_at = full.find('"manufacturability_rating"')
    assert cut_at != -1
    return full[:cut_at]


def _runpod_provider(**env_overrides: str):
    """Build a configured runpod OpenAI-compatible provider under isolated env."""
    with isolated_llm_env(
        LLM_PROVIDER="runpod",
        LLM_ALLOWED_PROVIDERS="runpod,simulation",
        RUNPOD_API_KEY="rpa_test",
        RUNPOD_OPENAI_BASE_URL="https://api.runpod.ai/v2/test/openai/v1",
        RUNPOD_OPENAI_MODEL="caid-technologies/parti-base",
        RUNPOD_VALIDATE_MODELS="false",
        **env_overrides,
    ):
        runtime = resolve_llm_runtime_config("runpod", "caid-technologies/parti-base")
        return build_llm_provider(runtime_config=runtime)


def _fake_request(responses: List[Tuple[str, Optional[str]]], captured: List[Dict[str, Any]]):
    """Fake _request_json returning (content, finish_reason) pairs in order.

    Each call snapshots the payload (the provider mutates one dict across retry
    attempts, so a live snapshot is required to see the per-attempt budget).
    """
    iterator = iter(responses)

    def fake(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        captured.append(copy.deepcopy(payload or {}))
        content, finish_reason = next(iterator)
        return {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}

    return fake


def _fake_request_scripted(script: List[Any], captured: List[Dict[str, Any]]):
    """Like _fake_request, but a script item may be an Exception to raise."""
    iterator = iter(script)

    def fake(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        captured.append(copy.deepcopy(payload or {}))
        item = next(iterator)
        if isinstance(item, Exception):
            raise item
        content, finish_reason = item
        return {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}

    return fake


def flat_web_project_plan() -> Dict[str, Any]:
    """The production failure shape: WebProjectPlan's submodel fields emitted
    flat at the root, with the wrapper key 'requirements' present as the INNER
    FunctionalRequirements.requirements list instead of the submodel object."""
    return {
        "title": "Smart Plant Monitor",
        "description": "ESP32 station that measures soil moisture and reports over WiFi.",
        "difficulty": "Beginner",
        "category": "IoT",
        "estimated_cost": 24.5,
        "requirements": ["Measure soil moisture hourly", "Report readings over WiFi"],
        "power_needs": "5V USB",
        "operating_voltage": 3.3,
        "physical_constraints": ["Fits a 90x60x30mm enclosure"],
        "architecture_notes": ["Use a capacitive soil probe to avoid corrosion"],
        "research_keywords": ["capacitive soil moisture sensor"],
    }


def build_web_project_plan() -> WebProjectPlan:
    flat = flat_web_project_plan()
    return WebProjectPlan.model_validate(
        {
            "overview": {key: flat[key] for key in ("title", "description", "difficulty", "category", "estimated_cost")},
            "requirements": {
                "requirements": flat["requirements"],
                "power_needs": flat["power_needs"],
                "operating_voltage": flat["operating_voltage"],
                "physical_constraints": flat["physical_constraints"],
            },
            "architecture_notes": flat["architecture_notes"],
            "research_keywords": flat["research_keywords"],
        }
    )


class _EngineA(BaseModel):
    shared_speed: int
    a_only: str = ""


class _EngineB(BaseModel):
    shared_speed: int
    b_only: str = ""


class _AmbiguousWrapper(BaseModel):
    engine_a: _EngineA
    engine_b: _EngineB


class _InnerWithSharedName(BaseModel):
    payload_note: str
    shared_list: List[str] = Field(default_factory=list)


class _WrapperWithSharedName(BaseModel):
    inner: _InnerWithSharedName
    shared_list: List[str] = Field(default_factory=list)


class StructuredRepairTests(unittest.TestCase):
    # --- Layer B: salvage --------------------------------------------------

    def test_truncated_mechanical_notes_is_salvaged(self) -> None:
        truncated = truncated_tail_json()
        self.assertGreater(len(truncated), 3000)  # a genuinely large record

        with self.assertLogs("blueprint_core.llm_providers", level="WARNING") as logs:
            result = _validate_structured_json(truncated, MechanicalNotes)

        self.assertIsInstance(result, MechanicalNotes)
        refs = [p.ref_des for p in result.component_placements]
        # Every earlier placement survives; the half-written trailing one is gone.
        self.assertEqual([ref for ref, _ in _REFS[:-1]], refs)
        self.assertNotIn(_REFS[-1][0], refs)
        self.assertTrue(any("required JSON salvage" in line for line in logs.output))

    def test_salvage_never_invents_required_fields(self) -> None:
        truncated = truncated_before_required_json()
        # manufacturability_rating is required and was cut off; salvage closes the
        # structure but cannot invent it, so validation must still fail.
        with self.assertRaises(Exception):
            _validate_structured_json(truncated, MechanicalNotes)

    # --- Layer A: always-sent token budget ---------------------------------

    def test_max_tokens_always_sent_when_no_env_cap(self) -> None:
        provider = _runpod_provider()  # no RUNPOD_MAX_TOKENS
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [(build_mechanical_notes().model_dump_json(), "stop")], captured
        )

        provider.generate_structured("Design an enclosure.", MechanicalNotes)

        self.assertEqual(1, len(captured))
        self.assertEqual(lp.DEFAULT_STRUCTURED_MAX_TOKENS, captured[0]["max_tokens"])
        self.assertNotIn("max_completion_tokens", captured[0])

    def test_large_schema_floor_and_small_schema_untouched(self) -> None:
        # Large schema with a too-small configured cap is raised to the floor.
        provider = _runpod_provider(RUNPOD_MAX_TOKENS="500")
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [(build_mechanical_notes().model_dump_json(), "stop")], captured
        )
        provider.generate_structured("Design an enclosure.", MechanicalNotes)
        self.assertEqual(lp.STRUCTURED_MAX_TOKENS_FLOOR, captured[0]["max_tokens"])

        # Small schema keeps the configured cap.
        small_provider = _runpod_provider(RUNPOD_MAX_TOKENS="500")
        small_captured: List[Dict[str, Any]] = []
        overview = ProjectOverview(
            title="Test",
            description="A small project.",
            difficulty="Beginner",
            estimated_cost=1.0,
            category="IoT",
        )
        small_provider._request_json = _fake_request(
            [(overview.model_dump_json(), "stop")], small_captured
        )
        small_provider.generate_structured("Summarize.", ProjectOverview)
        self.assertEqual(500, small_captured[0]["max_tokens"])

    # --- Layer C: one bounded retry ----------------------------------------

    def test_retry_once_with_increased_budget(self) -> None:
        provider = _runpod_provider()
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [
                (truncated_before_required_json(), "length"),  # unsalvageable
                (build_mechanical_notes().model_dump_json(), "stop"),  # complete
            ],
            captured,
        )

        result = provider.generate_structured("Design an enclosure.", MechanicalNotes)

        self.assertIsInstance(result, MechanicalNotes)
        self.assertEqual(2, len(captured))  # exactly one retry
        self.assertGreater(captured[1]["max_tokens"], captured[0]["max_tokens"])
        self.assertLessEqual(captured[1]["max_tokens"], lp.STRUCTURED_MAX_TOKENS_CEILING)

    def test_retry_exhaustion_raises_output_error(self) -> None:
        provider = _runpod_provider()
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [
                (truncated_before_required_json(), "length"),
                (truncated_before_required_json(), "length"),
            ],
            captured,
        )

        with self.assertRaises(LLMProviderOutputError):
            provider.generate_structured("Design an enclosure.", MechanicalNotes)

        self.assertEqual(2, len(captured))  # exactly two attempts, no more

    # --- Layer D: json_schema response_format ------------------------------

    def test_json_schema_response_format_embeds_schema(self) -> None:
        provider = _runpod_provider(RUNPOD_RESPONSE_FORMAT="json_schema")
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [(build_mechanical_notes().model_dump_json(), "stop")], captured
        )

        provider.generate_structured("Design an enclosure.", MechanicalNotes)

        response_format = captured[0]["response_format"]
        self.assertEqual("json_schema", response_format["type"])
        self.assertEqual(
            MechanicalNotes.model_json_schema(),
            response_format["json_schema"]["schema"],
        )

    # --- Layer E: flat-field re-nesting -------------------------------------

    def test_flat_webprojectplan_is_renested(self) -> None:
        """Exact production repro: '2 validation errors for WebProjectPlan'."""
        flat_json = json.dumps(flat_web_project_plan())

        with self.assertLogs("blueprint_core.llm_providers", level="WARNING") as logs:
            result = _validate_structured_json(flat_json, WebProjectPlan)

        self.assertIsInstance(result, WebProjectPlan)
        self.assertEqual("Smart Plant Monitor", result.overview.title)
        self.assertEqual("IoT", result.overview.category)
        self.assertEqual(24.5, result.overview.estimated_cost)
        self.assertEqual("5V USB", result.requirements.power_needs)
        self.assertEqual(
            ["Measure soil moisture hourly", "Report readings over WiFi"],
            result.requirements.requirements,
        )
        # The wrapper's own optional list fields stay at the root.
        self.assertEqual(["Use a capacitive soil probe to avoid corrosion"], result.architecture_notes)
        self.assertEqual(["capacitive soil moisture sensor"], result.research_keywords)
        self.assertTrue(any("flat-field re-nesting" in line for line in logs.output))

    def test_renesting_never_invents_content(self) -> None:
        # power_needs is FunctionalRequirements' only required field; without it
        # the 'requirements' wrapper must NOT be fabricated.
        missing_power = flat_web_project_plan()
        del missing_power["power_needs"]
        with self.assertRaises(ValidationError):
            _validate_structured_json(json.dumps(missing_power), WebProjectPlan)

        # title is required on ProjectOverview; same rule for 'overview'.
        missing_title = flat_web_project_plan()
        del missing_title["title"]
        with self.assertRaises(ValidationError):
            _validate_structured_json(json.dumps(missing_title), WebProjectPlan)

    def test_renesting_skips_ambiguous_collisions(self) -> None:
        # shared_speed is claimable by both engine_a and engine_b; ownership is
        # never guessed, so neither wrapper is re-nested and validation fails.
        with self.assertRaises(ValidationError):
            _try_validate_object(
                {"shared_speed": 5, "a_only": "x", "b_only": "y"},
                _AmbiguousWrapper,
            )

    def test_same_name_inner_field_renested_and_valid_dict_untouched(self) -> None:
        # 'requirements' present as the inner list, everything else nested: only
        # the provably-invalid same-name key is re-nested.
        obj = {
            "overview": {
                "title": "Clock",
                "description": "A desk clock.",
                "difficulty": "Beginner",
                "category": "IoT",
            },
            "requirements": ["Show the time"],
            "power_needs": "5V USB",
        }
        result = _try_validate_object(obj, WebProjectPlan)
        self.assertEqual(["Show the time"], result.requirements.requirements)
        self.assertEqual("5V USB", result.requirements.power_needs)

        # A valid nested record passes through untouched, with no repair log.
        valid = build_web_project_plan()
        with self.assertNoLogs("blueprint_core.llm_providers", level="WARNING"):
            round_tripped = _validate_structured_json(valid.model_dump_json(), WebProjectPlan)
        self.assertEqual(valid, round_tripped)

    def test_wrapper_own_field_not_swallowed_by_submodel(self) -> None:
        # shared_list is a declared field of BOTH the wrapper and the submodel;
        # it must stay at the root, not be claimed into 'inner'.
        result = _try_validate_object(
            {"payload_note": "route cables left", "shared_list": ["keep-at-root"]},
            _WrapperWithSharedName,
        )
        self.assertEqual(["keep-at-root"], result.shared_list)
        self.assertEqual("route cables left", result.inner.payload_note)
        self.assertEqual([], result.inner.shared_list)

    def test_renesting_composes_with_salvage(self) -> None:
        # Flat output truncated mid-string: salvage closes the JSON, then the
        # re-nesting layer recovers the wrapper structure.
        flat_json = json.dumps(flat_web_project_plan())
        cut_at = flat_json.rfind("capacitive soil moisture sensor") + len("capacitive soil")
        truncated = flat_json[:cut_at]

        with self.assertLogs("blueprint_core.llm_providers", level="WARNING") as logs:
            result = _validate_structured_json(truncated, WebProjectPlan)

        self.assertIsInstance(result, WebProjectPlan)
        self.assertEqual("Smart Plant Monitor", result.overview.title)
        self.assertEqual("5V USB", result.requirements.power_needs)
        self.assertTrue(any("flat-field re-nesting" in line for line in logs.output))
        self.assertTrue(any("required JSON salvage" in line for line in logs.output))

    def test_serverless_dict_output_is_renested(self) -> None:
        with isolated_llm_env(
            RUNPOD_API_KEY="rpa_test",
            RUNPOD_ENDPOINT_ID="test-endpoint",
        ):
            provider = lp.RunpodServerlessProvider(model_name="caid-technologies/parti-base")
        self.assertTrue(provider.is_configured)

        def fake(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return {"status": "COMPLETED", "output": flat_web_project_plan()}

        provider._request_json = fake
        result = provider.generate_structured("Plan a plant monitor.", WebProjectPlan)
        self.assertIsInstance(result, WebProjectPlan)
        self.assertEqual("Smart Plant Monitor", result.overview.title)

    # --- Layer F: runpod json_schema default + fallback ---------------------

    def test_runpod_default_response_format_is_json_schema(self) -> None:
        provider = _runpod_provider()  # no RUNPOD_RESPONSE_FORMAT env
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [(build_web_project_plan().model_dump_json(), "stop")], captured
        )

        provider.generate_structured("Plan a plant monitor.", WebProjectPlan)

        response_format = captured[0]["response_format"]
        self.assertEqual("json_schema", response_format["type"])
        self.assertEqual(
            WebProjectPlan.model_json_schema(),
            response_format["json_schema"]["schema"],
        )

        # Env override still wins for old workers.
        overridden = _runpod_provider(RUNPOD_RESPONSE_FORMAT="json_object")
        overridden_captured: List[Dict[str, Any]] = []
        overridden._request_json = _fake_request(
            [(build_web_project_plan().model_dump_json(), "stop")], overridden_captured
        )
        overridden.generate_structured("Plan a plant monitor.", WebProjectPlan)
        self.assertEqual({"type": "json_object"}, overridden_captured[0]["response_format"])

    def test_json_schema_rejection_falls_back_to_json_object(self) -> None:
        provider = _runpod_provider()
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request_scripted(
            [
                ProviderHTTPStatusError("runpod request failed with HTTP 400: bad response_format", 400),
                (build_web_project_plan().model_dump_json(), "stop"),
            ],
            captured,
        )

        with self.assertLogs("blueprint_core.llm_providers", level="WARNING") as logs:
            result = provider.generate_structured("Plan a plant monitor.", WebProjectPlan)

        self.assertIsInstance(result, WebProjectPlan)
        self.assertEqual(2, len(captured))
        self.assertEqual("json_schema", captured[0]["response_format"]["type"])
        self.assertEqual({"type": "json_object"}, captured[1]["response_format"])
        self.assertTrue(any("rejected response_format=json_schema" in line for line in logs.output))

        # The downgrade is cached AND the capability probe did not consume the
        # validation-retry budget: a later unusable response still gets its full
        # two attempts, both already in json_object mode.
        second_captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request_scripted(
            [
                (truncated_before_required_json(), "length"),
                (truncated_before_required_json(), "length"),
            ],
            second_captured,
        )
        with self.assertRaises(LLMProviderOutputError):
            provider.generate_structured("Design an enclosure.", MechanicalNotes)
        self.assertEqual(2, len(second_captured))
        for payload in second_captured:
            self.assertEqual({"type": "json_object"}, payload["response_format"])

    def test_non_format_http_errors_propagate(self) -> None:
        provider = _runpod_provider()
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request_scripted(
            [ProviderHTTPStatusError("runpod request failed with HTTP 500: boom", 500)],
            captured,
        )
        with self.assertRaises(ProviderHTTPStatusError):
            provider.generate_structured("Plan a plant monitor.", WebProjectPlan)
        self.assertEqual(1, len(captured))  # no fallback re-issue for non-4xx

    def test_guided_json_mode_sends_extra_body(self) -> None:
        provider = _runpod_provider(RUNPOD_RESPONSE_FORMAT="guided_json")
        captured: List[Dict[str, Any]] = []
        provider._request_json = _fake_request(
            [(build_web_project_plan().model_dump_json(), "stop")], captured
        )

        provider.generate_structured("Plan a plant monitor.", WebProjectPlan)

        self.assertEqual({"type": "json_object"}, captured[0]["response_format"])
        self.assertEqual(WebProjectPlan.model_json_schema(), captured[0]["guided_json"])


if __name__ == "__main__":
    unittest.main()
