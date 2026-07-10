"""Lattice: typed contracts for composable domain agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


SchemaKind = Literal["declared", "induced", "refined"]
RunStatus = Literal["started", "completed", "failed", "blocked"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def schema_from_model(model: type[BaseModel] | None) -> dict[str, Any]:
    if model is None:
        return {}
    return model.model_json_schema()


class LatticeCapability(BaseModel):
    """A discrete capability another agent can discover and call."""

    id: str = Field(..., description="Stable capability identifier, such as fabricator.plan.")
    label: str = Field(..., description="Human-readable capability label.")
    description: str = Field(..., description="What this capability is useful for.")
    inputs: list[str] = Field(default_factory=list, description="Natural-language input fields or concepts.")
    outputs: list[str] = Field(default_factory=list, description="Natural-language output fields or concepts.")
    actions: list[str] = Field(default_factory=list, description="Callable action names exposed by this capability.")

    @field_validator("id", "label", "description")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class LatticeSchemaContract(BaseModel):
    """A schema contract for an agent input/output pair.

    `declared` contracts are authored in code. `induced` and `refined` contracts
    are produced or updated from documents, examples, or run history.
    """

    id: str = Field(..., description="Stable contract identifier.")
    name: str = Field(..., description="Human-readable contract name.")
    version: str = Field("0.1.0", description="Contract version.")
    purpose: str = Field(..., description="Why this schema exists and when to use it.")
    schema_kind: SchemaKind = Field("declared", description="Whether the schema is declared, induced, or refined.")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for accepted input.")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for produced output.")
    induction_prompt: str | None = Field(None, description="Prompt used to induce or update this schema.")
    extraction_prompt: str | None = Field(None, description="Prompt used to extract data through this schema.")
    examples: list[dict[str, Any]] = Field(default_factory=list, description="Representative input/output examples.")
    review_required: bool = Field(True, description="Whether humans should review outputs before execution.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional contract metadata.")

    @classmethod
    def from_models(
        cls,
        *,
        id: str,
        name: str,
        purpose: str,
        input_model: type[BaseModel] | None = None,
        output_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> "LatticeSchemaContract":
        return cls(
            id=id,
            name=name,
            purpose=purpose,
            input_schema=schema_from_model(input_model),
            output_schema=schema_from_model(output_model),
            **kwargs,
        )

    @field_validator("id", "name", "version", "purpose")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class LatticeAgentCard(BaseModel):
    """A portable manifest for a domain agent."""

    card_type: str = Field("lattice.agent_card", description="Manifest type discriminator.")
    agent_id: str = Field(..., description="Stable agent id.")
    namespace: str | None = Field(None, description="Owned namespace, such as product.mech or product.bom.")
    name: str = Field(..., description="Human-readable agent name.")
    version: str = Field("0.1.0", description="Agent card version.")
    domain: str = Field(..., description="Domain this agent specializes in.")
    summary: str = Field(..., description="Short description of the agent's role.")
    capabilities: list[LatticeCapability] = Field(default_factory=list)
    contracts: list[LatticeSchemaContract] = Field(default_factory=list)
    runtime_boundary: str = Field(..., description="What the agent owns versus what the host runtime owns.")
    tools_needed: list[str] = Field(default_factory=list, description="Tool classes this agent may request.")
    handoff_actions: list[str] = Field(default_factory=list, description="Suggested downstream action names.")
    safety_limits: list[str] = Field(default_factory=list, description="Hard limits and safety posture.")
    human_review_triggers: list[str] = Field(default_factory=list, description="Cases that require human review.")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id", "name", "version", "domain", "summary", "runtime_boundary")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    def contract(self, contract_id: str) -> LatticeSchemaContract:
        for contract in self.contracts:
            if contract.id == contract_id:
                return contract
        raise KeyError(f"Unknown Lattice contract: {contract_id}")


class LatticeRunRecord(BaseModel):
    """Auditable record for one domain-agent invocation."""

    record_type: str = Field("lattice.run_record", description="Record type discriminator.")
    run_id: str = Field(default_factory=lambda: f"lat_{uuid4().hex}")
    agent_id: str
    action: str
    contract_id: str | None = None
    mode: str = Field("local", description="Execution mode, such as local, live, or live_fallback.")
    status: RunStatus = "started"
    started_at: str = Field(default_factory=utc_now)
    completed_at: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    handoff_actions: list[dict[str, Any]] = Field(default_factory=list)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def completed(
        cls,
        *,
        agent_card: LatticeAgentCard,
        action: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        contract_id: str | None = None,
        mode: str = "local",
        warnings: list[str] | None = None,
        handoff_actions: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "LatticeRunRecord":
        return cls(
            agent_id=agent_card.agent_id,
            action=action,
            contract_id=contract_id,
            mode=mode,
            status="completed",
            completed_at=utc_now(),
            input_payload=input_payload,
            output_payload=output_payload,
            warnings=warnings or [],
            handoff_actions=handoff_actions or [],
            metadata=metadata or {},
        )


class LatticeRegistry:
    """In-memory registry for domain-agent cards."""

    def __init__(self, cards: list[LatticeAgentCard] | None = None) -> None:
        self._cards: dict[str, LatticeAgentCard] = {}
        for card in cards or []:
            self.register(card)

    def register(self, card: LatticeAgentCard) -> LatticeAgentCard:
        self._cards[card.agent_id] = card
        return card

    def get(self, agent_id: str) -> LatticeAgentCard:
        try:
            return self._cards[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Lattice agent: {agent_id}") from exc

    def list_cards(self) -> list[LatticeAgentCard]:
        return [self._cards[key] for key in sorted(self._cards)]

    def find(
        self,
        *,
        namespace: str | None = None,
        domain: str | None = None,
        capability: str | None = None,
        tool: str | None = None,
    ) -> list[LatticeAgentCard]:
        namespace_text = namespace.lower() if namespace else None
        domain_text = domain.lower() if domain else None
        capability_text = capability.lower() if capability else None
        tool_text = tool.lower() if tool else None
        matches: list[LatticeAgentCard] = []

        for card in self.list_cards():
            if namespace_text and namespace_text not in (card.namespace or "").lower():
                continue
            if domain_text and domain_text not in card.domain.lower():
                continue
            if capability_text and not any(
                capability_text in item.id.lower() or capability_text in item.label.lower()
                for item in card.capabilities
            ):
                continue
            if tool_text and not any(tool_text in item.lower() for item in card.tools_needed):
                continue
            matches.append(card)

        return matches

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "Lattice",
            "lattice_version": "0.1.0",
            "agents": [card.model_dump(mode="json") for card in self.list_cards()],
        }


__all__ = [
    "LatticeAgentCard",
    "LatticeCapability",
    "LatticeRegistry",
    "LatticeRunRecord",
    "LatticeSchemaContract",
    "RunStatus",
    "SchemaKind",
    "schema_from_model",
    "utc_now",
]
