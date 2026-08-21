import type { ChatMessage } from "../types";
import { MAX_PROJECT_CHAT_MESSAGES, NEW_PROJECT_TITLE } from "../workspace-constants";
import { normalizeAgentPipelineProgress } from "./agent-pipeline";
import { chatTimestamp, initialChatMessages, newChatMessageId } from "./chat-ids";
import { normalizeContextSuggestions } from "../../../lib/context-suggestions";

export { chatTimestamp, formatChatTimestamp, initialChatMessages, newBuildChatId, newChatMessageId, newFrontendJobId } from "./chat-ids";

export function validChatStatus(value: any): ChatMessage["status"] {
  return ["idle", "loading", "success", "error", "cancelled"].includes(value) ? value : "idle";
}

export function validChatRole(value: any): ChatMessage["role"] {
  return ["assistant", "user", "system"].includes(value) ? value : "assistant";
}

export function normalizeChatMessage(value: any): ChatMessage | null {
  if (!value || typeof value !== "object" || typeof value.content !== "string") return null;
  const buildExecutionStatus = typeof value.buildExecution?.status === "string"
    ? value.buildExecution.status
    : "";
  const normalizedStatus = buildExecutionStatus === "planned" || buildExecutionStatus === "running"
    ? "loading"
    : validChatStatus(value.status);
  return {
    id: typeof value.id === "string" && value.id ? value.id : newChatMessageId(),
    role: validChatRole(value.role),
    content: value.content,
    status: normalizedStatus,
    timestamp: typeof value.timestamp === "string" && value.timestamp ? value.timestamp : chatTimestamp(),
    projectId: typeof value.projectId === "string" ? value.projectId : null,
    pipelineProgress: normalizeAgentPipelineProgress(value.pipelineProgress),
    imagePreview: typeof value.imagePreview === "string" ? value.imagePreview : null,
    contextProjectId: typeof value.contextProjectId === "string"
      ? value.contextProjectId
      : typeof value.context_project_id === "string"
        ? value.context_project_id
        : null,
    workflowState: typeof value.workflowState === "string"
      ? value.workflowState
      : typeof value.workflow_state === "string"
        ? value.workflow_state
        : null,
    contextQuestions: (Array.isArray(value.contextQuestions) ? value.contextQuestions : value.questions)
      ?.filter((question: unknown): question is string => typeof question === "string" && Boolean(question.trim()))
      .map((question: string) => question.trim()) || [],
    contextSuggestions: normalizeContextSuggestions(value.contextSuggestions ?? value.suggestions),
    buildPlanId: typeof value.buildPlanId === "string"
      ? value.buildPlanId
      : typeof value.build_plan_id === "string"
        ? value.build_plan_id
        : typeof value.buildExecution?.plan_id === "string"
          ? value.buildExecution.plan_id
          : null,
    buildJobId: typeof value.buildJobId === "string"
      ? value.buildJobId
      : typeof value.build_job_id === "string"
        ? value.build_job_id
        : typeof value.buildExecution?.job_id === "string"
          ? value.buildExecution.job_id
          : null,
    buildRequiresRequestBoundExecution: Boolean(
      value.buildRequiresRequestBoundExecution
      ?? value.build_request_bound_execution
      ?? value.buildExecution?.request_bound_execution
      ?? value.build_execution?.request_bound_execution
      ?? false
    ),
  };
}

export function chatHasStarted(messages: ChatMessage[]) {
  return messages.some((message) => message.role === "user" || Boolean(message.projectId));
}

export function chatTitleFromMessages(messages: ChatMessage[], fallback = NEW_PROJECT_TITLE) {
  const firstUserMessage = messages.find((message) => message.role === "user" && message.content.trim());
  const title = firstUserMessage?.content.trim().replace(/\s+/g, " ");
  if (!title) return fallback;
  return title.length > 80 ? `${title.slice(0, 77)}...` : title;
}

export function persistableChatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .map(normalizeChatMessage)
    .filter((message: ChatMessage | null): message is ChatMessage => Boolean(message))
    .slice(-MAX_PROJECT_CHAT_MESSAGES);
}

export function mergeFetchedChatMessages(remoteMessages: ChatMessage[], localMessages: ChatMessage[]): ChatMessage[] {
  const localById = new Map(localMessages.map((message) => [message.id, message]));
  const seen = new Set<string>();
  const merged: ChatMessage[] = [];

  remoteMessages.forEach((remote) => {
    if (seen.has(remote.id)) return;
    seen.add(remote.id);
    const local = localById.get(remote.id);
    if (!local) {
      merged.push(remote);
      return;
    }

    const localIsTerminal = ["success", "error", "cancelled"].includes(local.status || "");
    const remoteRegressed = localIsTerminal && remote.status === "loading";
    merged.push({
      ...local,
      ...remote,
      content: remoteRegressed ? local.content : remote.content,
      status: remoteRegressed ? local.status : remote.status,
      timestamp: remoteRegressed ? local.timestamp : remote.timestamp,
      projectId: remote.projectId || local.projectId || null,
      pipelineProgress: remote.pipelineProgress || local.pipelineProgress || null,
      contextProjectId: remote.contextProjectId || local.contextProjectId || null,
      workflowState: remoteRegressed
        ? (local.workflowState || remote.workflowState || null)
        : (remote.workflowState || local.workflowState || null),
      contextQuestions: remoteRegressed && local.contextQuestions?.length
        ? local.contextQuestions
        : (remote.contextQuestions?.length ? remote.contextQuestions : local.contextQuestions || []),
      contextSuggestions: remoteRegressed && local.contextSuggestions?.length
        ? local.contextSuggestions
        : (remote.contextSuggestions?.length ? remote.contextSuggestions : local.contextSuggestions || []),
      buildPlanId: remote.buildPlanId || local.buildPlanId || null,
      buildJobId: remote.buildJobId || local.buildJobId || null,
      buildRequiresRequestBoundExecution: Boolean(
        remote.buildRequiresRequestBoundExecution || local.buildRequiresRequestBoundExecution
      ),
      imagePreview: remote.imagePreview || local.imagePreview || null,
    });
  });

  localMessages.forEach((local) => {
    if (!seen.has(local.id)) merged.push(local);
  });
  return merged.slice(-MAX_PROJECT_CHAT_MESSAGES);
}

export function hydrateRoutedChatMessages(
  storedMessages: ChatMessage[],
  inMemoryMessages: ChatMessage[],
  options: { sameChat: boolean },
): ChatMessage[] {
  const overlapping = storedMessages.some((stored) =>
    inMemoryMessages.some((message) => message.id === stored.id)
  );
  const keepInMemory = options.sameChat || overlapping;
  if (!keepInMemory) return storedMessages;
  if (!storedMessages.length) return inMemoryMessages;
  return mergeFetchedChatMessages(storedMessages, inMemoryMessages);
}

export function chatIsWaiting(messages: ChatMessage[]) {
  return messages.some((message) => message.status === "loading");
}

export function chatMessageIdentityKey(messages: ChatMessage[]) {
  return messages.map((message) => message.id).join("|");
}

export function initialProjectChatMessages(projectId: string, title: string, sourcePrompt?: string | null): ChatMessage[] {
  const messages: ChatMessage[] = [];
  if (sourcePrompt?.trim()) {
    messages.push({
      id: newChatMessageId(),
      role: "user",
      content: sourcePrompt.trim(),
      status: "idle",
      timestamp: chatTimestamp(),
      projectId,
    });
  }
  messages.push({
    id: newChatMessageId(),
    role: "assistant",
    content: `${title || "Project"} is the active project for this chat.`,
    status: "success",
    timestamp: chatTimestamp(),
    projectId,
  });
  return messages;
}

export function missingProjectNotice(projectId: string) {
  return `This chat pointed at project ${projectId}, but that project is no longer available in the project database. The chat history is still here; generate again to create a new project.`;
}

export function messagesWithoutMissingProject(messages: ChatMessage[], projectId: string): ChatMessage[] {
  const notice = missingProjectNotice(projectId);
  const normalizedMessages = messages.map((message) =>
    message.projectId === projectId ? { ...message, projectId: null } : message
  );
  if (normalizedMessages.some((message) => message.role === "assistant" && message.content === notice)) {
    return normalizedMessages;
  }
  const noticeMessage: ChatMessage = {
    id: newChatMessageId(),
    role: "assistant",
    content: notice,
    status: "error",
    timestamp: chatTimestamp(),
    projectId: null,
  };
  return [...normalizedMessages, noticeMessage].slice(-MAX_PROJECT_CHAT_MESSAGES);
}
