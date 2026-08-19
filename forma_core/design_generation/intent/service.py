"""Bounded service for converting a prompt into machine intent."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel

from forma_core.design_generation.intent.models import MachineIntent, MachineIntentDraft


class StructuredGenerator(Protocol):
    """Small provider-neutral structured generation boundary."""

    def generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...


class IntentService:
    """Generate a small draft and assign canonical identity in application code."""

    def __init__(
        self,
        generator: StructuredGenerator,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.generator = generator
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def generate(self, *, prompt: str) -> MachineIntentDraft:
        """Generate only the semantic interpretation of a raw user prompt."""

        generation_prompt = f"""
You are the intent-understanding stage for a hardware design system.
Interpret what the requested machine must accomplish. Return only purpose,
users, operating environment, required capabilities, inputs, outputs,
constraints, success conditions, and unresolved questions.

Do not invent or select components. Preserve explicitly mandated implementation
constraints as plain constraint strings, but do not produce component records,
part numbers, pins, wiring, sourcing information, IDs, timestamps, or workflow
metadata.

User request:
{prompt}
""".strip()
        raw = self.generator.generate(generation_prompt, MachineIntentDraft)
        return (
            raw
            if isinstance(raw, MachineIntentDraft)
            else MachineIntentDraft.model_validate(raw)
        )

    def create_intent(
        self,
        *,
        project_id: str,
        source_prompt: str,
        draft: MachineIntentDraft,
    ) -> MachineIntent:
        """Normalize a draft into the application-owned canonical intent."""

        return MachineIntent(
            intent_id=self.id_factory(),
            project_id=project_id,
            source_prompt=source_prompt,
            **draft.model_dump(),
        )


class CallableStructuredGenerator:
    """Adapt an existing ``(prompt, schema)`` callable to the service protocol."""

    def __init__(self, call: Callable[[str, type[BaseModel]], Any]) -> None:
        self.call = call

    def generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        return schema.model_validate(self.call(prompt, schema))
