"""Capability registry and compatibility gates for specialized workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forma_core.workers.contracts import NonEmptyString, WorkerRequest, WorkerResult


WORKER_REGISTRY_VERSION = "1.0"


class WorkerCapability(BaseModel):
    """One callable capability and the payload versions it accepts and returns."""

    model_config = ConfigDict(extra="forbid")

    capability_id: NonEmptyString
    description: NonEmptyString
    supported_input_versions: list[NonEmptyString] = Field(min_length=1)
    supported_output_versions: list[NonEmptyString] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_versions(self) -> "WorkerCapability":
        self.supported_input_versions = list(dict.fromkeys(self.supported_input_versions))
        self.supported_output_versions = list(dict.fromkeys(self.supported_output_versions))
        return self


class WorkerDefinition(BaseModel):
    """Portable declaration registered before a worker can receive jobs."""

    model_config = ConfigDict(extra="forbid")

    worker_id: NonEmptyString
    name: NonEmptyString
    worker_version: NonEmptyString
    capabilities: list[WorkerCapability] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_capabilities(self) -> "WorkerDefinition":
        capability_ids = [capability.capability_id for capability in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("WorkerDefinition capability_id values must be unique.")
        return self

    def capability(self, capability_id: str) -> WorkerCapability | None:
        normalized = capability_id.strip()
        return next(
            (capability for capability in self.capabilities if capability.capability_id == normalized),
            None,
        )


@runtime_checkable
class WorkerDefinitionProvider(Protocol):
    """Minimal declaration surface implemented by concrete workers."""

    def worker_definition(self) -> WorkerDefinition: ...


class WorkerRegistryError(Exception):
    """Structured pre-execution registry failure."""

    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


@dataclass(frozen=True)
class WorkerResolution:
    worker: WorkerDefinition
    capability: WorkerCapability


class WorkerRegistry:
    """In-memory declaration registry used as a gate before job execution."""

    def __init__(
        self,
        workers: list[WorkerDefinition | WorkerDefinitionProvider] | None = None,
    ) -> None:
        self._workers: dict[str, WorkerDefinition] = {}
        for worker in workers or []:
            self.register(worker)

    @staticmethod
    def _definition(worker: WorkerDefinition | WorkerDefinitionProvider) -> WorkerDefinition:
        if isinstance(worker, WorkerDefinition):
            return worker
        if isinstance(worker, WorkerDefinitionProvider):
            return WorkerDefinition.model_validate(worker.worker_definition())
        raise TypeError("Workers must provide a WorkerDefinition.")

    def register(self, worker: WorkerDefinition | WorkerDefinitionProvider) -> WorkerDefinition:
        definition = self._definition(worker)
        if definition.worker_id in self._workers:
            raise WorkerRegistryError(
                "duplicate_worker",
                f"Worker '{definition.worker_id}' is already registered.",
                context={"worker_id": definition.worker_id},
            )
        self._workers[definition.worker_id] = definition
        return definition

    def get(self, worker_id: str) -> WorkerDefinition:
        normalized = worker_id.strip()
        worker = self._workers.get(normalized)
        if worker is None:
            raise WorkerRegistryError(
                "unknown_worker",
                f"Unknown worker '{normalized}'.",
                context={"worker_id": normalized},
            )
        return worker

    def resolve(self, worker_id: str, capability_id: str) -> WorkerResolution:
        worker = self.get(worker_id)
        capability = worker.capability(capability_id)
        if capability is None:
            raise WorkerRegistryError(
                "unknown_worker_capability",
                f"Worker '{worker.worker_id}' does not declare capability '{capability_id.strip()}'.",
                context={
                    "worker_id": worker.worker_id,
                    "capability_id": capability_id.strip(),
                    "available_capabilities": [item.capability_id for item in worker.capabilities],
                },
            )
        return WorkerResolution(worker=worker, capability=capability)

    @staticmethod
    def _require_version(
        *,
        resolution: WorkerResolution,
        requested_version: str,
        supported_versions: list[str],
        direction: str,
    ) -> None:
        if requested_version in supported_versions:
            return
        raise WorkerRegistryError(
            "incompatible_worker_contract_version",
            (
                f"Worker '{resolution.worker.worker_id}' capability "
                f"'{resolution.capability.capability_id}' does not support {direction} version "
                f"'{requested_version}'."
            ),
            context={
                "worker_id": resolution.worker.worker_id,
                "capability_id": resolution.capability.capability_id,
                "direction": direction,
                "requested_version": requested_version,
                "supported_versions": list(supported_versions),
            },
        )

    def validate_request(self, request: WorkerRequest) -> WorkerResolution:
        resolution = self.resolve(request.worker_id, request.capability_id)
        self._require_version(
            resolution=resolution,
            requested_version=request.input_contract_version,
            supported_versions=resolution.capability.supported_input_versions,
            direction="input",
        )
        return resolution

    def validate_result(self, result: WorkerResult) -> WorkerResolution:
        resolution = self.resolve(result.worker_id, result.capability_id)
        self._require_version(
            resolution=resolution,
            requested_version=result.output_contract_version,
            supported_versions=resolution.capability.supported_output_versions,
            direction="output",
        )
        return resolution

    def list_workers(self) -> list[WorkerDefinition]:
        return [self._workers[worker_id] for worker_id in sorted(self._workers)]

    def find_capability(
        self,
        capability_id: str,
        *,
        input_contract_version: str | None = None,
    ) -> list[WorkerResolution]:
        matches: list[WorkerResolution] = []
        for worker in self.list_workers():
            capability = worker.capability(capability_id)
            if capability is None:
                continue
            if input_contract_version and input_contract_version not in capability.supported_input_versions:
                continue
            matches.append(WorkerResolution(worker=worker, capability=capability))
        return matches

    def manifest(self) -> dict[str, Any]:
        return {
            "registry_version": WORKER_REGISTRY_VERSION,
            "workers": [worker.model_dump(mode="json") for worker in self.list_workers()],
        }


__all__ = [
    "WORKER_REGISTRY_VERSION",
    "WorkerCapability",
    "WorkerDefinition",
    "WorkerDefinitionProvider",
    "WorkerRegistry",
    "WorkerRegistryError",
    "WorkerResolution",
]
