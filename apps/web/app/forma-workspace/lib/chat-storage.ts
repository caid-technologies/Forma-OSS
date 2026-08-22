import type { ChatListItem } from "../sidebar";
import type { ChatMessage } from "../types";
import {
  CHAT_INDEX_STORAGE_KEY,
  CHAT_THREAD_STORAGE_PREFIX,
  LEGACY_PROJECT_CHAT_STORAGE_PREFIX,
  MAX_CHAT_INDEX_ITEMS,
  MAX_PROJECT_CHAT_MESSAGES,
  NEW_PROJECT_TITLE,
  PINNED_CHATS_STORAGE_KEY,
} from "../workspace-constants";
import { chatTimestamp } from "./chat-ids";
import { normalizeChatMessage } from "./chat-normalize";

export function chatThreadStorageKey(chatId: string, scope = "local") {
  return scope === "local"
    ? `${CHAT_THREAD_STORAGE_PREFIX}${chatId}`
    : `${CHAT_THREAD_STORAGE_PREFIX}${encodeURIComponent(scope)}.${chatId}`;
}

export function legacyProjectChatStorageKey(projectId: string) {
  return `${LEGACY_PROJECT_CHAT_STORAGE_PREFIX}${projectId}`;
}

export function readStoredChatThread(chatId: string, legacyProjectId?: string | null, scope = "local"): ChatMessage[] {
  if (typeof window === "undefined" || !chatId) return [];
  try {
    const raw = window.localStorage.getItem(chatThreadStorageKey(chatId, scope))
      || (scope === "local" && legacyProjectId ? window.localStorage.getItem(legacyProjectChatStorageKey(legacyProjectId)) : null);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatMessage).filter(Boolean) as ChatMessage[] : [];
  } catch {
    return [];
  }
}

export function writeStoredChatThread(chatId: string, messages: ChatMessage[], scope = "local") {
  if (typeof window === "undefined" || !chatId) return;
  try {
    window.localStorage.setItem(chatThreadStorageKey(chatId, scope), JSON.stringify(messages.slice(-MAX_PROJECT_CHAT_MESSAGES)));
  } catch {
    // Local chat history is best-effort.
  }
}

export function normalizeChatListItem(value: any): ChatListItem | null {
  if (!value || typeof value !== "object") return null;
  const chatId = typeof value.chatId === "string" ? value.chatId.trim() : "";
  if (!chatId) return null;
  return {
    chatId,
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : NEW_PROJECT_TITLE,
    projectId: typeof value.projectId === "string" ? value.projectId : "",
    createdAt: typeof value.createdAt === "string" && value.createdAt ? value.createdAt : chatTimestamp(),
    projectCount: Math.max(0, Number(value.projectCount || 0)),
  };
}

export function chatIndexStorageKey(scope = "local") {
  return scope === "local"
    ? CHAT_INDEX_STORAGE_KEY
    : `${CHAT_INDEX_STORAGE_KEY}.${encodeURIComponent(scope)}`;
}

export function readStoredChatIndex(scope = "local"): ChatListItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(chatIndexStorageKey(scope));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatListItem).filter(Boolean) as ChatListItem[] : [];
  } catch {
    return [];
  }
}

export function writeStoredChatIndex(items: ChatListItem[], scope = "local") {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(chatIndexStorageKey(scope), JSON.stringify(items.slice(0, MAX_CHAT_INDEX_ITEMS)));
  } catch {
    // Local chat index is best-effort.
  }
}

export function pinnedChatsStorageKey(scope = "local") {
  return scope === "local"
    ? PINNED_CHATS_STORAGE_KEY
    : `${PINNED_CHATS_STORAGE_KEY}.${encodeURIComponent(scope)}`;
}

export function readPinnedChatIds(scope = "local"): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(pinnedChatsStorageKey(scope));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((value: unknown): value is string => typeof value === "string" && Boolean(value.trim()))
      : [];
  } catch {
    return [];
  }
}

export function writePinnedChatIds(ids: Iterable<string>, scope = "local") {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(pinnedChatsStorageKey(scope), JSON.stringify(Array.from(ids)));
  } catch {
    // Pinned chat ids are best-effort.
  }
}

export function removeStoredChatThread(chatId: string, scope = "local") {
  if (typeof window === "undefined" || !chatId) return;
  try {
    window.localStorage.removeItem(chatThreadStorageKey(chatId, scope));
  } catch {
    // Local chat history is best-effort.
  }
}
