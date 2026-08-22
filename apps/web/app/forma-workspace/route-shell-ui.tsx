"use client";

import type { ElementType, ReactNode } from "react";
import { AlertTriangle, ArrowLeft, KeyRound, RefreshCw, Trash2 } from "lucide-react";

import { useFormaAuth } from "../../lib/forma-auth";
import { MobileSidebarButton } from "./sidebar";
import type { ChatRouteTransition, PendingProjectDeletion } from "./types";

export function ProjectDeletionDialog({
  project,
  acknowledged,
  contribute,
  busy,
  error,
  onAcknowledgedChange,
  onContributeChange,
  onCancel,
  onConfirm,
}: {
  project: PendingProjectDeletion | null;
  acknowledged: boolean;
  contribute: boolean;
  busy: boolean;
  error: string | null;
  onAcknowledgedChange: (value: boolean) => void;
  onContributeChange: (value: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!project) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="presentation">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
        className="w-full max-w-xl rounded-2xl border border-white/5 bg-[#181b22] p-6 text-zinc-100 shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-300">
            <Trash2 className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h2 id="delete-project-title" className="text-lg font-semibold tracking-tight text-zinc-100">
              Delete this project?
            </h2>
            <p className="mt-1 break-words text-sm text-zinc-400">{project.title}</p>
          </div>
        </div>
        <p className="mt-5 text-sm leading-6 text-zinc-300">
          Removed from your workspace now. Permanently deleted after 30 days.
        </p>
        <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg border border-white/10 bg-[#0f1117] p-4 text-sm leading-5 text-zinc-300">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => onAcknowledgedChange(event.target.checked)}
            disabled={busy}
            className="mt-0.5 h-4 w-4 accent-red-400"
          />
          <span>I understand I will lose access to this project.</span>
        </label>
        <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] p-4">
          <label className="flex cursor-pointer items-start gap-3 text-sm font-medium leading-5 text-zinc-200">
            <input
              type="checkbox"
              checked={contribute}
              onChange={(event) => onContributeChange(event.target.checked)}
              disabled={busy}
              className="mt-0.5 h-4 w-4 accent-emerald-400"
            />
            <span>Keep a sanitized copy for product research.</span>
          </label>
          <p className="mt-3 text-xs leading-5 text-zinc-500">
            Personal details are removed. You can withdraw until the copy is anonymized.
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-xs font-medium">
            <a href="/legal/privacy-policy" target="_blank" rel="noreferrer" className="text-emerald-400 transition-colors hover:text-emerald-300">Privacy policy</a>
            <a href="/legal/data-contribution-terms" target="_blank" rel="noreferrer" className="text-emerald-400 transition-colors hover:text-emerald-300">Data contribution terms</a>
          </div>
        </div>
        {error && <p className="mt-4 rounded-lg border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">{error}</p>}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="inline-flex h-9 items-center justify-center rounded-lg border border-white/10 px-4 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!acknowledged || busy}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-red-500 px-4 text-xs font-medium text-white transition-colors hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Deleting..." : "Delete project"}
          </button>
        </div>
      </section>
    </div>
  );
}


export function WorkspaceChromeIdentity({
  icon: Icon,
  badge,
  title,
}: {
  icon: ElementType<{ className?: string }>;
  badge: string;
  title: React.ReactNode;
}) {
  return (
    <div className="min-w-0 flex-1">
      <div className="flex min-w-0 items-center gap-2">
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
          <Icon className="h-3 w-3" />
          {badge}
        </span>
        {typeof title === "string" ? (
          <h2 className="truncate text-sm font-semibold tracking-tight text-zinc-100">{title}</h2>
        ) : title}
      </div>
    </div>
  );
}

export function WorkspacePageHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: ElementType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <section className="mb-6 border-b border-white/5 pb-5">
      <div className="hidden min-w-0 items-center gap-3 md:flex">
        <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold tracking-tight text-zinc-100">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-500">{description}</p>
        </div>
      </div>
      <p className="max-w-2xl text-sm leading-6 text-zinc-500 md:hidden">{description}</p>
    </section>
  );
}

export function ProjectRouteFallbackPanel({
  projectId,
  error,
  onHome,
  onOpenSidebar,
}: {
  projectId: string;
  error: string | null;
  onHome: () => void;
  onOpenSidebar: () => void;
}) {
  return (
    <main className="flex min-h-0 min-w-0 flex-col">
      <header className="flex h-12 items-center gap-3 border-b border-white/5 bg-[#0f1117]/80 px-4 backdrop-blur-md">
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="flex min-w-0 flex-1 items-baseline gap-2">
          <div className="truncate text-sm font-semibold tracking-tight text-zinc-100">
            {error ? "Project unavailable" : "Opening project"}
          </div>
          <div className="truncate font-mono text-[10px] text-zinc-600">{projectId}</div>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 items-center justify-center p-5">
        <div className="w-full max-w-md rounded-2xl border border-white/5 bg-[#181b22] p-6 text-center shadow-2xl shadow-black/30">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-500/10">
            {error ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <RefreshCw className="h-5 w-5 animate-spin text-emerald-400" />}
          </div>
          <h1 className="mt-5 text-lg font-semibold tracking-tight text-zinc-100">
            {error ? "Project unavailable" : "Opening project"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            {error || "Loading the saved hardware plan."}
          </p>
          {error && (
            <button
              type="button"
              onClick={onHome}
              className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-4 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100"
            >
              <ArrowLeft className="h-4 w-4" />
              Back home
            </button>
          )}
        </div>
      </section>
    </main>
  );
}

export function AuthRequiredRouteScreen({
  loading,
  title,
  message,
  onHome,
}: {
  loading: boolean;
  title: string;
  message: string;
  onHome: () => void;
}) {
  const { openSignIn } = useFormaAuth();
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#0f1117] px-5 font-sans text-zinc-100">
      <div className="w-full max-w-md rounded-2xl border border-white/5 bg-[#181b22] p-6 shadow-2xl">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
            <KeyRound className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight text-zinc-100">{title}</h1>
            <p className="mt-1 text-sm text-zinc-500">{loading ? "Checking session..." : message}</p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onHome}
            className="inline-flex h-9 items-center justify-center rounded-lg border border-white/10 px-3 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100"
          >
            Home
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" })}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-emerald-500 px-3 text-xs font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 disabled:cursor-wait disabled:opacity-50"
          >
            Sign in
          </button>
        </div>
      </div>
    </div>
  );
}

export function ChatRouteFallbackPanel({
  transition,
  onHome,
  onOpenSidebar,
}: {
  transition: ChatRouteTransition;
  onHome: () => void;
  onOpenSidebar: () => void;
}) {
  const hasProjectTarget = Boolean(transition.projectId);
  return (
    <main className="flex min-h-0 min-w-0 flex-col">
      <header className="flex h-12 min-w-0 items-center gap-2 overflow-hidden border-b border-white/5 bg-[#0f1117]/80 px-3 backdrop-blur-md sm:gap-3 sm:px-4">
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="flex min-w-0 flex-1 items-baseline gap-2">
          <div className="truncate text-sm font-semibold tracking-tight text-zinc-100">{transition.title || "Opening chat"}</div>
          <span className="truncate font-mono text-[10px] text-zinc-600">{transition.projectId || transition.chatId}</span>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 items-center justify-center p-5">
        <div className="w-full max-w-md rounded-2xl border border-white/5 bg-[#181b22] p-6 text-center shadow-2xl shadow-black/30">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-500/10">
            {transition.error ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <RefreshCw className="h-5 w-5 animate-spin text-emerald-400" />}
          </div>
          <h1 className="mt-5 text-lg font-semibold tracking-tight text-zinc-100">
            {transition.error ? "Chat unavailable" : hasProjectTarget ? "Opening project chat" : "Opening chat"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            {transition.error || (hasProjectTarget ? "Loading the active project for this chat." : "Preparing the chat workspace.")}
          </p>
          <div className="mt-4 space-y-2">
            <div className="truncate rounded-lg border border-white/5 bg-[#0f1117] px-3 py-2 font-mono text-xs text-zinc-500">
              {transition.chatId}
            </div>
            {transition.projectId && (
              <div className="truncate rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-3 py-2 font-mono text-xs text-emerald-100">
                {transition.projectId}
              </div>
            )}
          </div>
          {transition.error && (
            <button
              type="button"
              onClick={onHome}
              className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-4 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800/40 hover:text-zinc-100"
            >
              <ArrowLeft className="h-4 w-4" />
              Back home
            </button>
          )}
        </div>
      </section>
    </main>
  );
}

