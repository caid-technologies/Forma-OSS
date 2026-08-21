import assert from "node:assert/strict";
import { test } from "node:test";

import {
  mergeChatListItems,
  sortChatListItems,
  upsertChatListItem,
} from "../app/forma-workspace/lib/chat-list";
import type { ChatListItem } from "../app/forma-workspace/sidebar";

const older: ChatListItem = {
  chatId: "chat-a",
  title: "New project",
  projectId: "",
  createdAt: "2026-01-01T00:00:00.000Z",
  projectCount: 0,
};

const newer: ChatListItem = {
  chatId: "chat-a",
  title: "Plant monitor",
  projectId: "proj-1",
  createdAt: "2026-01-02T00:00:00.000Z",
  projectCount: 1,
};

test("upsert keeps a real title when a later New project placeholder arrives", () => {
  const merged = upsertChatListItem([newer], { ...older, title: "New project" });
  assert.equal(merged[0].title, "Plant monitor");
  assert.equal(merged[0].projectId, "proj-1");
});

test("mergeChatListItems prefers primary fields, the later timestamp, and pinned order", () => {
  const pinned: ChatListItem = {
    chatId: "chat-b",
    title: "Pinned",
    projectId: "proj-2",
    createdAt: "2025-01-01T00:00:00.000Z",
    projectCount: 1,
    pinned: true,
  };
  const merged = mergeChatListItems([older], [newer, pinned]);
  const chatA = merged.find((item) => item.chatId === "chat-a");
  assert.equal(chatA?.title, "New project");
  assert.equal(chatA?.createdAt, "2026-01-02T00:00:00.000Z");
  assert.equal(chatA?.projectCount, 1);
  assert.deepEqual(merged.map((item) => item.chatId), ["chat-b", "chat-a"]);
});
