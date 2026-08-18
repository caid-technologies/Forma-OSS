"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Database,
  Handshake,
  History,
  KeyRound,
  Layers,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Settings,
  Terminal,
  X,
} from "lucide-react";

import CaidLogo from "../../components/caid-logo";
import { FormaUserButton, useFormaAuth } from "../../lib/forma-auth";
import { type WorkspaceStatusPresentation } from "../../lib/connection-status";

export type ChatListItem = {
  chatId: string;
  title: string;
  projectId: string;
  createdAt: string | null;
  projectCount: number;
};

export function EditableWorkspaceTitle({
  value,
  canEdit,
  onCommit,
  label,
  className = "truncate text-sm font-semibold tracking-tight text-zinc-100",
  element = "h2",
}: {
  value: string;
  canEdit: boolean;
  onCommit: (nextTitle: string) => void;
  label: string;
  className?: string;
  element?: "h2" | "h3" | "div";
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const TitleTag = element;

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [editing, value]);

  if (!canEdit) {
    return <TitleTag className={className}>{value}</TitleTag>;
  }

  if (editing) {
    return (
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft.trim() || value.trim() || "Untitled Hardware Project";
          setEditing(false);
          if (next !== value) onCommit(next);
          else setDraft(value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.blur();
          }
          if (event.key === "Escape") {
            event.preventDefault();
            setDraft(value);
            setEditing(false);
          }
        }}
        autoFocus
        aria-label={label}
        className={`min-w-0 flex-1 bg-transparent ${className} outline-none`}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title={`Rename ${label.toLowerCase()}`}
      aria-label={`Rename ${label.toLowerCase()}`}
      className={`min-w-0 flex-1 truncate text-left ${className} hover:text-white`}
    >
      {value}
    </button>
  );
}

function formatSidebarDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function ApiConnectionStatus({ status }: { status: WorkspaceStatusPresentation }) {
  return (
    <span
      className={`status-badge ${status.tone === "error" ? "status-badge-error" : "status-badge-ok"} ${
        status.pulse ? "status-badge-pulse" : "status-badge-idle"
      }`}
      role="status"
      aria-live="polite"
      aria-label={status.label}
      title={status.label}
    >
      <span className="status-badge-ping" aria-hidden="true" />
      <span className="status-badge-dot" aria-hidden="true" />
    </span>
  );
}

export function WorkspaceStatusCorner({ status }: { status: WorkspaceStatusPresentation }) {
  return (
    <div className="pointer-events-none absolute right-4 top-4 z-40 flex items-center gap-2 overflow-visible">
      <span className="workspace-beta-badge">
        BETA
      </span>
      <span className="pointer-events-auto">
        <ApiConnectionStatus status={status} />
      </span>
    </div>
  );
}

export function MobileWorkspaceBar({
  onOpenSidebar,
  authRequired,
}: {
  onOpenSidebar: () => void;
  authRequired: boolean;
}) {
  return (
    <header className="workspace-chrome-header fixed inset-x-0 top-0 z-30 flex min-h-14 shrink-0 items-center justify-between gap-3 px-3 pb-5 pt-2 pr-16 md:hidden">
      <MobileSidebarButton onClick={onOpenSidebar} />
      <AuthStatusControl authRequired={authRequired} compact />
    </header>
  );
}

export function AuthStatusControl({
  authRequired,
  compact = false,
}: {
  authRequired: boolean;
  compact?: boolean;
}) {
  const { isLoaded, isSignedIn, openSignIn } = useFormaAuth();
  if (!authRequired) return null;
  if (isSignedIn) return <FormaUserButton afterSignOutUrl="/" />;

  return (
    <button
      type="button"
      disabled={!isLoaded}
      onClick={() => openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" })}
      className={`inline-flex shrink-0 items-center justify-center rounded-lg border border-white/10 font-medium text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100 disabled:cursor-wait disabled:text-zinc-600 disabled:hover:bg-transparent ${
        compact ? "h-8 w-8" : "h-8 gap-1.5 px-2.5 text-xs"
      }`}
      aria-label={isLoaded ? "Sign in" : "Checking sign-in status"}
      title={isLoaded ? "Sign in" : "Checking sign-in status"}
    >
      <KeyRound className={compact ? "h-4 w-4" : "h-3.5 w-3.5"} />
      {!compact && <span>Sign in</span>}
    </button>
  );
}

export function MobileSidebarButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100 md:hidden"
      aria-label="Open sidebar"
      title="Open sidebar"
    >
      <Menu className="h-4 w-4" />
    </button>
  );
}

export function MobileSidebarDrawer({
  open,
  onClose,
  collapsed,
  onToggle,
  onHome,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  onRenameChat,
  waitingChatIds,
  chatsLoading,
  showJobs,
  jobsPending,
  showDeveloperTools,
  authRequired,
}: {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggle: () => void;
  onHome: () => void;
  chats: ChatListItem[];
  activeChatId: string | null;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  onRenameChat?: (item: ChatListItem, title: string) => void;
  waitingChatIds: Set<string>;
  chatsLoading?: boolean;
  showJobs: boolean;
  jobsPending?: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Sidebar">
      <button
        type="button"
        className="absolute inset-0 h-full w-full bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close sidebar"
      />
      <div className="relative h-full">
        <ChatSidebar
          mode="drawer"
          collapsed={collapsed}
          onToggle={onToggle}
          onClose={onClose}
          onNavigate={onClose}
          onHome={onHome}
          chats={chats}
          activeChatId={activeChatId}
          onNewChat={onNewChat}
          newChatDisabled={newChatDisabled}
          onOpenChat={onOpenChat}
          onRenameChat={onRenameChat}
          waitingChatIds={waitingChatIds}
          chatsLoading={chatsLoading}
          showJobs={showJobs}
          jobsPending={jobsPending}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
        />
      </div>
    </div>
  );
}

function SidebarSectionLabel({ compact, children }: { compact: boolean; children: React.ReactNode }) {
  if (compact) return null;
  return <div className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{children}</div>;
}

function SidebarAccountDock({ compact }: { compact: boolean }) {
  const { isSignedIn } = useFormaAuth();
  return (
    <div className={`mt-3 flex items-center gap-2.5 border-t border-white/5 pt-3 ${compact ? "justify-center" : "px-3"}`}>
      <AuthStatusControl authRequired compact={compact || isSignedIn} />
      {!compact && isSignedIn && <span className="truncate text-xs font-medium text-zinc-500">Account</span>}
    </div>
  );
}

function SidebarNavLink({
  href,
  icon: Icon,
  label,
  compact,
  onNavigate,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  compact: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800/40 hover:text-zinc-200 ${
        compact ? "justify-center px-0" : ""
      }`}
      title={label}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!compact && <span className="truncate">{label}</span>}
    </Link>
  );
}

export function ChatSidebar({
  collapsed,
  onToggle,
  onClose,
  onNavigate,
  onHome,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  onRenameChat,
  waitingChatIds,
  chatsLoading = false,
  showJobs,
  jobsPending = false,
  showDeveloperTools,
  authRequired,
  mode = "desktop",
}: {
  collapsed: boolean;
  onToggle: () => void;
  onClose?: () => void;
  onNavigate?: () => void;
  onHome: () => void;
  chats: ChatListItem[];
  activeChatId: string | null;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  onRenameChat?: (item: ChatListItem, title: string) => void;
  waitingChatIds: Set<string>;
  chatsLoading?: boolean;
  showJobs: boolean;
  jobsPending?: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  mode?: "desktop" | "drawer";
}) {
  const isDrawer = mode === "drawer";
  const compact = !isDrawer && collapsed;
  const [renamingChatId, setRenamingChatId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  const commitSidebarRename = (chat: ChatListItem) => {
    const nextTitle = renameDraft.trim() || chat.title;
    setRenamingChatId(null);
    if (nextTitle !== chat.title) onRenameChat?.(chat, nextTitle);
  };

  return (
    <aside
      className={
        isDrawer
          ? "flex h-full min-h-0 w-[min(320px,calc(100vw-2rem))] flex-col overflow-hidden rounded-r-2xl border-r border-white/5 bg-[#181b22] text-zinc-100 shadow-2xl shadow-black/50"
          : "hidden h-full min-h-0 flex-col border-r border-white/5 bg-[#181b22] text-zinc-100 md:flex"
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className={`flex shrink-0 items-center ${compact ? "h-auto flex-col justify-center gap-2 px-0 py-3" : "h-14 gap-2 px-3"}`}>
          <button
            type="button"
            onClick={() => {
              onHome();
              onNavigate?.();
            }}
            className="inline-flex h-9 w-11 shrink-0 items-center justify-center rounded-lg text-zinc-200 transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-emerald-500"
            aria-label="Home"
            title="Home"
          >
            <CaidLogo className="h-5 w-9" sizes="36px" />
          </button>
          {!compact && (
            <span className="min-w-0 truncate text-sm font-semibold tracking-tight text-zinc-100">Forma</span>
          )}
          <button
            type="button"
            onClick={isDrawer ? onClose : onToggle}
            className={`${compact ? "h-8 w-8" : "ml-auto h-8 w-8"} inline-flex shrink-0 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-800/40 hover:text-zinc-200`}
            aria-label={isDrawer ? "Close sidebar" : compact ? "Expand chat sidebar" : "Collapse chat sidebar"}
            title={isDrawer ? "Close sidebar" : compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isDrawer ? <X className="h-4 w-4" /> : compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        <div className="px-3 pb-2 pt-1">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              if (!newChatDisabled) onNavigate?.();
            }}
            disabled={newChatDisabled}
            className={`flex h-9 w-full items-center justify-center gap-2 rounded-lg text-xs font-semibold transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500 ${
              newChatDisabled
                ? "cursor-not-allowed bg-zinc-800/40 text-zinc-600"
                : "bg-emerald-500 text-zinc-950 shadow-sm hover:bg-emerald-400"
            } ${compact ? "px-0" : "px-3"}`}
            aria-label="New chat"
            title={newChatDisabled ? "Send a message before starting another chat" : "New chat"}
          >
            <Plus className="h-4 w-4 shrink-0" />
            {!compact && <span className="truncate">New chat</span>}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <SidebarSectionLabel compact={compact}>Chats</SidebarSectionLabel>
          <div className="space-y-0.5">
            {chatsLoading ? (
              Array.from({ length: compact ? 5 : 7 }, (_, index) => (
                <div
                  key={`chat-skeleton-${index}`}
                  className={`flex h-9 animate-pulse items-center gap-3 px-3 ${compact ? "justify-center" : ""}`}
                  aria-hidden="true"
                >
                  {compact ? (
                    <span className="h-4 w-4 rounded bg-zinc-800/80" />
                  ) : (
                    <>
                      <span className="h-2.5 flex-1 rounded bg-zinc-800/80" />
                      <span className="h-2.5 w-9 rounded bg-zinc-800/60" />
                    </>
                  )}
                </div>
              ))
            ) : chats.length ? (
              chats.map((chat) => {
                const active = chat.chatId === activeChatId;
                const dateLabel = formatSidebarDate(chat.createdAt);
                const waiting = waitingChatIds.has(chat.chatId);
                const renaming = !compact && Boolean(onRenameChat) && renamingChatId === chat.chatId;
                const rowClassName = `flex w-full min-w-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors ${
                  active
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-200"
                } ${compact ? "justify-center px-0" : ""}`;
                const rowContent = compact ? (
                  waiting ? (
                    <RefreshCw className={`h-4 w-4 animate-spin ${active ? "text-emerald-400" : "text-zinc-500"}`} />
                  ) : (
                    <MessageSquare className={`h-4 w-4 ${active ? "text-emerald-400" : "text-zinc-500"}`} />
                  )
                ) : (
                  <>
                    <div className="min-w-0 flex-1">
                      {renaming ? (
                        <input
                          value={renameDraft}
                          onChange={(event) => setRenameDraft(event.target.value)}
                          onBlur={() => commitSidebarRename(chat)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              event.currentTarget.blur();
                            }
                            if (event.key === "Escape") {
                              event.preventDefault();
                              setRenameDraft(chat.title);
                              setRenamingChatId(null);
                            }
                          }}
                          onClick={(event) => event.stopPropagation()}
                          autoFocus
                          aria-label={`Rename ${chat.title}`}
                          className="w-full bg-transparent text-xs font-medium text-zinc-100 outline-none"
                        />
                      ) : (
                        <div className="truncate">{chat.title}</div>
                      )}
                      {chat.projectCount > 1 && (
                        <div className="mt-0.5 text-[10px] text-zinc-600">{chat.projectCount} projects</div>
                      )}
                    </div>
                    {waiting && (
                      <RefreshCw className={`h-3.5 w-3.5 shrink-0 animate-spin ${active ? "text-emerald-400" : "text-zinc-500"}`} />
                    )}
                    {dateLabel && <div className="shrink-0 text-[10px] text-zinc-600">{dateLabel}</div>}
                  </>
                );
                if (renaming) {
                  return (
                    <div key={chat.chatId} className={rowClassName}>
                      {rowContent}
                    </div>
                  );
                }
                return (
                  <button
                    key={chat.chatId}
                    type="button"
                    onClick={() => {
                      onOpenChat(chat);
                      onNavigate?.();
                    }}
                    onDoubleClick={(event) => {
                      if (compact || !onRenameChat) return;
                      event.preventDefault();
                      event.stopPropagation();
                      setRenameDraft(chat.title);
                      setRenamingChatId(chat.chatId);
                    }}
                    className={rowClassName}
                    title={waiting ? `${chat.title} is waiting` : onRenameChat ? `${chat.title}. Double-click to rename.` : chat.title}
                    aria-label={`Open chat ${chat.title}${waiting ? " (waiting)" : ""}`}
                  >
                    {rowContent}
                  </button>
                );
              })
            ) : (
              !compact && <div className="px-3 py-2 text-xs leading-5 text-zinc-500">No saved chats yet.</div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-white/5 px-3 py-3">
        <SidebarSectionLabel compact={compact}>Workspace</SidebarSectionLabel>
        <div className="space-y-0.5">
          <SidebarNavLink href="/my-projects" icon={Database} label="My projects" compact={compact} onNavigate={onNavigate} />
          <SidebarNavLink href="/projects" icon={Layers} label="Community" compact={compact} onNavigate={onNavigate} />
          {showJobs ? (
            <SidebarNavLink href="/jobs" icon={History} label="Jobs" compact={compact} onNavigate={onNavigate} />
          ) : jobsPending ? (
            <div className={`flex h-8 animate-pulse items-center gap-2.5 px-3 ${compact ? "justify-center px-0" : ""}`} aria-hidden="true">
              <span className="h-4 w-4 rounded bg-zinc-800/80" />
              {!compact && <span className="h-2.5 w-14 rounded bg-zinc-800/80" />}
            </div>
          ) : null}
          {showDeveloperTools && (
            <SidebarNavLink href="/backend-logs" icon={Terminal} label="Backend logs" compact={compact} onNavigate={onNavigate} />
          )}
          {showDeveloperTools && (
            <SidebarNavLink href="/listening-jobs" icon={Terminal} label="Listening jobs" compact={compact} onNavigate={onNavigate} />
          )}
        </div>
        <SidebarSectionLabel compact={compact}>General</SidebarSectionLabel>
        <div className={`space-y-0.5 ${compact ? "mt-1" : ""}`}>
          <SidebarNavLink href="/settings" icon={Settings} label="Settings" compact={compact} onNavigate={onNavigate} />
          <SidebarNavLink href="/about" icon={Handshake} label="About us" compact={compact} onNavigate={onNavigate} />
        </div>
        {authRequired && <SidebarAccountDock compact={compact} />}
      </div>
    </aside>
  );
}
