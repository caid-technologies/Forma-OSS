"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Eye, Layers, Maximize2, Minimize2, MessageSquare, RefreshCw, Square } from "lucide-react";

import CopyButton from "../../components/copy-button";
import { formatChatTimestamp } from "./lib/chat-ids";
import { workspaceNamespaceForTab, workspaceTabs } from "./lib/workspace-routes";
import { AgentPipelineProgressView } from "./pipeline-progress-view";
import { EditableWorkspaceTitle, MobileSidebarButton } from "./sidebar";
import type { ChatMessage } from "./types";
import useChatAutoScroll from "./use-chat-auto-scroll";
import useChromeHeaderScroll from "./use-chrome-header-scroll";

export function ProjectDetailWorkspace({
  onOpenSidebar,
  projectId,
  projectTitle,
  owned,
  onRenameTitle,
  namespaceTabs,
  activeNamespace,
  onNamespaceChange,
  projectContent,
}: {
  onOpenSidebar: () => void;
  projectId: string | null;
  projectTitle: string;
  owned: boolean;
  onRenameTitle?: (title: string) => void;
  namespaceTabs: typeof workspaceTabs;
  activeNamespace: string;
  onNamespaceChange: (value: string) => void;
  projectContent: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-[var(--forma-page)]">
      <header className="workspace-chrome-header flex min-h-14 min-w-0 items-center gap-3 overflow-hidden px-3 pb-5 pt-2 sm:px-4">
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-[rgb(var(--forma-green-rgb)/0.12)] px-2 py-0.5 text-[10px] font-medium text-[rgb(var(--forma-green-rgb))]">
              <Eye className="h-3 w-3" />
              {owned ? "Your project" : "Public project"}
            </span>
            <EditableWorkspaceTitle
              value={projectTitle}
              canEdit={owned && Boolean(onRenameTitle)}
              label="Project title"
              onCommit={(title) => onRenameTitle?.(title)}
            />
          </div>
        </div>
      </header>

      <section className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--forma-page)]" aria-label="Project workspace">
        <ProjectWorkspacePanel
          projectId={projectId}
          namespaceTabs={namespaceTabs}
          activeNamespace={activeNamespace}
          onNamespaceChange={onNamespaceChange}
        >
          {projectContent}
        </ProjectWorkspacePanel>
      </section>
    </div>
  );
}

export function ChatWorkspace({
  onOpenSidebar,
  projectId,
  chatId,
  projectTitle,
  onRenameTitle,
  messages,
  input,
  setInput,
  onSubmit,
  isLoading,
  canStop,
  onStop,
  canChat,
  namespaceTabs,
  activeNamespace,
  activeNamespaceLabel,
  activeNamespaceName,
  onNamespaceChange,
  projectContent,
}: {
  onOpenSidebar: () => void;
  projectId: string | null;
  chatId: string | null;
  projectTitle: string;
  onRenameTitle?: (title: string) => void;
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
  isLoading: boolean;
  canStop: boolean;
  onStop: () => void;
  canChat: boolean;
  namespaceTabs: typeof workspaceTabs;
  activeNamespace: string;
  activeNamespaceLabel: string;
  activeNamespaceName: string;
  onNamespaceChange: (value: string) => void;
  projectContent: React.ReactNode;
}) {
  const { containerRef, endRef, handleScroll } = useChatAutoScroll(chatId || projectId || "project-chat", messages);
  const { headerAway, updateFromContainer } = useChromeHeaderScroll(chatId || projectId || "project-chat");

  const onChatScroll = () => {
    handleScroll();
    updateFromContainer(containerRef.current);
  };

  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-col bg-[var(--forma-page)]">
      <header className={`workspace-chrome-header absolute inset-x-0 top-0 z-20 flex min-h-14 min-w-0 items-center gap-3 px-3 pb-5 pt-2 sm:px-4 ${headerAway ? "is-away" : ""}`}>
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-[rgb(var(--forma-green-rgb)/0.12)] px-2 py-0.5 text-[10px] font-medium text-[rgb(var(--forma-green-rgb))]">
              {canChat ? <MessageSquare className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              {canChat ? "Project chat" : "Read-only project"}
            </span>
            <EditableWorkspaceTitle
              value={projectTitle}
              canEdit={canChat && Boolean(onRenameTitle)}
              label="Project chat title"
              onCommit={(title) => onRenameTitle?.(title)}
            />
          </div>
        </div>
      </header>

      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
        {canChat && (
          <div className="flex h-full min-h-0 min-w-0 flex-col">
            <div
              ref={containerRef}
              onScroll={onChatScroll}
              className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 pb-5 pt-16 sm:px-5 sm:pb-6 sm:pt-16"
            >
              <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-3">
                {messages.length ? (
                  messages.map((message) => {
                    const isUser = message.role === "user";
                    const isSystem = message.role === "system";
                    return (
                      <div key={message.id} className={`mx-auto flex w-full min-w-0 max-w-3xl ${isUser ? "justify-end" : "justify-start"}`}>
                        <div
                          className={`min-w-0 max-w-[92%] overflow-hidden rounded-xl border px-4 py-3 ${
                            isUser
                              ? "border-emerald-500/20 bg-emerald-500/10 text-zinc-100"
                              : message.status === "error"
                                ? "border-rose-400/30 bg-rose-950/25 text-rose-100"
                                : message.status === "cancelled"
                                  ? "border-amber-300/30 bg-amber-950/20 text-amber-50"
                                : isSystem
                                  ? "border-white/5 bg-black/25 text-zinc-400"
                                  : "border-white/5 bg-[#181b22] text-zinc-200"
                          }`}
                        >
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] font-medium text-zinc-500">
                            <span>{isUser ? "You" : isSystem ? "Context" : "Forma"}</span>
                            <span className="text-zinc-700">·</span>
                            <span suppressHydrationWarning>{formatChatTimestamp(message.timestamp)}</span>
                            {message.status === "loading" && <RefreshCw className="h-3 w-3 animate-spin text-emerald-400" />}
                            {message.status === "cancelled" && <Square className="h-3 w-3 fill-current text-amber-300" />}
                            <CopyButton
                              value={message.content}
                              label={isUser ? "Copy your message" : isSystem ? "Copy context message" : "Copy Forma's message"}
                              className="ml-auto"
                            />
                          </div>
                          <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                          {!message.projectId && (
                            <AgentPipelineProgressView progress={message.pipelineProgress} status={message.status} compact />
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="mx-auto w-full max-w-3xl rounded-xl border border-white/5 bg-[#181b22] p-5 text-sm leading-6 text-zinc-500">
                    This chat has no project messages yet.
                  </div>
                )}
                <div ref={endRef} />
                <ChatProjectArtifact
                  projectId={projectId}
                  projectTitle={projectTitle}
                  canEdit={canChat && Boolean(onRenameTitle)}
                  onRenameTitle={onRenameTitle}
                  namespaceTabs={namespaceTabs}
                  activeNamespace={activeNamespace}
                  onNamespaceChange={onNamespaceChange}
                  projectContent={projectContent}
                />
              </div>
            </div>

            <form onSubmit={onSubmit} className="shrink-0 border-t border-white/5 bg-[#0f1117]/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:p-4">
              <div className="mx-auto max-w-3xl">
                <div className="w-full rounded-2xl border border-white/5 bg-[#181b22] p-3 shadow-lg transition-all focus-within:border-emerald-500/50 focus-within:ring-1 focus-within:ring-emerald-500/20">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        if (isLoading) return;
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder={`Describe a change to ${activeNamespaceLabel.toLowerCase()}...`}
                    className="min-h-[72px] w-full resize-none border-none bg-transparent text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <div className="mt-1 flex items-center justify-end gap-1.5">
                    {!canStop && !isLoading && Boolean(input.trim()) && (
                      <span className="prompt-composer-enter-hint hidden sm:inline" aria-hidden="true">
                        Enter
                      </span>
                    )}
                    <button
                      type={canStop ? "button" : "submit"}
                      onClick={canStop ? onStop : undefined}
                      disabled={!canStop && (isLoading || !projectId || !input.trim())}
                      className={`prompt-composer-send inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed ${
                        !canStop && !isLoading && input.trim() ? "is-ready" : ""
                      }`}
                      aria-label={canStop ? "Stop project update" : "Apply change to project, or press Enter"}
                      title={canStop ? "Stop project update" : `Apply change to ${activeNamespaceName} · Enter`}
                    >
                      {canStop ? <Square className="h-3.5 w-3.5 fill-current" /> : isLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        )}

        {!canChat && (
          <section className="absolute inset-0 min-h-0 min-w-0 overflow-hidden bg-[var(--forma-page)] pt-14" aria-label="Project workspace">
            <ProjectWorkspacePanel
              projectId={projectId}
              namespaceTabs={namespaceTabs}
              activeNamespace={activeNamespace}
              onNamespaceChange={onNamespaceChange}
            >
              {projectContent}
            </ProjectWorkspacePanel>
          </section>
        )}
      </div>
    </div>
  );
}

export function scrollableVerticalParent(node: HTMLElement | null) {
  let current = node?.parentElement || null;
  while (current) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (/(auto|scroll)/.test(overflowY) && current.scrollHeight > current.clientHeight) return current;
    current = current.parentElement;
  }
  return null;
}

export function ChatProjectArtifact({
  projectId,
  projectTitle,
  canEdit = false,
  onRenameTitle,
  namespaceTabs,
  activeNamespace,
  onNamespaceChange,
  projectContent,
}: {
  projectId: string | null;
  projectTitle: string;
  canEdit?: boolean;
  onRenameTitle?: (title: string) => void;
  namespaceTabs: typeof workspaceTabs;
  activeNamespace: string;
  onNamespaceChange: (namespaceId: string) => void;
  projectContent: React.ReactNode;
}) {
  const [fullScreen, setFullScreen] = useState(false);
  const artifactRef = useRef<HTMLElement>(null);
  const chatScrollSnapshotRef = useRef<{
    element: HTMLElement | null;
    top: number;
    left: number;
    windowX: number;
    windowY: number;
  } | null>(null);
  const restoreChatScrollRef = useRef(false);

  const enterFullScreen = () => {
    const element = scrollableVerticalParent(artifactRef.current);
    chatScrollSnapshotRef.current = {
      element,
      top: element?.scrollTop || 0,
      left: element?.scrollLeft || 0,
      windowX: window.scrollX,
      windowY: window.scrollY,
    };
    setFullScreen(true);
  };

  const exitFullScreen = () => {
    restoreChatScrollRef.current = true;
    setFullScreen(false);
  };

  useLayoutEffect(() => {
    if (fullScreen || !restoreChatScrollRef.current) return;
    restoreChatScrollRef.current = false;
    const snapshot = chatScrollSnapshotRef.current;
    if (!snapshot) return;

    const restoreScroll = () => {
      if (snapshot.element?.isConnected) {
        snapshot.element.scrollTo({ top: snapshot.top, left: snapshot.left, behavior: "auto" });
      } else {
        window.scrollTo({ top: snapshot.windowY, left: snapshot.windowX, behavior: "auto" });
      }
    };

    restoreScroll();
    const frameId = window.requestAnimationFrame(restoreScroll);
    return () => window.cancelAnimationFrame(frameId);
  }, [fullScreen]);

  useEffect(() => {
    if (!fullScreen) return;
    const previousOverflow = document.body.style.overflow;
    const exitOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        restoreChatScrollRef.current = true;
        setFullScreen(false);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", exitOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", exitOnEscape);
    };
  }, [fullScreen]);

  return (
    <section
      ref={artifactRef}
      className={`min-w-0 overflow-hidden bg-[var(--forma-page)] ${
        fullScreen
          ? "fixed inset-0 z-[80] flex h-[100dvh] w-screen flex-col"
          : "mx-auto mt-3 w-full max-w-6xl rounded-xl border border-[var(--forma-border)]"
      }`}
      aria-labelledby="chat-project-title"
    >
      <header className="flex min-h-[56px] min-w-0 shrink-0 items-center justify-between gap-3 border-b border-[var(--forma-border)] bg-[var(--forma-surface)] px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 shrink-0 text-[rgb(var(--forma-green-rgb))]" />
            <h3 id="chat-project-title" className="truncate text-[10px] font-medium text-[var(--forma-text-muted)]">
              Project
            </h3>
          </div>
          <EditableWorkspaceTitle
            value={projectTitle}
            canEdit={canEdit && Boolean(onRenameTitle)}
            label="Project title"
            element="div"
            className="mt-0.5 truncate text-xs font-semibold text-[var(--forma-text-strong)]"
            onCommit={(title) => onRenameTitle?.(title)}
          />
        </div>
        <div className="flex min-w-0 items-center justify-end">
          <button
            type="button"
            onClick={fullScreen ? exitFullScreen : enterFullScreen}
            className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-[var(--forma-border)] px-2.5 text-xs font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-surface-muted)] hover:text-[var(--forma-text-strong)] sm:px-3"
            aria-pressed={fullScreen}
            aria-label={fullScreen ? "Exit project full screen" : "View project full screen"}
            title={fullScreen ? "Exit full screen (Esc)" : "Full screen"}
          >
            {fullScreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            <span className="hidden md:inline">{fullScreen ? "Exit full screen" : "Full screen"}</span>
          </button>
        </div>
      </header>

      <div className={fullScreen ? "min-h-0 min-w-0 flex-1 overflow-hidden" : "h-[70dvh] min-h-[540px] max-h-[820px] min-w-0 overflow-hidden"}>
        <ProjectWorkspacePanel
          projectId={projectId}
          namespaceTabs={namespaceTabs}
          activeNamespace={activeNamespace}
          onNamespaceChange={onNamespaceChange}
        >
          {projectContent}
        </ProjectWorkspacePanel>
      </div>
    </section>
  );
}

export function ProjectWorkspacePanel({
  projectId,
  namespaceTabs,
  activeNamespace,
  onNamespaceChange,
  children,
}: {
  projectId?: string | null;
  namespaceTabs: typeof workspaceTabs;
  activeNamespace: string;
  onNamespaceChange: (value: string) => void;
  children: React.ReactNode;
}) {
  const namespaceName = workspaceNamespaceForTab(activeNamespace);
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <nav
        className="flex min-h-[44px] min-w-0 shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--forma-border)] bg-[var(--forma-surface)] px-2"
        aria-label="Project workspace"
      >
        {namespaceTabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeNamespace === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onNamespaceChange(tab.id)}
              className={`inline-flex h-8 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 text-xs font-medium transition-colors ${
                active
                  ? "bg-[rgb(var(--forma-green-rgb)/0.12)] text-[rgb(var(--forma-green-rgb))]"
                  : "text-[var(--forma-text-muted)] hover:bg-[var(--forma-surface-muted)] hover:text-[var(--forma-text-strong)]"
              }`}
              aria-pressed={active}
              title={`${tab.label} / ${workspaceNamespaceForTab(tab.id)}`}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
              <span className={active ? "inline" : "hidden sm:inline"}>{tab.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</div>
      <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 py-1.5 font-mono text-[9px] text-[var(--forma-text-muted)]">
        {projectId && (
          <span className="max-w-[min(100%,14rem)] truncate" title={projectId}>
            {projectId}
          </span>
        )}
        {projectId && <span aria-hidden="true">·</span>}
        <span className="max-w-48 truncate" title={namespaceName}>
          {namespaceName}
        </span>
      </div>
    </div>
  );
}
