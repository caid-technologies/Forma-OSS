"use client";

import type { ChangeEventHandler, ClipboardEventHandler, FormEventHandler, ReactNode, RefObject } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Cpu,
  KeyRound,
  Paperclip,
  RefreshCw,
  Settings,
  Square,
  X,
} from "lucide-react";

import CopyButton from "../../components/copy-button";
import useChatAutoScroll from "./use-chat-auto-scroll";

type HomeChatMessage = {
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

type HomeChatViewProps = {
  started: boolean;
  conversationKey: string;
  workspaceTitle?: ReactNode;
  messages: HomeChatMessage[];
  renderPipelineProgress: (message: HomeChatMessage) => ReactNode;
  projectArtifact?: ReactNode;
  examples: string[];
  onSelectExample: (example: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  canBuildNow: boolean;
  buildNowLoading: boolean;
  onBuildNow: () => void;
  onSelectContextSuggestion: (suggestion: string) => void;
  isLoading: boolean;
  generationReady: boolean;
  needsGenerationProvider: boolean;
  needsImageProvider: boolean;
  selectedImage: string | null;
  onRemoveImage: () => void;
  notice: string | null;
  prompt: string;
  onPromptChange: (prompt: string) => void;
  generationActive: boolean;
  onStop: () => void;
  canRetryFailedBuild: boolean;
  retryingFailedBuild: boolean;
  onRetryFailedBuild: () => void;
  hasGenerationInput: boolean;
  inputValid: boolean;
  imageInputRef: RefObject<HTMLInputElement | null>;
  onImageChange: ChangeEventHandler<HTMLInputElement>;
  onImagePaste: ClipboardEventHandler<HTMLTextAreaElement>;
};

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function HomeChatView({
  started,
  conversationKey,
  workspaceTitle,
  messages,
  renderPipelineProgress,
  projectArtifact,
  examples,
  onSelectExample,
  onSubmit,
  canBuildNow,
  buildNowLoading,
  onBuildNow,
  onSelectContextSuggestion,
  isLoading,
  generationReady,
  needsGenerationProvider,
  needsImageProvider,
  selectedImage,
  onRemoveImage,
  notice,
  prompt,
  onPromptChange,
  generationActive,
  onStop,
  canRetryFailedBuild,
  retryingFailedBuild,
  onRetryFailedBuild,
  hasGenerationInput,
  inputValid,
  imageInputRef,
  onImageChange,
  onImagePaste,
}: HomeChatViewProps) {
  const { containerRef, endRef, handleScroll } = useChatAutoScroll(conversationKey, messages);
  const latestChoiceMessageId = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && Boolean(message.contextSuggestions?.length))?.id;
  const retryMode = canRetryFailedBuild && !hasGenerationInput && !generationActive;
  const promptRunning = isLoading || generationActive;
  const primaryActionLabel = generationActive
    ? "Stop generation"
    : retryMode
      ? "Try failed build again"
      : inputValid
        ? "Send context"
        : "Check hardware idea";

  return (
    <section
      className={`${
        !started
          ? "fixed bottom-[224px] left-0 right-0 top-[3.75rem] z-10 max-w-none md:static md:inset-auto md:z-auto md:w-full md:max-w-none md:justify-center md:px-6 md:py-8"
          : "w-full max-w-none"
      } flex min-h-0 flex-1 flex-col text-center`}
    >
      {!started && (
        <div className="shrink-0">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100 sm:mt-1 sm:text-3xl">
            Turn an idea into a hardware plan.
          </h1>
          <p className="mx-auto mt-1.5 max-w-xl text-xs leading-relaxed text-zinc-400 sm:text-sm">
            Upload a photo, sketch, or short description. Get parts, wiring, cost, and build steps.
          </p>
        </div>
      )}

      <div
        className={`${
          started
            ? "mt-0 flex-1 overflow-hidden"
            : "mt-4 flex-1 overflow-hidden sm:mt-5 md:mx-auto md:w-full md:max-w-2xl md:flex-none md:overflow-visible"
        } flex min-h-0 flex-col text-left`}
      >
        {started && workspaceTitle ? (
          <div className="flex min-w-0 shrink-0 items-center px-3 pb-1 sm:px-4">
            {workspaceTitle}
          </div>
        ) : null}
        {started && (
          <div
            ref={containerRef}
            onScroll={handleScroll}
            className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-3 py-4 sm:px-4 sm:py-5"
          >
            {messages.map((message) => {
              const isUser = message.role === "user";
              const statusTone =
                message.status === "error"
                  ? "border-rose-400/40 bg-rose-950/30 text-rose-100"
                  : message.status === "success"
                    ? "border-emerald-400/35 bg-emerald-950/25 text-emerald-50"
                    : message.status === "cancelled"
                      ? "border-amber-300/35 bg-amber-950/20 text-amber-50"
                      : isUser
                        ? "border-emerald-500/20 bg-emerald-500/10 text-zinc-100"
                        : "border-white/5 bg-[#181b22] text-zinc-100";
              return (
                <div key={message.id} className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
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
                      <span>{isUser ? "You" : "Forma"}</span>
                      <span className="text-zinc-700">·</span>
                      <span suppressHydrationWarning>{formatTimestamp(message.timestamp)}</span>
                      <CopyButton
                        value={message.content}
                        label={isUser ? "Copy your message" : "Copy Forma's message"}
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
                            onClick={() => onSelectContextSuggestion(suggestion)}
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
                      <img
                        src={message.imagePreview}
                        alt="Hardware reference thumbnail"
                        className="mt-3 h-24 w-36 rounded-lg border border-white/10 object-cover"
                      />
                    )}
                    {!message.projectId && renderPipelineProgress(message)}
                  </div>
                </div>
              );
            })}
            {projectArtifact}
            <div ref={endRef} />
          </div>
        )}

        {!started && (
          <div className="mt-auto shrink-0 px-3 py-3 sm:px-4 md:order-2 md:mt-4 md:px-0 md:py-0">
            <div className="flex snap-x gap-3 overflow-x-auto pb-1 sm:grid sm:grid-cols-3 sm:overflow-visible sm:pb-0">
              {examples.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => onSelectExample(example)}
                  className="group relative flex min-w-[240px] snap-start cursor-pointer flex-col justify-between rounded-xl border border-white/5 bg-[#181b22]/70 p-3.5 text-left transition-all hover:border-emerald-500/30 hover:bg-[#181b22] sm:min-w-0"
                >
                  <span className="line-clamp-3 text-xs font-medium leading-snug text-zinc-300 transition-colors group-hover:text-zinc-100">
                    {example}
                  </span>
                  <span className="mt-2 flex items-center gap-1 text-[10px] text-zinc-500 transition-colors group-hover:text-emerald-400">
                    <ArrowRight className="h-3 w-3" />
                    Use prompt
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        <form
          onSubmit={onSubmit}
          className={`${
            started
              ? "md:sticky md:bottom-0 md:bg-transparent md:pb-4"
              : "md:static md:order-1 md:bg-transparent md:p-0"
          } fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain bg-transparent px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2 sm:px-4 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible`}
        >
          {(needsGenerationProvider || needsImageProvider) && (
            <section className="mb-3 rounded-xl border border-white/5 bg-[#181b22] p-3 text-left sm:p-4" aria-label="Bring your own key setup">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                    <KeyRound className="h-4 w-4" />
                    Bring your own key
                  </div>
                  <p className="mt-1 text-xs leading-5 text-zinc-400">
                    Provider credentials are configured per account and are not taken from the public frontend environment.
                  </p>
                </div>
                <Link
                  href="/settings"
                  className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-emerald-500 px-3 text-xs font-semibold text-zinc-950 transition-colors hover:bg-emerald-400"
                >
                  <Settings className="h-3.5 w-3.5" />
                  Open settings
                </Link>
              </div>
              <div className={`mt-3 grid gap-2 ${needsGenerationProvider && needsImageProvider ? "md:grid-cols-2" : ""}`}>
                {needsGenerationProvider && (
                  <div className="rounded-lg border border-white/5 bg-[#0f1117] p-3">
                    <div className="text-xs font-medium text-zinc-100">LLM provider required</div>
                    <ol className="mt-2 space-y-1 text-xs leading-5 text-zinc-400">
                      <li>1. Open Settings and choose a model provider.</li>
                      <li>2. Enter its scoped API key and model.</li>
                      <li>3. Turn Enabled on, save, then return here.</li>
                    </ol>
                  </div>
                )}
                {needsImageProvider && (
                  <div className="rounded-lg border border-white/5 bg-[#0f1117] p-3">
                    <div className="text-xs font-medium text-zinc-100">Image provider required</div>
                    <ol className="mt-2 space-y-1 text-xs leading-5 text-zinc-400">
                      <li>1. Open Settings and select Image Generation.</li>
                      <li>2. Choose a provider and add its scoped key, model, and required confirmation.</li>
                      <li>3. Enable and save it before returning to your build.</li>
                    </ol>
                  </div>
                )}
              </div>
            </section>
          )}

          {selectedImage && (
            <div className="mb-3 flex items-center gap-3 rounded-xl border border-white/5 bg-[#181b22] p-2">
              <img src={selectedImage} alt="Attached reference" className="h-16 w-24 rounded-lg object-cover" />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-zinc-100">Image attached</div>
                <div className="mt-1 text-[11px] text-zinc-500">Forma will use this image with your next message.</div>
              </div>
              <button
                type="button"
                onClick={onRemoveImage}
                className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-800/40 hover:text-zinc-200"
                aria-label="Remove image"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {notice && (
            <div id="generation-input-notice" role="status" className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
              <span className="break-anywhere min-w-0 flex-1">{notice}</span>
            </div>
          )}

          <div
            className={`prompt-composer w-full rounded-2xl bg-[#181b22] p-3 ${
              promptRunning ? "prompt-composer-illuminate" : "prompt-composer-idle"
            }`}
          >
            <input ref={imageInputRef} type="file" accept="image/*" onChange={onImageChange} className="hidden" />
            <textarea
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              onPaste={onImagePaste}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (isLoading) return;
                  if (retryMode) {
                    onRetryFailedBuild();
                    return;
                  }
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Describe the product, constraints, references, and outputs you need…"
              aria-invalid={Boolean(notice)}
              aria-describedby={notice ? "generation-input-notice" : undefined}
              className="min-h-[72px] w-full resize-none border-none bg-transparent text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-500 sm:min-h-[88px] sm:leading-7"
            />
            <div className="mt-1 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800/50 hover:text-zinc-200"
                aria-label="Attach image"
                title="Attach an image or paste one from your clipboard"
              >
                <Paperclip className="h-4 w-4" />
              </button>
              <button
                type={generationActive || retryMode ? "button" : "submit"}
                onClick={generationActive ? onStop : retryMode ? onRetryFailedBuild : undefined}
                disabled={retryMode ? retryingFailedBuild : !generationActive && (isLoading || !hasGenerationInput || !generationReady)}
                className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500 text-zinc-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={primaryActionLabel}
                title={primaryActionLabel}
              >
                {generationActive ? (
                  <Square className="h-3.5 w-3.5 fill-current" />
                ) : retryMode ? (
                  <RefreshCw className={`h-3.5 w-3.5 ${retryingFailedBuild ? "animate-spin" : ""}`} />
                ) : isLoading ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

        </form>
        {started && <div className="h-[224px] shrink-0 md:hidden" aria-hidden="true" />}
      </div>
    </section>
  );
}
