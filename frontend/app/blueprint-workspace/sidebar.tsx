"use client";

import Link from "next/link";
import Image from "next/image";
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
  Wifi,
  WifiOff,
  X,
} from "lucide-react";

import { FormaUserButton, useFormaAuth } from "../../lib/forma-auth";

export type ChatListItem = {
  chatId: string;
  title: string;
  projectId: string;
  createdAt: string | null;
  projectCount: number;
};

function formatSidebarDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function MobileWorkspaceBar({
  onOpenSidebar,
  serverStatus = "disconnected",
  authRequired,
}: {
  onOpenSidebar: () => void;
  serverStatus?: "connected" | "disconnected";
  authRequired: boolean;
}) {
  const ApiStatusIcon = serverStatus === "connected" ? Wifi : WifiOff;
  const apiStatusLabel = serverStatus === "connected" ? "API connected" : "API disconnected";
  const apiStatusTone =
    serverStatus === "connected"
      ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
      : "border-orange-500/30 bg-orange-950/20 text-orange-300";

  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-12 shrink-0 items-center gap-3 border-b border-[#292b31] bg-[#141519] px-3 md:hidden">
      <MobileSidebarButton onClick={onOpenSidebar} />
      <div className="min-w-0 flex flex-1 items-center gap-2">
        <span className="truncate text-sm font-black uppercase tracking-[0.22em] text-white">Forma</span>
        <span className="border border-cyan-300/30 bg-cyan-300/10 px-1.5 py-0.5 text-[9px] font-black uppercase text-cyan-100">OSS</span>
      </div>
      <span
        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center border ${apiStatusTone}`}
        title={apiStatusLabel}
        aria-label={apiStatusLabel}
      >
        <ApiStatusIcon className="h-4 w-4" />
      </span>
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
      className={`inline-flex shrink-0 items-center justify-center border border-cyan-300/30 bg-cyan-300/10 font-black uppercase text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-wait disabled:border-slate-700 disabled:text-slate-600 disabled:hover:bg-transparent disabled:hover:text-slate-600 ${
        compact ? "h-8 w-8" : "h-7 gap-1.5 px-2 text-[10px]"
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
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-[#2c2f37] bg-black text-slate-200 transition hover:bg-white hover:text-black md:hidden"
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
  waitingChatIds,
  chatsLoading,
  showJobs,
  jobsPending,
  showDeveloperTools,
  authRequired,
  serverStatus,
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
  waitingChatIds: Set<string>;
  chatsLoading?: boolean;
  showJobs: boolean;
  jobsPending?: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  serverStatus: "connected" | "disconnected";
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Sidebar">
      <button
        type="button"
        className="absolute inset-0 h-full w-full bg-black/65"
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
          waitingChatIds={waitingChatIds}
          chatsLoading={chatsLoading}
          showJobs={showJobs}
          jobsPending={jobsPending}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
      </div>
    </div>
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
  waitingChatIds,
  chatsLoading = false,
  showJobs,
  jobsPending = false,
  showDeveloperTools,
  authRequired,
  serverStatus = "disconnected",
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
  waitingChatIds: Set<string>;
  chatsLoading?: boolean;
  showJobs: boolean;
  jobsPending?: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  serverStatus?: "connected" | "disconnected";
  mode?: "desktop" | "drawer";
}) {
  const isDrawer = mode === "drawer";
  const compact = !isDrawer && collapsed;
  const ApiStatusIcon = serverStatus === "connected" ? Wifi : WifiOff;
  const apiStatusLabel = serverStatus === "connected" ? "API connected" : "API disconnected";
  const apiStatusTone =
    serverStatus === "connected"
      ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
      : "border-orange-500/30 bg-orange-950/20 text-orange-300";

  return (
    <aside
      className={
        isDrawer
          ? "flex h-full min-h-0 w-[min(320px,calc(100vw-2rem))] flex-col border-r border-[#292b31] bg-[#141519] text-slate-100 shadow-2xl shadow-black/50"
          : "hidden h-full min-h-0 flex-col border-r border-[#292b31] bg-[#141519] text-slate-100 md:flex"
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className={`flex shrink-0 items-center border-b border-[#292b31] ${compact ? "h-20 flex-col justify-center gap-2 px-0" : "h-16 gap-3 px-4"}`}>
          <button
            type="button"
            onClick={() => {
              onHome();
              onNavigate?.();
            }}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-[#2c2f37] bg-black text-slate-200 transition hover:bg-white hover:text-black"
            aria-label="Home"
            title="Home"
          >
            <Image
              src="/brand/caid-dark-logo.png"
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 object-contain"
              aria-hidden="true"
            />
          </button>
          {!compact && (
            <div className="min-w-0 flex items-center gap-2">
              <span className="truncate text-sm font-black uppercase tracking-[0.22em] text-white">Forma</span>
              <span className="border border-cyan-300/30 bg-cyan-300/10 px-1.5 py-0.5 text-[9px] font-black uppercase text-cyan-100">OSS</span>
              <span
                className={`inline-flex h-7 w-7 shrink-0 items-center justify-center border ${apiStatusTone}`}
                title={apiStatusLabel}
                aria-label={apiStatusLabel}
              >
                <ApiStatusIcon className="h-3.5 w-3.5" />
              </span>
              <AuthStatusControl authRequired={authRequired} />
            </div>
          )}
          <button
            type="button"
            onClick={isDrawer ? onClose : onToggle}
            className={`${compact ? "h-7 w-7" : "ml-auto h-8 w-8"} inline-flex shrink-0 items-center justify-center border border-transparent text-slate-500 transition hover:border-[#2c2f37] hover:text-cyan-100`}
            aria-label={isDrawer ? "Close sidebar" : compact ? "Expand chat sidebar" : "Collapse chat sidebar"}
            title={isDrawer ? "Close sidebar" : compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isDrawer ? <X className="h-4 w-4" /> : compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        <div className="px-4 pb-4">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              if (!newChatDisabled) onNavigate?.();
            }}
            disabled={newChatDisabled}
            className={`group flex h-11 w-full items-center border text-sm font-semibold ${
              newChatDisabled
                ? "cursor-not-allowed border-[#242832] bg-[#101116] text-slate-600"
                : "border-[#2c2f37] bg-[#17181d] text-white hover:bg-white hover:text-black"
            } ${
              compact ? "justify-center px-0" : "gap-3 px-3"
            }`}
            aria-label="New chat"
            title={newChatDisabled ? "Send a message before starting another chat" : "New chat"}
          >
            <Plus className={`h-5 w-5 shrink-0 ${newChatDisabled ? "text-slate-700" : "text-slate-500 group-hover:text-black"}`} />
            {!compact && <span className="truncate">New chat</span>}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {!compact && <div className="mb-3 text-sm text-slate-500">Chats</div>}
          <div className="space-y-1">
            {chatsLoading ? (
              Array.from({ length: compact ? 5 : 7 }, (_, index) => (
                <div
                  key={`chat-skeleton-${index}`}
                  className={`flex h-10 animate-pulse items-center gap-3 px-2 ${compact ? "justify-center" : ""}`}
                  aria-hidden="true"
                >
                  {compact ? (
                    <span className="h-5 w-5 bg-[#242832]" />
                  ) : (
                    <>
                      <span className="h-3 flex-1 bg-[#242832]" />
                      <span className="h-3 w-10 bg-[#20242d]" />
                    </>
                  )}
                </div>
              ))
            ) : chats.length ? (
              chats.map((chat) => {
                const active = chat.chatId === activeChatId;
                const dateLabel = formatSidebarDate(chat.createdAt);
                const waiting = waitingChatIds.has(chat.chatId);
                return (
                  <button
                    key={chat.chatId}
                    type="button"
                    onClick={() => {
                      onOpenChat(chat);
                      onNavigate?.();
                    }}
                    className={`flex w-full min-w-0 items-center gap-3 px-2 py-2 text-left text-sm transition ${
                      active ? "border border-cyan-300/25 bg-cyan-300/10 text-cyan-100" : "border border-transparent text-slate-100 hover:bg-[#17181d]"
                    } ${compact ? "justify-center" : ""}`}
                    title={waiting ? `${chat.title} is waiting` : chat.title}
                    aria-label={`Open chat ${chat.title}${waiting ? " (waiting)" : ""}`}
                  >
                    {compact ? (
                      waiting ? (
                        <RefreshCw className={`h-5 w-5 animate-spin ${active ? "text-cyan-300" : "text-slate-500"}`} />
                      ) : (
                        <MessageSquare className={`h-5 w-5 ${active ? "text-cyan-300" : "text-slate-500"}`} />
                      )
                    ) : (
                      <>
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-semibold">{chat.title}</div>
                          {chat.projectCount > 1 && (
                            <div className="mt-0.5 text-[11px] text-slate-600">{chat.projectCount} projects</div>
                          )}
                        </div>
                        {waiting && (
                          <RefreshCw className={`h-4 w-4 shrink-0 animate-spin ${active ? "text-cyan-300" : "text-slate-500"}`} />
                        )}
                        {dateLabel && <div className="shrink-0 text-xs text-slate-500">{dateLabel}</div>}
                      </>
                    )}
                  </button>
                );
              })
            ) : (
              !compact && <div className="px-2 py-2 text-xs leading-5 text-slate-500">No saved chats yet.</div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-[#292b31] px-4 py-5">
        {!compact && <div className="mb-3 text-sm text-slate-500">Workspace</div>}
        <div className="space-y-1">
          <Link
            href="/my-projects"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="My projects"
          >
            <Database className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">My projects</span>}
          </Link>
          <Link
            href="/projects"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="Projects"
          >
            <Layers className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">Projects</span>}
          </Link>
          {showJobs ? (
            <Link
              href="/jobs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Jobs"
            >
              <History className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Jobs</span>}
            </Link>
          ) : jobsPending ? (
            <div className={`flex h-10 animate-pulse items-center gap-3 px-2 ${compact ? "justify-center" : ""}`} aria-hidden="true">
              <span className="h-5 w-5 bg-[#242832]" />
              {!compact && <span className="h-3 w-16 bg-[#242832]" />}
            </div>
          ) : null}
          {showDeveloperTools && (
            <Link
              href="/backend-logs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Backend logs"
            >
              <Terminal className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Backend logs</span>}
            </Link>
          )}
          {showDeveloperTools && (
            <Link
              href="/listening-jobs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Listening jobs"
            >
              <Terminal className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Listening jobs</span>}
            </Link>
          )}
          <Link
            href="/settings"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="Settings"
          >
            <Settings className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">Settings</span>}
          </Link>
          <Link
            href="/about"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="About us"
          >
            <Handshake className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">About us</span>}
          </Link>
        </div>
      </div>
    </aside>
  );
}
