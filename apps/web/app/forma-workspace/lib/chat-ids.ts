import { INITIAL_CHAT_TIMESTAMP } from "../workspace-constants";
import type { ChatMessage } from "../types";

export function newChatMessageId() {
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function newBuildChatId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function newFrontendJobId() {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `job_frontend_${suffix.replace(/[^A-Za-z0-9_.:-]/g, "_")}`;
}

export function chatTimestamp() {
  return new Date().toISOString();
}

export function formatChatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function initialChatMessages(timestamp: string = INITIAL_CHAT_TIMESTAMP): ChatMessage[] {
  return [
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "Tell me what you want to build. I can turn it into a project with parts, wiring, mechanical notes, validation, jobs, and optional product images.",
      status: "idle",
      timestamp,
    },
  ];
}
