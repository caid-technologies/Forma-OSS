"""Persistence boundary for independently committed design-generation data."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Protocol, TypedDict

from pydantic import BaseModel, Field

from forma_core.design_generation.completeness.models import (
    BomLineTrace,
    ComponentRole,
    DesignObligation,
    SubsystemPlan,
)
from forma_core.design_generation.components.selection import PartSelectionDraft
from forma_core.design_generation.intent.models import MachineIntent
from forma_core.design_generation.state_machine.models import DesignGenerationState
from forma_core.workspaces.projects.models import (
    AssemblyStep,
    BOMLineItem,
    ComponentInstance,
    ConnectionNet,
    PartDefinition,
    PinMappingEntry,
)


class ProjectFragments(BaseModel):
    """Wiring and assembly fragments persisted before HardwareIR compilation."""

    nets: list[ConnectionNet] = Field(default_factory=list)
    pin_mappings: list[PinMappingEntry] = Field(default_factory=list)
    assembly: list[AssemblyStep] = Field(default_factory=list)


class _ProjectRecord(TypedDict):
    """Typed in-memory record for one intent-first project."""

    intent: MachineIntent | None
    obligations: list[DesignObligation]
    subsystems: list[SubsystemPlan]
    roles: list[ComponentRole]
    selections: dict[str, PartSelectionDraft]
    definitions: list[PartDefinition]
    instances: list[ComponentInstance]
    bom: list[BOMLineItem]
    bom_traces: list[BomLineTrace]
    fragments: ProjectFragments
    state: DesignGenerationState | None


class DesignCheckpointError(RuntimeError):
    """Durable checkpointing failed; generation must not continue past it."""


class DesignGenerationRepository(Protocol):
    """Persistence contract used by the explicit intent-first state machine."""

    def initialize_project(self, project_id: str) -> None: ...
    def save_intent(self, intent: MachineIntent) -> None: ...
    def get_intent(self, project_id: str) -> MachineIntent | None: ...
    def get_intent_by_id(self, intent_id: str) -> MachineIntent | None: ...
    def save_obligations(
        self, project_id: str, obligations: list[DesignObligation]
    ) -> None: ...
    def get_obligations(self, project_id: str) -> list[DesignObligation]: ...
    def save_subsystems(
        self, project_id: str, subsystems: list[SubsystemPlan]
    ) -> None: ...
    def get_subsystems(self, project_id: str) -> list[SubsystemPlan]: ...
    def save_component_roles(
        self, project_id: str, roles: list[ComponentRole]
    ) -> None: ...
    def get_component_roles(self, project_id: str) -> list[ComponentRole]: ...
    def save_selection(
        self, project_id: str, role_id: str, selection: PartSelectionDraft
    ) -> None: ...
    def get_selection(
        self, project_id: str, role_id: str
    ) -> PartSelectionDraft | None: ...
    def delete_selection(self, project_id: str, role_id: str) -> None: ...
    def find_definition(
        self, project_id: str, manufacturer: str | None, part_number: str
    ) -> PartDefinition | None: ...
    def save_definition(self, project_id: str, definition: PartDefinition) -> None: ...
    def get_definitions(self, project_id: str) -> list[PartDefinition]: ...
    def save_instances(
        self, project_id: str, instances: list[ComponentInstance]
    ) -> None: ...
    def get_instances(self, project_id: str) -> list[ComponentInstance]: ...
    def save_bom_line(self, project_id: str, line: BOMLineItem) -> None: ...
    def get_bom_lines(self, project_id: str) -> list[BOMLineItem]: ...
    def save_bom_trace(self, project_id: str, trace: BomLineTrace) -> None: ...
    def get_bom_traces(self, project_id: str) -> list[BomLineTrace]: ...
    def save_fragments(self, project_id: str, fragments: ProjectFragments) -> None: ...
    def get_fragments(self, project_id: str) -> ProjectFragments: ...
    def save_state(self, state: DesignGenerationState) -> None: ...
    def get_state(self, project_id: str) -> DesignGenerationState | None: ...


class InMemoryDesignGenerationRepository:
    """Reference store with optional durable snapshot checkpoints."""

    def __init__(
        self, *, checkpoint: Callable[[dict[str, object]], None] | None = None
    ) -> None:
        self._projects: dict[str, _ProjectRecord] = {}
        self.checkpoint = checkpoint

    def initialize_project(self, project_id: str) -> None:
        self._projects[project_id] = {
            "intent": None,
            "obligations": [],
            "subsystems": [],
            "roles": [],
            "selections": {},
            "definitions": [],
            "instances": [],
            "bom": [],
            "bom_traces": [],
            "fragments": ProjectFragments(),
            "state": None,
        }

    def _project(self, project_id: str) -> _ProjectRecord:
        if project_id not in self._projects:
            self.initialize_project(project_id)
        return self._projects[project_id]

    def save_intent(self, intent: MachineIntent) -> None:
        self._project(intent.project_id)["intent"] = deepcopy(intent)
        self._emit_checkpoint(intent.project_id)

    def get_intent(self, project_id: str) -> MachineIntent | None:
        return deepcopy(self._project(project_id)["intent"])

    def get_intent_by_id(self, intent_id: str) -> MachineIntent | None:
        for project in self._projects.values():
            intent = project.get("intent")
            if isinstance(intent, MachineIntent) and intent.intent_id == intent_id:
                return deepcopy(intent)
        return None

    def save_obligations(
        self, project_id: str, obligations: list[DesignObligation]
    ) -> None:
        self._project(project_id)["obligations"] = deepcopy(obligations)
        self._emit_checkpoint(project_id)

    def get_obligations(self, project_id: str) -> list[DesignObligation]:
        return deepcopy(self._project(project_id)["obligations"])

    def save_subsystems(self, project_id: str, subsystems: list[SubsystemPlan]) -> None:
        self._project(project_id)["subsystems"] = deepcopy(subsystems)
        self._emit_checkpoint(project_id)

    def get_subsystems(self, project_id: str) -> list[SubsystemPlan]:
        return deepcopy(self._project(project_id)["subsystems"])

    def save_component_roles(self, project_id: str, roles: list[ComponentRole]) -> None:
        self._project(project_id)["roles"] = deepcopy(roles)
        self._emit_checkpoint(project_id)

    def get_component_roles(self, project_id: str) -> list[ComponentRole]:
        return deepcopy(self._project(project_id)["roles"])

    def save_selection(
        self, project_id: str, role_id: str, selection: PartSelectionDraft
    ) -> None:
        selections = self._project(project_id)["selections"]
        selections[role_id] = deepcopy(selection)
        self._emit_checkpoint(project_id)

    def get_selection(self, project_id: str, role_id: str) -> PartSelectionDraft | None:
        selections = self._project(project_id)["selections"]
        return deepcopy(selections.get(role_id))

    def delete_selection(self, project_id: str, role_id: str) -> None:
        selections = self._project(project_id)["selections"]
        selections.pop(role_id, None)
        self._emit_checkpoint(project_id)

    def find_definition(
        self,
        project_id: str,
        manufacturer: str | None,
        part_number: str,
    ) -> PartDefinition | None:
        key = ((manufacturer or "").strip().casefold(), part_number.strip().casefold())
        for definition in self.get_definitions(project_id):
            candidate = (
                (definition.manufacturer or "").strip().casefold(),
                definition.part_number.strip().casefold(),
            )
            if candidate == key or (
                candidate[1] == key[1] and (not candidate[0] or not key[0])
            ):
                return definition
        return None

    def save_definition(self, project_id: str, definition: PartDefinition) -> None:
        definitions = self.get_definitions(project_id)
        definitions = [
            item
            for item in definitions
            if item.part_definition_id != definition.part_definition_id
        ]
        definitions.append(deepcopy(definition))
        self._project(project_id)["definitions"] = definitions
        self._emit_checkpoint(project_id)

    def get_definitions(self, project_id: str) -> list[PartDefinition]:
        return deepcopy(self._project(project_id)["definitions"])

    def save_instances(
        self, project_id: str, instances: list[ComponentInstance]
    ) -> None:
        existing = {item.ref_des: item for item in self.get_instances(project_id)}
        existing.update({item.ref_des: deepcopy(item) for item in instances})
        self._project(project_id)["instances"] = list(existing.values())
        self._emit_checkpoint(project_id)

    def get_instances(self, project_id: str) -> list[ComponentInstance]:
        return deepcopy(self._project(project_id)["instances"])

    def save_bom_line(self, project_id: str, line: BOMLineItem) -> None:
        lines = [
            item
            for item in self.get_bom_lines(project_id)
            if item.line_id != line.line_id
        ]
        lines.append(deepcopy(line))
        self._project(project_id)["bom"] = lines
        self._emit_checkpoint(project_id)

    def get_bom_lines(self, project_id: str) -> list[BOMLineItem]:
        return deepcopy(self._project(project_id)["bom"])

    def save_bom_trace(self, project_id: str, trace: BomLineTrace) -> None:
        traces = [
            item
            for item in self.get_bom_traces(project_id)
            if item.line_id != trace.line_id
        ]
        traces.append(deepcopy(trace))
        self._project(project_id)["bom_traces"] = traces
        self._emit_checkpoint(project_id)

    def get_bom_traces(self, project_id: str) -> list[BomLineTrace]:
        return deepcopy(self._project(project_id)["bom_traces"])

    def save_fragments(self, project_id: str, fragments: ProjectFragments) -> None:
        self._project(project_id)["fragments"] = deepcopy(fragments)
        self._emit_checkpoint(project_id)

    def get_fragments(self, project_id: str) -> ProjectFragments:
        return deepcopy(self._project(project_id)["fragments"])

    def save_state(self, state: DesignGenerationState) -> None:
        self._project(state.project_id)["state"] = deepcopy(state)
        self._emit_checkpoint(state.project_id)

    def get_state(self, project_id: str) -> DesignGenerationState | None:
        return deepcopy(self._project(project_id)["state"])

    def snapshot(self, project_id: str) -> dict[str, object]:
        project = self._project(project_id)

        def dump(value: object) -> object:
            if isinstance(value, BaseModel):
                return value.model_dump(mode="json")
            if isinstance(value, list):
                return [dump(item) for item in value]
            if isinstance(value, dict):
                return {str(key): dump(item) for key, item in value.items()}
            return deepcopy(value)

        return {key: dump(value) for key, value in project.items()}

    def restore(self, project_id: str, snapshot: dict[str, object]) -> None:
        def snapshot_list(key: str) -> list[object]:
            value = snapshot.get(key, [])
            return value if isinstance(value, list) else []

        def snapshot_dict(key: str) -> dict[object, object]:
            value = snapshot.get(key, {})
            return value if isinstance(value, dict) else {}

        self._projects[project_id] = {
            "intent": (
                MachineIntent.model_validate(snapshot["intent"])
                if snapshot.get("intent") is not None
                else None
            ),
            "obligations": [
                DesignObligation.model_validate(item)
                for item in snapshot_list("obligations")
            ],
            "subsystems": [
                SubsystemPlan.model_validate(item)
                for item in snapshot_list("subsystems")
            ],
            "roles": [
                ComponentRole.model_validate(item) for item in snapshot_list("roles")
            ],
            "selections": {
                str(key): PartSelectionDraft.model_validate(value)
                for key, value in snapshot_dict("selections").items()
            },
            "definitions": [
                PartDefinition.model_validate(item)
                for item in snapshot_list("definitions")
            ],
            "instances": [
                ComponentInstance.model_validate(item)
                for item in snapshot_list("instances")
            ],
            "bom": [BOMLineItem.model_validate(item) for item in snapshot_list("bom")],
            "bom_traces": [
                BomLineTrace.model_validate(item)
                for item in snapshot_list("bom_traces")
            ],
            "fragments": ProjectFragments.model_validate(snapshot.get("fragments", {})),
            "state": (
                DesignGenerationState.model_validate(snapshot["state"])
                if snapshot.get("state") is not None
                else None
            ),
        }

    def _emit_checkpoint(self, project_id: str) -> None:
        if self.checkpoint is None:
            return
        state = self._project(project_id).get("state")
        run_id = (
            state.run_id
            if isinstance(state, DesignGenerationState)
            else f"intent-first:{project_id}"
        )
        terminal = isinstance(state, DesignGenerationState) and state.is_terminal
        try:
            self.checkpoint(
                {
                    "generation_run_id": run_id,
                    "workflow": "intent_first",
                    "status": state.status.value
                    if isinstance(state, DesignGenerationState)
                    else "running",
                    "record": {
                        "stage_id": "intent_first_state",
                        "status": "succeeded" if terminal else "running",
                        "dependencies": [],
                        "input_artifact_ids": [],
                        "artifact_id": None,
                        "artifact": None,
                        "output": self.snapshot(project_id),
                        "attempt": sum(state.attempt_counts.values())
                        if isinstance(state, DesignGenerationState)
                        else 0,
                        "error": None,
                        "started_at": None,
                        "completed_at": None,
                        "attempt_history": [],
                    },
                }
            )
        except Exception as error:
            if error.__class__.__name__ == "PipelineCancelledError":
                raise
            raise DesignCheckpointError(
                "Could not persist the design-generation checkpoint."
            ) from error
