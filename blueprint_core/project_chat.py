from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, Field

from blueprint_core.iteration import ProjectIterator, compact_hardware_ir_for_iteration
from blueprint_core.llm import LLMRuntimeConfig, StructuredLLMProvider, build_llm_provider, resolve_llm_runtime_config
from blueprint_core.models import HardwareIR, ProjectChatMessage
from blueprint_core.project_objects import normalize_project_namespace


class ProjectChatDecision(BaseModel):
    action: Literal["answer", "iterate"] = Field(description="Answer a question or invoke the project iteration tool.")
    response: str = Field(description="Grounded answer for answer actions, or a short acknowledgement for iterations.")
    instruction: Optional[str] = Field(None, description="Concrete project mutation instruction when action is iterate.")
    namespace: Optional[str] = Field(None, description="Best project namespace for the requested mutation.")


class PrebuildChatDecision(BaseModel):
    action: Literal["converse", "build"] = Field(description="Continue normal conversation or begin a hardware build.")
    response: str = Field(description="Conversational reply, or a short acknowledgement of the build request.")
    build_prompt: Optional[str] = Field(None, description="Clean hardware build prompt when action is build.")


@dataclass(frozen=True)
class ProjectChatResult:
    action: str
    response: str
    project_ir: Optional[HardwareIR] = None
    target_namespace: Optional[str] = None


def build_project_chat_prompt(
    current_ir: HardwareIR,
    message: str,
    *,
    history: Sequence[ProjectChatMessage] = (),
    active_namespace: Optional[str] = None,
) -> str:
    recent_history = [{"role": item.role, "content": item.content} for item in history[-12:]]
    return (
        "You are Blueprint's project chat agent. Decide whether to answer from the active project or invoke its iteration tool.\n"
        "Use action=answer for questions, explanations, summaries, comparisons, and requests to inspect the existing design. "
        "Answer only from the supplied HardwareIR and clearly say when information is absent.\n"
        "Use action=iterate only when the user asks to add, remove, replace, change, fix, redesign, or otherwise mutate the project. "
        "For iterate, write a complete concrete instruction and select the most relevant namespace. "
        "A question such as 'what did you build?' must be answered and must never mutate the project.\n"
        f"Active namespace: {normalize_project_namespace(active_namespace) or 'project.chat'}\n"
        f"Recent chat: {json.dumps(recent_history, sort_keys=True)}\n"
        f"User message: {message.strip()}\n\n"
        "Current HardwareIR:\n"
        f"{json.dumps(compact_hardware_ir_for_iteration(current_ir), indent=2, sort_keys=True)}"
    )


def build_prebuild_conversation_prompt(message: str, *, history: Sequence[ProjectChatMessage] = ()) -> str:
    recent_history = [{"role": item.role, "content": item.content} for item in history[-12:]]
    return (
        "You are Blueprint, a concise and friendly hardware design assistant. Reply naturally to the user. "
        "Do not pretend a project has been created. If appropriate, invite them to describe the hardware they want to build.\n"
        f"Recent chat: {json.dumps(recent_history, sort_keys=True)}\n"
        f"User message: {message.strip()}"
    )


class ProjectChatAgent:
    def __init__(
        self,
        *,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        runtime_config: Optional[LLMRuntimeConfig] = None,
        llm_provider: Optional[StructuredLLMProvider] = None,
    ) -> None:
        self.runtime_config = runtime_config or resolve_llm_runtime_config(provider_name=provider_name, model_name=model_name)
        self.llm_provider = llm_provider or build_llm_provider(runtime_config=self.runtime_config)

    def respond(
        self,
        current_ir: HardwareIR,
        message: str,
        *,
        history: Sequence[ProjectChatMessage] = (),
        active_namespace: Optional[str] = None,
        original_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ProjectChatResult:
        decision = self.llm_provider.generate_structured(
            build_project_chat_prompt(current_ir, message, history=history, active_namespace=active_namespace),
            ProjectChatDecision,
        )
        if decision.action == "answer":
            return ProjectChatResult(action="answer", response=decision.response.strip())

        instruction = (decision.instruction or message).strip()
        target_namespace = normalize_project_namespace(decision.namespace or active_namespace)
        iterator = ProjectIterator(runtime_config=self.runtime_config, llm_provider=self.llm_provider)
        revised = iterator.iterate_project(
            current_ir,
            instruction,
            original_prompt=original_prompt,
            project_id=project_id,
            target_namespace=target_namespace,
        )
        revision = (revised.assembly_metadata or {}).get("revision")
        response = decision.response.strip() or f"Project updated{f' to revision {revision}' if revision else ''}."
        return ProjectChatResult(action="iterate", response=response, project_ir=revised, target_namespace=target_namespace)


class PrebuildChatAgent:
    def __init__(
        self,
        *,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        runtime_config: Optional[LLMRuntimeConfig] = None,
        llm_provider: Optional[StructuredLLMProvider] = None,
    ) -> None:
        self.runtime_config = runtime_config or resolve_llm_runtime_config(provider_name=provider_name, model_name=model_name)
        self.llm_provider = llm_provider or build_llm_provider(runtime_config=self.runtime_config)

    def respond(self, message: str, *, history: Sequence[ProjectChatMessage] = ()) -> PrebuildChatDecision:
        recent_history = [{"role": item.role, "content": item.content} for item in history[-12:]]
        prompt = (
            "You are Blueprint's front-door chat agent. Decide whether the user is asking to design or build hardware.\n"
            "Use action=converse for greetings, thanks, casual conversation, questions about Blueprint, or messages that do not yet describe a hardware project. "
            "Reply naturally and, when helpful, invite the user to describe what they want to build.\n"
            "Use action=build only when the user gives a concrete request to create, design, modify, or plan a physical/electronic product. "
            "For build, preserve the user's requirements in build_prompt. A greeting such as 'hi' is always converse.\n"
            f"Recent chat: {json.dumps(recent_history, sort_keys=True)}\n"
            f"User message: {message.strip()}"
        )
        return self.llm_provider.generate_structured(prompt, PrebuildChatDecision)


__all__ = [
    "PrebuildChatAgent",
    "PrebuildChatDecision",
    "ProjectChatAgent",
    "ProjectChatDecision",
    "ProjectChatResult",
    "build_prebuild_conversation_prompt",
    "build_project_chat_prompt",
]
