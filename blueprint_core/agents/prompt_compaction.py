from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)


OPENAI_IMAGE_PROMPT_MAX_CHARS = 32000
DEFAULT_IMAGE_PROMPT_TARGET_CHARS = 28000


@dataclass(frozen=True)
class PromptCompactionResult:
    prompt: str
    original_length: int
    final_length: int
    was_compacted: bool
    strategy: str = "none"


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _keep_keys(source: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    return {key: source[key] for key in keys if key in source and source[key] not in (None, "", [], {})}


def _pins_for_net(net: Dict[str, Any], limit: int) -> List[str]:
    pins = []
    for pin in _list(net.get("pins"))[:limit]:
        pin_data = _dict(pin)
        ref_des = str(pin_data.get("ref_des") or "").strip()
        pin_id = str(pin_data.get("pin_id") or "").strip()
        if ref_des and pin_id:
            pins.append(f"{ref_des}.{pin_id}")
        elif ref_des:
            pins.append(ref_des)
    return pins


def _component_briefs(spec: Dict[str, Any], *, limit: int, text_limit: int) -> List[Dict[str, Any]]:
    assembly_model = _dict(spec.get("design_assembly_model"))
    placements = {
        str(item.get("ref_des") or ""): item
        for item in _list(spec.get("component_placements"))
        if isinstance(item, dict) and item.get("ref_des")
    }
    mounting = {
        str(item.get("ref_des") or ""): item
        for item in _list(assembly_model.get("component_mounting_zones"))
        if isinstance(item, dict) and item.get("ref_des")
    }

    briefs = []
    for component in _list(spec.get("components"))[:limit]:
        if not isinstance(component, dict):
            continue
        ref_des = str(component.get("ref_des") or "").strip()
        placement = _dict(placements.get(ref_des))
        mounted = _dict(mounting.get(ref_des))
        brief = {
            "ref": ref_des,
            "name": _truncate(component.get("name"), text_limit),
            "part": _truncate(component.get("part_number"), 80),
            "category": _truncate(component.get("category"), 60),
            "role": mounted.get("visual_role"),
            "subsystem": mounted.get("subsystem"),
            "zone": mounted.get("mounting_zone"),
            "mounted_on": mounted.get("mounted_on") or placement.get("mounting_face"),
            "facing_normal": mounted.get("facing_normal"),
            "position_mm": placement.get("position_mm") or mounted.get("position_mm"),
            "size_mm": placement.get("size_mm") or mounted.get("size_mm"),
        }
        briefs.append({key: value for key, value in brief.items() if value not in (None, "", [], {})})
    return briefs


def _net_briefs(spec: Dict[str, Any], *, limit: int, pin_limit: int) -> List[Dict[str, Any]]:
    briefs = []
    for net in _list(spec.get("connection_nets"))[:limit]:
        if not isinstance(net, dict):
            continue
        brief = _keep_keys(net, ["net_id", "name", "net_type", "voltage"])
        pins = _pins_for_net(net, pin_limit)
        if pins:
            brief["pins"] = pins
        briefs.append(brief)
    return briefs


def _subsystem_briefs(spec: Dict[str, Any], *, limit: int, list_limit: int, text_limit: int) -> List[Dict[str, Any]]:
    briefs = []
    for subsystem in _list(spec.get("subsystems"))[:limit]:
        if not isinstance(subsystem, dict):
            continue
        contract = _dict(subsystem.get("contract"))
        brief: Dict[str, Any] = {
            "id": subsystem.get("id"),
            "label": subsystem.get("label"),
            "refs": _list(subsystem.get("component_refs"))[:list_limit],
            "zones": _list(subsystem.get("mounting_zones"))[:list_limit],
            "facing": _list(subsystem.get("facing_normals"))[:list_limit],
        }
        if contract:
            brief["contract"] = {
                "purpose": _truncate(contract.get("purpose"), text_limit),
                "interfaces": [_truncate(item, text_limit) for item in _list(contract.get("physical_interfaces"))[:list_limit]],
                "constraints": [_truncate(item, text_limit) for item in _list(contract.get("placement_constraints"))[:list_limit]],
                "checks": [_truncate(item, text_limit) for item in _list(contract.get("verification_checks"))[: max(1, list_limit - 1)]],
                "relevant_nets": [_truncate(item, text_limit) for item in _list(contract.get("relevant_nets"))[:list_limit]],
            }
        briefs.append({key: value for key, value in brief.items() if value not in (None, "", [], {})})
    return briefs


def _dependency_briefs(spec: Dict[str, Any], *, limit: int, text_limit: int) -> List[Dict[str, Any]]:
    briefs = []
    for edge in _list(spec.get("physical_dependency_graph"))[:limit]:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source_subsystem") or edge.get("source_ref_des")
        target = edge.get("target_subsystem") or edge.get("target_ref_des")
        brief = {
            "from": source,
            "to": target,
            "interface": _truncate(edge.get("interface"), text_limit),
            "check": _truncate(edge.get("design_check"), text_limit),
        }
        briefs.append({key: value for key, value in brief.items() if value not in (None, "", [], {})})
    return briefs


def _assembly_state_briefs(spec: Dict[str, Any], *, limit: int, text_limit: int) -> List[Dict[str, Any]]:
    briefs = []
    for state in _list(spec.get("assembly_states"))[:limit]:
        if not isinstance(state, dict):
            continue
        briefs.append(
            {
                "id": state.get("id"),
                "purpose": _truncate(state.get("purpose"), text_limit),
                "visible": [_truncate(item, text_limit) for item in _list(state.get("visible"))[:4]],
                "hidden": [_truncate(item, text_limit) for item in _list(state.get("hidden"))[:3]],
            }
        )
    return briefs


def _behavior_brief(spec: Dict[str, Any], *, list_limit: int, text_limit: int) -> Dict[str, Any]:
    behavior = _dict(spec.get("behavior_control_model"))
    if not behavior:
        return {}
    brief = _keep_keys(
        behavior,
        [
            "control_model_type",
            "controlled_variables",
            "setpoint_sources",
            "measurement_sources",
            "controller_refs",
            "driver_refs",
            "actuator_refs",
            "feedback_nets",
            "control_output_nets",
            "missing_feedback_warning",
        ],
    )
    for key, value in list(brief.items()):
        if isinstance(value, list):
            brief[key] = [_truncate(item, text_limit) for item in value[:list_limit]]
    return brief


def _compact_visual_spec(spec: Dict[str, Any], profile: str) -> Dict[str, Any]:
    profiles = {
        "standard": {
            "components": 20,
            "nets": 16,
            "pins": 6,
            "subsystems": 8,
            "dependencies": 18,
            "list_limit": 4,
            "text_limit": 150,
            "labels": 48,
            "rules": 10,
        },
        "tight": {
            "components": 16,
            "nets": 10,
            "pins": 4,
            "subsystems": 7,
            "dependencies": 12,
            "list_limit": 3,
            "text_limit": 110,
            "labels": 32,
            "rules": 8,
        },
        "minimal": {
            "components": 12,
            "nets": 6,
            "pins": 3,
            "subsystems": 6,
            "dependencies": 8,
            "list_limit": 2,
            "text_limit": 80,
            "labels": 24,
            "rules": 6,
        },
    }
    settings = profiles.get(profile, profiles["standard"])
    assembly_model = _dict(spec.get("design_assembly_model"))

    compact = {
        "title": _truncate(spec.get("title"), 140),
        "description": _truncate(spec.get("description"), 260 if profile == "standard" else 180),
        "dimensions_mm": {
            "external": spec.get("external_dimensions_mm"),
            "internal_usable": spec.get("internal_usable_dimensions_mm"),
        },
        "enclosure_type": _truncate(spec.get("enclosure_type"), 120),
        "mounting_guidance": _truncate(spec.get("mounting_guidance"), 160),
        "coordinate_frame": _dict(assembly_model.get("coordinate_frame")),
        "components": _component_briefs(
            spec,
            limit=settings["components"],
            text_limit=settings["text_limit"],
        ),
        "connection_nets": _net_briefs(spec, limit=settings["nets"], pin_limit=settings["pins"]),
        "subsystem_contracts": _subsystem_briefs(
            spec,
            limit=settings["subsystems"],
            list_limit=settings["list_limit"],
            text_limit=settings["text_limit"],
        ),
        "physical_dependency_graph": _dependency_briefs(
            spec,
            limit=settings["dependencies"],
            text_limit=settings["text_limit"],
        ),
        "behavior_control_model": _behavior_brief(
            spec,
            list_limit=settings["list_limit"],
            text_limit=settings["text_limit"],
        ),
        "assembly_states": _assembly_state_briefs(spec, limit=4, text_limit=settings["text_limit"]),
        "orientation_landmarks": [
            _truncate(item, settings["text_limit"])
            for item in _list(assembly_model.get("orientation_landmarks"))[: settings["rules"]]
        ],
        "continuity_checks": [
            _truncate(item, settings["text_limit"])
            for item in _list(assembly_model.get("continuity_checks"))[: settings["rules"]]
        ],
        "control_loop_visual_requirements": [
            _truncate(item, settings["text_limit"])
            for item in _list(spec.get("control_loop_visual_requirements"))[: settings["list_limit"]]
        ],
        "allowed_visual_labels": [_truncate(item, 80) for item in _list(spec.get("allowed_visual_labels"))[: settings["labels"]]],
        "truth_rules": [_truncate(item, settings["text_limit"]) for item in _list(spec.get("truth_rules"))[: settings["rules"]]],
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _looks_like_visual_spec(value: Dict[str, Any]) -> bool:
    return bool(
        value.get("design_assembly_model")
        or (value.get("components") and value.get("component_placements"))
        or (value.get("subsystems") and value.get("external_dimensions_mm"))
    )


class PromptCompactionAgent:
    """Deterministically compacts oversized prompts while preserving visual constraints."""

    def compact_if_needed(
        self,
        prompt: str,
        *,
        max_chars: int = OPENAI_IMAGE_PROMPT_MAX_CHARS,
        target_chars: int = DEFAULT_IMAGE_PROMPT_TARGET_CHARS,
        label: str = "prompt",
    ) -> PromptCompactionResult:
        prompt = prompt or ""
        max_chars = max(1000, int(max_chars or OPENAI_IMAGE_PROMPT_MAX_CHARS))
        target_chars = max(1000, min(int(target_chars or DEFAULT_IMAGE_PROMPT_TARGET_CHARS), max_chars - 1))
        original_length = len(prompt)
        if original_length <= target_chars:
            return PromptCompactionResult(prompt, original_length, original_length, False)

        compacted = self._replace_visual_spec_json(prompt, target_chars=target_chars)
        strategy = "visual_spec_summary" if compacted != prompt else "line_budget"
        if len(compacted) > target_chars:
            compacted = self._trim_low_value_lines(compacted, target_chars)
            strategy = f"{strategy}+line_trim"
        if len(compacted) > max_chars:
            compacted = self._emergency_fit(compacted, max_chars)
            strategy = f"{strategy}+emergency_fit"

        final_length = len(compacted)
        if final_length > max_chars:
            raise ValueError(f"{label} compaction failed: {final_length} chars still exceeds {max_chars}.")

        was_compacted = compacted != prompt
        if was_compacted:
            logger.info(
                "Compacted %s from %s to %s characters using %s.",
                label,
                original_length,
                final_length,
                strategy,
            )
        return PromptCompactionResult(compacted, original_length, final_length, was_compacted, strategy)

    def _replace_visual_spec_json(self, prompt: str, *, target_chars: int) -> str:
        lines = prompt.splitlines()
        changed = False
        non_json_chars = sum(len(line) + 1 for line in lines)

        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("{") or not stripped.endswith("}"):
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict) or not _looks_like_visual_spec(parsed):
                continue

            spec_budget = max(4000, target_chars - (non_json_chars - len(line)) - 500)
            replacement = self._visual_spec_summary_json(parsed, spec_budget)
            if replacement != stripped:
                lines[index] = replacement
                changed = True

        return "\n".join(lines) if changed else prompt

    def _visual_spec_summary_json(self, spec: Dict[str, Any], budget: int) -> str:
        for profile in ("standard", "tight", "minimal"):
            compact = _compact_visual_spec(spec, profile)
            text = json.dumps(compact, separators=(",", ":"), ensure_ascii=True)
            if len(text) <= budget:
                return text

        fallback = {
            "title": _truncate(spec.get("title"), 120),
            "description": _truncate(spec.get("description"), 160),
            "dimensions_mm": {
                "external": spec.get("external_dimensions_mm"),
                "internal_usable": spec.get("internal_usable_dimensions_mm"),
            },
            "components": [
                _keep_keys(component, ["ref_des", "name", "category"])
                for component in _list(spec.get("components"))[:10]
                if isinstance(component, dict)
            ],
            "behavior_control_model": _behavior_brief(spec, list_limit=2, text_limit=80),
            "truth_rules": [_truncate(item, 90) for item in _list(spec.get("truth_rules"))[:4]],
        }
        fallback_text = json.dumps(fallback, separators=(",", ":"), ensure_ascii=True)
        if len(fallback_text) <= budget:
            return fallback_text
        return json.dumps(
            {
                "title": _truncate(spec.get("title"), 80),
                "dimensions_mm": {
                    "external": spec.get("external_dimensions_mm"),
                    "internal_usable": spec.get("internal_usable_dimensions_mm"),
                },
                "note": "visual spec compacted to provider prompt budget",
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )

    def _trim_low_value_lines(self, prompt: str, target_chars: int) -> str:
        lines = prompt.splitlines()
        low_value_markers = (
            "failure modes",
            "fabrication notes",
            "cad sources",
            "hardware kit",
            "do not add labels",
            "safe low-voltage",
            "clean neutral",
            "white or light",
        )
        kept = []
        for line in lines:
            lowered = line.lower()
            if len("\n".join(kept)) > target_chars and any(marker in lowered for marker in low_value_markers):
                continue
            kept.append(line)
        text = "\n".join(kept)
        if len(text) <= target_chars:
            return text

        shortened = []
        for line in kept:
            if len(line) > 3000:
                line = line[:2999].rstrip() + "..."
            shortened.append(line)
        return "\n".join(shortened)

    def _emergency_fit(self, prompt: str, max_chars: int) -> str:
        notice = "\n[Prompt compacted to provider limit: middle detail removed, preserve visible dimensions, components, mounting planes, and stage rules.]\n"
        budget = max_chars - len(notice) - 1
        if budget <= 0:
            return prompt[:max_chars]
        head_chars = int(budget * 0.68)
        tail_chars = budget - head_chars
        return prompt[:head_chars].rstrip() + notice + prompt[-tail_chars:].lstrip()
