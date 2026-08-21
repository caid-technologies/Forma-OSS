import assert from "node:assert/strict";
import { test } from "node:test";

import type { ChatMessage } from "../app/forma-workspace/types";
import {
  hydrateRoutedChatMessages,
  mergeFetchedChatMessages,
} from "../app/forma-workspace/lib/chat-normalize";

function message(partial: Partial<ChatMessage> & Pick<ChatMessage, "id" | "content">): ChatMessage {
  return {
    role: "assistant",
    status: "idle",
    timestamp: "2026-01-01T00:00:00.000Z",
    projectId: null,
    pipelineProgress: null,
    imagePreview: null,
    contextProjectId: null,
    workflowState: null,
    contextQuestions: [],
    contextSuggestions: [],
    buildPlanId: null,
    buildJobId: null,
    buildRequiresRequestBoundExecution: false,
    ...partial,
  };
}

test("merge keeps a completed gather result when stored thread still says Thinking", () => {
  const local = message({
    id: "assistant-1",
    content: "I started the design brief. Proceed with defaults?",
    status: "success",
    contextProjectId: "proj-1",
    workflowState: "gathering_context",
    contextQuestions: ["What enclosure material?"],
    contextSuggestions: ["Use safe prototype defaults"],
  });
  const remote = message({
    id: "assistant-1",
    content: "Thinking…",
    status: "loading",
  });

  const merged = mergeFetchedChatMessages([remote], [local]);
  assert.equal(merged[0]?.content, local.content);
  assert.equal(merged[0]?.status, "success");
  assert.equal(merged[0]?.workflowState, "gathering_context");
  assert.equal(merged[0]?.contextProjectId, "proj-1");
  assert.deepEqual(merged[0]?.contextQuestions, ["What enclosure material?"]);
  assert.deepEqual(merged[0]?.contextSuggestions, ["Use safe prototype defaults"]);
});

test("hydrate keeps in-flight messages for the same chat when storage is empty", () => {
  const inMemory = [
    message({ id: "user-1", role: "user", content: "Build a plant monitor" }),
    message({ id: "assistant-1", content: "Thinking…", status: "loading" }),
  ];
  const hydrated = hydrateRoutedChatMessages([], inMemory, { sameChat: true });
  assert.equal(hydrated, inMemory);
});

test("hydrate replaces in-memory messages when opening a different chat", () => {
  const otherChat = [message({ id: "user-a", role: "user", content: "Other chat" })];
  const stored = [message({ id: "user-b", role: "user", content: "Opened chat" })];
  const hydrated = hydrateRoutedChatMessages(stored, otherChat, { sameChat: false });
  assert.equal(hydrated[0]?.id, "user-b");
  assert.equal(hydrateRoutedChatMessages([], otherChat, { sameChat: false }).length, 0);
});

test("hydrate merges when stored ids belong to the in-memory thread even if sameChat is false", () => {
  const local = message({
    id: "assistant-1",
    content: "I started the design brief.",
    status: "success",
    contextProjectId: "proj-1",
    workflowState: "gathering_context",
  });
  const stored = [message({ id: "assistant-1", content: "Thinking…", status: "loading" })];
  const hydrated = hydrateRoutedChatMessages(stored, [local], { sameChat: false });
  assert.equal(hydrated[0]?.content, "I started the design brief.");
  assert.equal(hydrated[0]?.workflowState, "gathering_context");
});
