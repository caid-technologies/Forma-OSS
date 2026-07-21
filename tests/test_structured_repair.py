"""Gate tests for truncation-aware structured-output handling.

These reproduce the production failure "Generation failed: 1 validation error
for MechanicalNotes / Invalid JSON: EOF while parsing a string" - the fine-tuned
parti-base model hits its token budget mid-string on the largest structured
record (MechanicalNotes) and the JSON never closes.

They cover the four layers of the fix in blueprint_core/llm_providers.py:
  A - a token budget is always sent, with a floor for large schemas
  B - truncated JSON is salvaged (structure closed, trailing item pruned) and
      still fully validated, so salvage can never invent content
  C - one bounded retry with a larger budget, then LLMProviderOutputError
  D - json_schema response_format is emitted when configured

Runnable via pytest (the tests are a package, so the isolated_llm_env fixture is
imported from tests.test_llm_runtime).
"""
from __future__ import annotations

import copy
import json
import unittest
from typing import Any, Dict, List, Optional, Tuple

from tests.test_llm_runtime import isolated_llm_env

from blueprint_core import llm_providers as lp
from blueprint_core.llm import build_llm_provider, resolve_llm_runtime_config
from blueprint_core.llm_providers import (
    LLMProviderOutputError,
    _schema_with_closed_objects,
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

    def test_anthropic_closed_schema_marks_nested_objects(self) -> None:
        schema = _schema_with_closed_objects(MechanicalNotes.model_json_schema())

        def assert_objects_closed(node: Any, path: str = "schema") -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertEqual(False, node.get("additionalProperties"), path)
                for key, value in node.items():
                    assert_objects_closed(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    assert_objects_closed(value, f"{path}[{index}]")

        assert_objects_closed(schema)


if __name__ == "__main__":
    unittest.main()
