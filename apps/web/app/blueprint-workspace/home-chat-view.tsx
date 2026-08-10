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
  buildPlanId?: string | null;
  buildJobId?: string | null;
};

type HomeChatViewProps = {
  started: boolean;
  messages: HomeChatMessage[];
  endRef: RefObject<HTMLDivElement | null>;
  renderPipelineProgress: (message: HomeChatMessage) => ReactNode;
  projectArtifact?: ReactNode;
  examples: string[];
  onSelectExample: (example: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  canSkipContext: boolean;
  contextSkipping: boolean;
  onSkipContext: () => void;
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
  messages,
  endRef,
  renderPipelineProgress,
  projectArtifact,
  examples,
  onSelectExample,
  onSubmit,
  canSkipContext,
  contextSkipping,
  onSkipContext,
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
  hasGenerationInput,
  inputValid,
  imageInputRef,
  onImageChange,
  onImagePaste,
}: HomeChatViewProps) {
  const latestContextMessageId = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.workflowState === "gathering_context")?.id;

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
          <h1 className="text-2xl font-semibold leading-tight text-white sm:mt-1 sm:text-4xl sm:leading-tight">
            Turn an idea into a hardware plan.
          </h1>
          <p className="mx-auto mt-2 max-w-2xl text-xs leading-5 text-slate-400 sm:mt-3 sm:text-sm sm:leading-6">
            Upload a photo, sketch, or short description. Get parts, wiring, cost, and build steps.
          </p>
        </div>
      )}

      <div
        className={`${
          started
            ? "mt-0 flex-1 overflow-hidden"
            : "mt-4 flex-1 overflow-hidden sm:mt-5 md:mx-auto md:w-full md:max-w-5xl md:flex-none md:overflow-visible md:border"
        } flex min-h-0 flex-col border-y border-[#2c2f37] bg-[#111216] text-left shadow-2xl shadow-black/30`}
      >
        {started && (
          <div className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-3 py-4 sm:px-4 sm:py-5">
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
                        ? "border-cyan-300/45 bg-cyan-300/10 text-white"
                        : "border-[#30333d] bg-[#17181d] text-slate-100";
              return (
                <div key={message.id} className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
                  <div className={`min-w-0 max-w-[92%] overflow-hidden border px-3 py-2.5 sm:max-w-[86%] sm:px-4 sm:py-3 ${statusTone}`}>
                    <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                      {message.status === "loading" ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-300" />
                      ) : message.status === "success" ? (
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
                      ) : message.status === "error" ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />
                      ) : message.status === "cancelled" ? (
                        <Square className="h-3.5 w-3.5 fill-current text-amber-300" />
                      ) : isUser ? (
                        <ArrowRight className="h-3.5 w-3.5 text-cyan-300" />
                      ) : (
                        <Cpu className="h-3.5 w-3.5 text-slate-400" />
                      )}
                      <span>{isUser ? "You" : "Forma"}</span>
                      <span className="text-slate-700">/</span>
                      <span suppressHydrationWarning>{formatTimestamp(message.timestamp)}</span>
                      <CopyButton
                        value={message.content}
                        label={isUser ? "Copy your message" : "Copy Forma's message"}
                        className="ml-auto"
                      />
                    </div>
                    <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                    {!isUser && canSkipContext && message.id === latestContextMessageId && (
                      <button
                        type="button"
                        onClick={onSkipContext}
                        disabled={contextSkipping || isLoading}
                        className="mt-3 inline-flex h-9 items-center justify-center gap-2 border border-cyan-300/40 px-3 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100 hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {contextSkipping ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
                        Skip context gathering
                      </button>
                    )}
                    {message.imagePreview && (
                      <img
                        src={message.imagePreview}
                        alt="Hardware reference thumbnail"
                        className="mt-3 h-24 w-36 border border-cyan-300/25 object-cover"
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
          <div className="mt-auto shrink-0 bg-[#111216] px-3 py-3 sm:border-t sm:border-[#2c2f37] sm:px-4 md:mt-0">
            <div className="flex snap-x gap-2 overflow-x-auto pb-1 sm:flex-wrap sm:overflow-visible sm:pb-0">
              {examples.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => onSelectExample(example)}
                  className="min-w-[260px] snap-start border border-[#2c2f37] bg-[#17181d] px-3 py-2 text-left text-[11px] leading-5 text-slate-400 hover:border-slate-500 hover:text-white sm:min-w-0"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        <form
          onSubmit={onSubmit}
          className={`${started ? "md:sticky md:bottom-0" : "md:static"} fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain border-y border-[#2c2f37] bg-[#141519]/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:p-4 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible md:border-b-0 md:pb-4`}
        >
          {(needsGenerationProvider || needsImageProvider) && (
            <section className="mb-3 border border-cyan-300/30 bg-cyan-300/5 p-3 text-left sm:p-4" aria-label="Bring your own key setup">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.16em] text-cyan-100">
                    <KeyRound className="h-4 w-4 text-cyan-300" />
                    Bring your own key (BYOK)
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    Provider credentials are configured per account and are not taken from the public frontend environment.
                  </p>
                </div>
                <Link href="/settings" className="inline-flex h-9 shrink-0 items-center gap-2 bg-white px-3 text-[10px] font-black uppercase tracking-widest text-black hover:bg-slate-200">
                  <Settings className="h-3.5 w-3.5" />
                  Open Settings
                </Link>
              </div>
              <div className={`mt-3 grid gap-2 ${needsGenerationProvider && needsImageProvider ? "md:grid-cols-2" : ""}`}>
                {needsGenerationProvider && (
                  <div className="border border-[#2c2f37] bg-[#111216] p-3">
                    <div className="text-[10px] font-black uppercase tracking-widest text-white">LLM provider required</div>
                    <ol className="mt-2 space-y-1 text-xs leading-5 text-slate-400">
                      <li>1. Open Settings and choose a model provider.</li>
                      <li>2. Enter its scoped API key and model.</li>
                      <li>3. Turn Enabled on, save, then return here.</li>
                    </ol>
                  </div>
                )}
                {needsImageProvider && (
                  <div className="border border-[#2c2f37] bg-[#111216] p-3">
                    <div className="text-[10px] font-black uppercase tracking-widest text-white">Image provider required</div>
                    <ol className="mt-2 space-y-1 text-xs leading-5 text-slate-400">
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
            <div className="mb-3 flex items-center gap-3 border border-[#2c2f37] bg-black/30 p-2">
              <img src={selectedImage} alt="Attached reference" className="h-16 w-24 object-cover" />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-white">Image attached</div>
                <div className="mt-1 text-[11px] text-slate-500">Forma will use this image with your next message.</div>
              </div>
              <button type="button" onClick={onRemoveImage} className="p-2 text-slate-500 hover:text-white" aria-label="Remove image">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {notice && (
            <div id="generation-input-notice" role="status" className="mb-3 flex items-start gap-2 border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
              <span className="break-anywhere min-w-0 flex-1">{notice}</span>
            </div>
          )}

          <div className="relative">
            <input ref={imageInputRef} type="file" accept="image/*" onChange={onImageChange} className="hidden" />
            <textarea
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              onPaste={onImagePaste}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (!isLoading) event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Describe the product, constraints, references, and outputs you need…"
              aria-invalid={Boolean(notice)}
              aria-describedby={notice ? "generation-input-notice" : undefined}
              className="min-h-[98px] w-full resize-none border border-[#2c2f37] bg-[#0f1014] py-3 pl-14 pr-14 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300 sm:min-h-[104px] sm:py-4 sm:pl-16 sm:pr-16 sm:leading-7"
            />
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              className="absolute bottom-3 left-3 inline-flex h-9 w-9 items-center justify-center border border-[#2c2f37] text-slate-400 transition hover:bg-white hover:text-black sm:bottom-4 sm:left-4 sm:h-10 sm:w-10"
              aria-label="Attach image"
              title="Attach an image or paste one from your clipboard"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <button
              type={generationActive ? "button" : "submit"}
              onClick={generationActive ? onStop : undefined}
              disabled={!generationActive && (isLoading || !hasGenerationInput || !generationReady)}
              className="absolute bottom-3 right-3 inline-flex h-9 w-9 items-center justify-center bg-white text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40 sm:bottom-4 sm:right-4 sm:h-10 sm:w-10"
              aria-label={generationActive ? "Stop generation" : inputValid ? "Send context" : "Check hardware idea"}
              title={generationActive ? "Stop generation" : inputValid ? "Send context" : "Check hardware idea"}
            >
              {generationActive ? <Square className="h-4 w-4 fill-current" /> : isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
            </button>
          </div>

        </form>
        {started && <div className="h-[224px] shrink-0 md:hidden" aria-hidden="true" />}
      </div>
    </section>
  );
}
