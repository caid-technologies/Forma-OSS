"use client";

import type { ReactNode } from "react";
import Image from "next/image";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Cpu,
  RefreshCw,
  Square,
} from "lucide-react";

import CopyButton from "../../components/copy-button";

export type ConversationMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  status?: "idle" | "loading" | "success" | "error" | "cancelled";
  timestamp: string;
  projectId?: string | null;
  pipelineProgress?: unknown;
  imagePreview?: string | null;
  contextProjectId?: string | null;
  workflowState?: string | null;
  contextQuestions?: string[];
  contextSuggestions?: string[];
  buildPlanId?: string | null;
  buildJobId?: string | null;
};

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ConversationMessageList({
  messages,
  renderPipelineProgress,
  variant = "home",
  emptyMessage,
  onSelectContextSuggestion,
  isLoading = false,
  canBuildNow = false,
  buildNowLoading = false,
  onBuildNow,
}: {
  messages: ConversationMessage[];
  renderPipelineProgress: (message: ConversationMessage) => ReactNode;
  variant?: "home" | "project";
  emptyMessage?: string;
  onSelectContextSuggestion?: (suggestion: string) => void;
  isLoading?: boolean;
  canBuildNow?: boolean;
  buildNowLoading?: boolean;
  onBuildNow?: () => void;
}) {
  const latestChoiceMessageId = onSelectContextSuggestion
    ? [...messages]
      .reverse()
      .find((message) => message.role === "assistant" && Boolean(message.contextSuggestions?.length))?.id
    : null;
  const projectLayout = variant === "project";

  if (!messages.length && emptyMessage) {
    return (
      <div className="mx-auto w-full max-w-3xl rounded-xl border border-white/5 bg-[#181b22] p-5 text-sm leading-6 text-zinc-500">
        {emptyMessage}
      </div>
    );
  }

  return messages.map((message) => {
    const isUser = message.role === "user";
    const isSystem = message.role === "system";
    const statusTone =
      message.status === "error"
        ? "border-rose-400/40 bg-rose-950/30 text-rose-100"
        : message.status === "success"
          ? "border-emerald-400/35 bg-emerald-950/25 text-emerald-50"
          : message.status === "cancelled"
            ? "border-amber-300/35 bg-amber-950/20 text-amber-50"
            : isUser
              ? "border-emerald-500/20 bg-emerald-500/10 text-zinc-100"
              : isSystem
                ? "border-white/5 bg-black/25 text-zinc-400"
                : "border-white/5 bg-[#181b22] text-zinc-100";
    const showPipeline = Boolean(message.pipelineProgress)
      && (!message.projectId || message.status === "error" || message.status === "cancelled");

    return (
      <div
        key={message.id}
        className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"} ${projectLayout ? "mx-auto w-full max-w-3xl" : ""}`}
      >
        <div className={`min-w-0 max-w-[92%] overflow-hidden rounded-xl border px-3 py-2.5 sm:max-w-[86%] sm:px-4 sm:py-3 ${statusTone}`}>
          <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2 text-[10px] font-medium text-zinc-500">
            {message.status === "loading" ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin text-emerald-400" />
            ) : message.status === "success" ? (
              <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
            ) : message.status === "error" ? (
              <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />
            ) : message.status === "cancelled" ? (
              <Square className="h-3.5 w-3.5 fill-current text-amber-300" />
            ) : isUser ? (
              <ArrowRight className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <Cpu className="h-3.5 w-3.5 text-zinc-400" />
            )}
            <span>{isUser ? "You" : isSystem ? "Context" : "Forma"}</span>
            <span className="text-zinc-700">·</span>
            <span suppressHydrationWarning>{formatTimestamp(message.timestamp)}</span>
            <CopyButton
              value={message.content}
              label={isUser ? "Copy your message" : isSystem ? "Copy context message" : "Copy Forma's message"}
              className="ml-auto"
            />
          </div>
          <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
          {!isUser && message.id === latestChoiceMessageId && Boolean(message.contextSuggestions?.length) && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2" aria-label="Suggested answers">
              {message.contextSuggestions?.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => onSelectContextSuggestion?.(suggestion)}
                  disabled={isLoading}
                  className="flex min-h-12 items-center gap-2 rounded-lg border border-white/10 bg-[#0f1117] px-3 py-2 text-left text-xs font-medium text-zinc-300 transition-colors hover:border-emerald-500/30 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ArrowRight className="h-3.5 w-3.5 shrink-0" />
                  <span className="break-words">{suggestion}</span>
                </button>
              ))}
            </div>
          )}
          {!isUser && canBuildNow && (message.workflowState === "gathering_context" || Boolean(message.contextProjectId)) && (
            <button
              type="button"
              onClick={onBuildNow}
              disabled={buildNowLoading || isLoading}
              className="mt-3 inline-flex h-8 items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 text-xs font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Default — proceed with safe prototype defaults"
              title="Default — proceed with safe prototype defaults"
            >
              {buildNowLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
              Default
            </button>
          )}
          {message.imagePreview && (
            <Image
              src={message.imagePreview}
              alt="Hardware reference thumbnail"
              width={144}
              height={96}
              unoptimized
              className="mt-3 h-24 w-36 rounded-lg border border-white/10 object-cover"
            />
          )}
          {showPipeline && renderPipelineProgress(message)}
        </div>
      </div>
    );
  });
}
