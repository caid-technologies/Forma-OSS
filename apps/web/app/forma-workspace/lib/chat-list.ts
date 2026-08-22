import type { ChatListItem } from "../sidebar";
import { MAX_CHAT_INDEX_ITEMS, NEW_PROJECT_TITLE } from "../workspace-constants";
import { chatTimestamp } from "./chat-ids";
import { persistableChatMessages } from "./chat-normalize";

export function chatListItemTime(value: string | null | undefined): number {
  const normalizedValue = value?.trim() || "";
  // Project creation timestamps have historically been emitted as UTC without a
  // timezone suffix. Treat them as UTC so they compare correctly with chat
  // updated_at values, which include "Z".
  const timestamp = Date.parse(
    normalizedValue && !/(?:z|[+-]\d{2}:?\d{2})$/i.test(normalizedValue)
      ? `${normalizedValue}Z`
      : normalizedValue
  );
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export function latestChatListItemDate(
  left: string | null | undefined,
  right: string | null | undefined
): string | null {
  return chatListItemTime(right) > chatListItemTime(left) ? right || null : left || right || null;
}

export function sortChatListItems(items: ChatListItem[]): ChatListItem[] {
  return [...items].sort((left, right) => {
    if (Boolean(left.pinned) !== Boolean(right.pinned)) return left.pinned ? -1 : 1;
    return chatListItemTime(right.createdAt) - chatListItemTime(left.createdAt);
  });
}

export function upsertChatListItem(items: ChatListItem[], item: Partial<ChatListItem> & { chatId: string }): ChatListItem[] {
  const existing = items.find((current) => current.chatId === item.chatId);
  const incomingTitle = item.title?.trim() || "";
  const existingTitle = existing?.title?.trim() || "";
  const keepExistingTitle =
    incomingTitle === NEW_PROJECT_TITLE && Boolean(existingTitle) && existingTitle !== NEW_PROJECT_TITLE;
  const incomingProjectId = typeof item.projectId === "string" ? item.projectId : undefined;
  const nextItem: ChatListItem = {
    chatId: item.chatId,
    title: keepExistingTitle ? existingTitle : incomingTitle || existingTitle || NEW_PROJECT_TITLE,
    projectId: incomingProjectId === undefined ? existing?.projectId || "" : incomingProjectId || existing?.projectId || "",
    createdAt: item.createdAt || existing?.createdAt || chatTimestamp(),
    projectCount: Math.max(item.projectCount ?? existing?.projectCount ?? 0, 0),
  };
  return sortChatListItems([nextItem, ...items.filter((current) => current.chatId !== item.chatId)])
    .slice(0, MAX_CHAT_INDEX_ITEMS);
}

export function buildChatListItems(projectHistory: any[], localChatItems: ChatListItem[] = []): ChatListItem[] {
  const groups = new Map<string, { latest: any; projectCount: number }>();

  projectHistory
    .filter((project: any) => project?.project_id)
    .forEach((project: any) => {
      const projectId = String(project.project_id);
      const chatId = String(project.chat_id || projectId).trim();
      if (!chatId) return;

      const existing = groups.get(chatId);
      if (!existing) {
        groups.set(chatId, { latest: project, projectCount: 1 });
        return;
      }

      const currentTime = Date.parse(existing.latest?.created_at || "");
      const nextTime = Date.parse(project.created_at || "");
      groups.set(chatId, {
        latest: Number.isNaN(nextTime) || nextTime <= (Number.isNaN(currentTime) ? 0 : currentTime)
          ? existing.latest
          : project,
        projectCount: existing.projectCount + 1,
      });
    });

  const savedItems = Array.from(groups.entries())
    .map(([chatId, group]) => ({
      chatId,
      title: group.latest?.title || "Untitled chat",
      projectId: String(group.latest?.project_id || ""),
      createdAt: typeof group.latest?.created_at === "string" ? group.latest.created_at : null,
      projectCount: group.projectCount,
    }));

  const merged = new Map<string, ChatListItem>();
  localChatItems.forEach((item) => {
    if (item.chatId) merged.set(item.chatId, item);
  });
  savedItems.forEach((item) => {
    const existing = merged.get(item.chatId);
    merged.set(item.chatId, {
      ...existing,
      ...item,
      createdAt: latestChatListItemDate(existing?.createdAt, item.createdAt),
      projectCount: Math.max(existing?.projectCount || 0, item.projectCount),
    });
  });

  return sortChatListItems(Array.from(merged.values()));
}

export function normalizePrivateChatItems(value: any): ChatListItem[] {
  const chats = Array.isArray(value) ? value : [];
  return chats
    .map((chat: any): ChatListItem | null => {
      const chatId = typeof chat?.chat_id === "string" ? chat.chat_id.trim() : "";
      if (!chatId) return null;
      const messages = persistableChatMessages(Array.isArray(chat?.messages) ? chat.messages : []);
      const projectId = [...messages].reverse().find((message) => message.projectId)?.projectId || "";
      return {
        chatId,
        title: typeof chat.title === "string" && chat.title.trim() ? chat.title.trim() : NEW_PROJECT_TITLE,
        projectId,
        createdAt: typeof chat.updated_at === "string" ? chat.updated_at : typeof chat.created_at === "string" ? chat.created_at : null,
        projectCount: 0,
      };
    })
    .filter((item: ChatListItem | null): item is ChatListItem => Boolean(item));
}

export function normalizeProjectListPage(value: any): { items: any[]; total: number } {
  if (Array.isArray(value)) return { items: value, total: value.length };
  const items = Array.isArray(value?.items) ? value.items : [];
  const parsedTotal = Number(value?.total);
  return {
    items,
    total: Number.isFinite(parsedTotal) ? Math.max(items.length, Math.trunc(parsedTotal)) : items.length,
  };
}

export function mergeChatListItems(primary: ChatListItem[], secondary: ChatListItem[]): ChatListItem[] {
  const merged = new Map<string, ChatListItem>();
  secondary.forEach((item) => {
    if (item.chatId) merged.set(item.chatId, item);
  });
  primary.forEach((item) => {
    if (!item.chatId) return;
    const existing = merged.get(item.chatId);
    merged.set(item.chatId, {
      ...existing,
      ...item,
      createdAt: latestChatListItemDate(existing?.createdAt, item.createdAt),
      projectCount: Math.max(existing?.projectCount || 0, item.projectCount),
    });
  });
  return sortChatListItems(Array.from(merged.values()));
}

export function mergeProjectRecords(primary: any[], secondary: any[]): any[] {
  const merged = new Map<string, any>();
  primary.forEach((project: any) => {
    const projectId = project?.project_id ? String(project.project_id) : "";
    if (projectId) merged.set(projectId, project);
  });
  secondary.forEach((project: any) => {
    const projectId = project?.project_id ? String(project.project_id) : "";
    if (projectId) merged.set(projectId, project);
  });
  return Array.from(merged.values());
}

export function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export function projectRecordsFromChatItems(chatItems: ChatListItem[]): any[] {
  return chatItems
    .filter((item) => item.projectId)
    .map((item) => ({
      project_id: item.projectId,
      chat_id: item.chatId,
      title: item.title || "Untitled project",
      prompt: item.title || "",
      created_at: item.createdAt || chatTimestamp(),
      can_chat: true,
      creator_display: "unknown",
      creator_username: "unknown",
      creator_image_url: null,
      parts_count: 0,
      save_count: 0,
      remix_count: 0,
      saved: false,
    }));
}

export function normalizeProjectHistoryRecord(value: any): any | null {
  if (!value || typeof value !== "object") return null;
  const projectId = typeof value.project_id === "string" ? value.project_id.trim() : "";
  if (!projectId) return null;
  const creatorDisplay =
    typeof value.creator_username === "string" && value.creator_username.trim()
      ? value.creator_username.trim()
      : typeof value.creator_display === "string" && value.creator_display.trim()
        ? value.creator_display.trim()
        : "unknown";
  const creatorImageUrl =
    typeof value.creator_image_url === "string" && value.creator_image_url.trim()
      ? value.creator_image_url.trim()
      : typeof value.creatorImageUrl === "string" && value.creatorImageUrl.trim()
        ? value.creatorImageUrl.trim()
        : null;
  return {
    ...value,
    project_id: projectId,
    chat_id: typeof value.chat_id === "string" ? value.chat_id.trim() : "",
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : "Untitled project",
    prompt: typeof value.prompt === "string" ? value.prompt : "",
    created_at: typeof value.created_at === "string" && value.created_at ? value.created_at : chatTimestamp(),
    visibility: value.visibility === "private" ? "private" : "public",
    can_chat: Boolean(value.can_chat ?? value.canChat),
    creator_display: creatorDisplay,
    creator_username: creatorDisplay,
    creator_image_url: creatorImageUrl,
    parts_count: Math.max(0, Number(value.parts_count || value.partsCount || 0)),
    save_count: Math.max(0, Number(value.save_count || value.saveCount || 0)),
    remix_count: Math.max(0, Number(value.remix_count || value.remixCount || 0)),
    saved: Boolean(value.saved),
  };
}

