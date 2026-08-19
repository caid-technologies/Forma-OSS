"use client";

import type { ChangeEventHandler, ClipboardEventHandler, FormEventHandler, ReactNode, RefObject } from "react";
import { useEffect, useRef } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  KeyRound,
  Paperclip,
  RefreshCw,
  Settings,
  Square,
  X,
} from "lucide-react";

import { shouldOfferFailedBuildRetry } from "../../lib/conversation-build-state";
import ConversationMessageList, { type ConversationMessage } from "./conversation-message-list";
import useChatAutoScroll from "./use-chat-auto-scroll";

type HomeChatViewProps = {
  started: boolean;
  conversationKey: string;
  workspaceTitle?: ReactNode;
  messages: ConversationMessage[];
  renderPipelineProgress: (message: ConversationMessage) => ReactNode;
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
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const retryMode = shouldOfferFailedBuildRetry({
    canRetryFailedBuild,
    hasInput: hasGenerationInput,
    generationActive,
  });
  const promptRunning = isLoading || generationActive;
  const canFinishPrompt = !generationActive && !retryMode && hasGenerationInput && generationReady && !isLoading;
  const primaryActionLabel = generationActive
    ? "Stop generation"
    : retryMode
      ? "Try failed build again"
      : inputValid
        ? "Send context"
        : "Check hardware idea";

  useEffect(() => {
    if (selectedImage) promptRef.current?.focus();
  }, [selectedImage]);

  return (
    <section
      className={`${
        !started
          ? "fixed bottom-[10rem] left-0 right-0 top-0 z-10 max-w-none pt-16 md:static md:inset-auto md:z-auto md:w-full md:max-w-none md:justify-center md:px-6 md:py-8 md:pt-8"
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
          <div className="hidden min-w-0 shrink-0 items-center px-3 pb-1 sm:px-4 md:flex">
            {workspaceTitle}
          </div>
        ) : null}
        {started && (
          <div
            ref={containerRef}
            onScroll={handleScroll}
            className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-3 pb-5 pt-16 sm:px-4 sm:pb-6 md:pt-5"
          >
            <ConversationMessageList
              messages={messages}
              renderPipelineProgress={renderPipelineProgress}
              onSelectContextSuggestion={onSelectContextSuggestion}
              isLoading={isLoading}
              canBuildNow={canBuildNow}
              buildNowLoading={buildNowLoading}
              onBuildNow={onBuildNow}
            />
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
                  className="home-example-card group relative flex min-w-[240px] snap-start cursor-pointer flex-col justify-between rounded-xl border p-3.5 text-left transition-all sm:min-w-0"
                >
                  <span className="home-example-card-label line-clamp-3 text-xs font-medium leading-snug">
                    {example}
                  </span>
                  <span className="home-example-card-icon mt-2 flex justify-end text-zinc-500" aria-hidden="true">
                    <ArrowUpRight className="h-3.5 w-3.5" />
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
              ? "md:sticky md:bottom-0 md:bg-transparent md:pb-3"
              : "md:static md:order-1 md:bg-transparent md:p-0"
          } fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain bg-transparent px-3 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1 sm:px-4 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible`}
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

          {notice && (
            <div id="generation-input-notice" role="status" className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
              <span className="break-anywhere min-w-0 flex-1">{notice}</span>
            </div>
          )}

          <div
            className={`prompt-composer w-full rounded-2xl bg-[#181b22] px-3 pb-2.5 pt-2.5 ${
              promptRunning ? "prompt-composer-illuminate" : "prompt-composer-idle"
            }`}
          >
            <input ref={imageInputRef} type="file" accept="image/*" onChange={onImageChange} className="hidden" />
            {selectedImage && (
              <div className="mb-2 flex items-start gap-2 rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-1.5 pr-2">
                <img
                  src={selectedImage}
                  alt="Attached prompt image"
                  className="h-16 w-16 shrink-0 rounded-lg object-cover"
                />
                <div className="min-w-0 flex-1 py-0.5">
                  <div className="text-xs font-medium text-[var(--forma-text-strong)]">Image prompt</div>
                  <div className="mt-0.5 text-[11px] leading-4 text-[var(--forma-text-muted)]">
                    Add details below, then press Enter.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onRemoveImage}
                  className="rounded-md p-1.5 text-[var(--forma-text-muted)] transition-colors hover:bg-[var(--forma-page)] hover:text-[var(--forma-text-strong)]"
                  aria-label="Remove image"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            <textarea
              ref={promptRef}
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
              placeholder={
                selectedImage
                  ? "Add constraints, references, or what you want from this image…"
                  : "Describe the product, constraints, references, and outputs you need…"
              }
              aria-invalid={Boolean(notice)}
              aria-describedby={notice ? "generation-input-notice" : undefined}
              className="min-h-[64px] w-full resize-none border-none bg-transparent text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-500 sm:min-h-[72px] sm:leading-7"
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
              <div className="flex items-center gap-1.5">
                {canFinishPrompt && (
                  <span className="prompt-composer-enter-hint hidden sm:inline" aria-hidden="true">
                    Enter
                  </span>
                )}
                <button
                  type={generationActive || retryMode ? "button" : "submit"}
                  onClick={generationActive ? onStop : retryMode ? onRetryFailedBuild : undefined}
                  disabled={retryMode ? retryingFailedBuild : !generationActive && (isLoading || !hasGenerationInput || !generationReady)}
                  className={`prompt-composer-send flex h-7 w-7 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed ${
                    canFinishPrompt || retryMode ? "is-ready" : ""
                  }`}
                  aria-label={canFinishPrompt ? `${primaryActionLabel}, or press Enter` : primaryActionLabel}
                  title={canFinishPrompt ? `${primaryActionLabel} · Enter` : primaryActionLabel}
                >
                  {generationActive ? (
                    <Square className="h-3.5 w-3.5 fill-current" />
                  ) : retryMode ? (
                    <RefreshCw className={`h-3.5 w-3.5 ${retryingFailedBuild ? "animate-spin" : ""}`} />
                  ) : isLoading ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ArrowRight className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>
          </div>

        </form>
        {started && <div className="h-40 shrink-0 md:hidden" aria-hidden="true" />}
      </div>
    </section>
  );
}
