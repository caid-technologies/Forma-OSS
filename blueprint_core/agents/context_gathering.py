from __future__ import annotations

import json
import re
from typing import Any

from blueprint_core.llm import StructuredLLMProvider
from blueprint_core.workspaces.context.agent import ContextBriefUpdater, _assistant_reply
from blueprint_core.workspaces.context.models import ContextGatheringRequest, ContextTurnDecision
from blueprint_core.workspaces.design_briefs import DesignBrief


class ContextGatheringAgent(ContextBriefUpdater):
    """Routes natural conversation and updates context only when appropriate."""

    def __init__(self, llm_provider: StructuredLLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def route_turn(
        self,
        request: ContextGatheringRequest,
        previous: DesignBrief | None,
        *,
        workflow_state: str | None,
        messages: list[dict[str, Any]],
    ) -> ContextTurnDecision:
        if request.requested_tool is not None:
            return ContextTurnDecision(
                turn_kind="proceed",
                tool_name=request.requested_tool,
                assistant_message="I’ll start from the current project context.",
            )
        if self.llm_provider is not None and self.llm_provider.is_configured:
            return self.llm_provider.generate_structured(
                self._routing_prompt(request, previous, workflow_state=workflow_state, messages=messages),
                ContextTurnDecision,
            )
        return self._fallback_decision(request, previous)

    @staticmethod
    def _routing_prompt(
        request: ContextGatheringRequest,
        previous: DesignBrief | None,
        *,
        workflow_state: str | None,
        messages: list[dict[str, Any]],
    ) -> str:
        recent_messages = [
            {
                "role": str(item.get("role") or ""),
                "content": str(item.get("content") or "")[:1200],
            }
            for item in messages[-12:]
            if isinstance(item, dict)
        ]
        brief = None if previous is None else {
            "summary": previous.summary,
            "requirements": previous.requirements,
            "constraints": previous.constraints,
            "requested_outputs": previous.requested_outputs,
            "unresolved_questions": previous.unresolved_questions,
        }
        return "\n".join([
            "You are Forma's conversational hardware-design intake agent.",
            "Choose exactly one tool by meaning, not keywords or UI mode:",
            "- ask_question: talk with the user, answer questions, or ask at most one useful design question. Set save_context=true only when the newest message contains an actual project requirement or preference.",
            "- build_project: the user asks to start, build, proceed, or skip remaining questions.",
            "- render_project: a completed project exists and the user asks to show or open it.",
            "- iterate_project: a completed project exists and the user requests a change to it.",
            "Set turn_kind only as compatibility metadata: ask_question uses chat, clarification, or context; all other tools use proceed.",
            "Never mention internal fields, unresolved-context bookkeeping, routing, or context collection. Never repeat a question the user just answered or asked you to explain.",
            "If the user asks what they can build, offer a few relevant ideas and invite them to choose or describe a direction.",
            "If the user says they do not know, guide them using outcomes and tradeoffs rather than repeating a technical question.",
            f"Workflow state: {workflow_state or 'not_started'}",
            f"Current DesignBrief: {json.dumps(brief, ensure_ascii=False)}",
            f"Recent conversation: {json.dumps(recent_messages, ensure_ascii=False)}",
            f"Newest user text: {request.text}",
            f"Attachment kinds: {json.dumps([item.kind for item in request.attachments])}",
        ])

    @staticmethod
    def _fallback_decision(
        request: ContextGatheringRequest,
        previous: DesignBrief | None,
    ) -> ContextTurnDecision:
        text = request.text.strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        if re.search(r"\b(?:go|go ahead|continue|start|build it|do it|do it now|proceed|ready)\b", normalized):
            return ContextTurnDecision(
                turn_kind="proceed",
                tool_name="build_project",
                assistant_message="Understood—I’ll hand the current brief to the next agent stage.",
            )
        if re.search(r"\b(?:what do you mean|can you explain|could you explain|why do you ask)\b", normalized):
            return ContextTurnDecision(
                turn_kind="clarification",
                tool_name="ask_question",
                assistant_message=_assistant_reply(text, list(previous.unresolved_questions) if previous else [], previous),
            )
        if normalized in {"hi", "hello", "hey"} or "what can i build" in normalized:
            return ContextTurnDecision(
                turn_kind="chat",
                tool_name="ask_question",
                assistant_message=(
                    "I can help you explore a hardware idea, from a handheld instrument or environmental monitor to a small robot. "
                    "Tell me what you want it to accomplish, or name a direction you’re curious about."
                ),
            )
        return ContextTurnDecision(
            turn_kind="context",
            tool_name="ask_question",
            save_context=True,
            assistant_message=_assistant_reply(text, list(previous.unresolved_questions) if previous else [], previous),
        )
