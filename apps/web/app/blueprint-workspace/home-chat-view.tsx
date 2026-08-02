"use client";

import type { ChangeEventHandler, ClipboardEventHandler, FormEventHandler, ReactNode, RefObject } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Cpu,
  Info,
  KeyRound,
  Paperclip,
  RefreshCw,
  Settings,
  Square,
  X,
} from "lucide-react";

type HomeChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  status?: "idle" | "loading" | "success" | "error" | "cancelled";
  timestamp: string;
  projectId?: string | null;
  pipelineProgress?: unknown;
  imagePreview?: string | null;
};

type PendingContext = {
  basePrompt: string;
  questions: Array<{
    id: string;
    label: string;
    question: string;
    placeholder: string;
    suggestions: string[];
  }>;
  answers: Record<string, string>;
};

type HomeChatProjectObject = {
  projectId: string;
  title: string;
  description: string;
  partsCount: number;
  namespaceCount?: number | null;
  namespaces?: string[];
  revision?: number | string | null;
};

type HomeChatViewProps = {
  started: boolean;
  messages: HomeChatMessage[];
  endRef: RefObject<HTMLDivElement>;
  renderPipelineProgress: (message: HomeChatMessage) => ReactNode;
  examples: string[];
  onSelectExample: (example: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  pendingContext: PendingContext | null;
  onContextAnswer: (questionId: string, answer: string) => void;
  onClearContext: () => void;
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
  imageInputRef: RefObject<HTMLInputElement>;
  onImageChange: ChangeEventHandler<HTMLInputElement>;
  onImagePaste: ClipboardEventHandler<HTMLTextAreaElement>;
  projectObject?: HomeChatProjectObject | null;
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
  examples,
  onSelectExample,
  onSubmit,
  pendingContext,
  onContextAnswer,
  onClearContext,
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
  projectObject = null,
}: HomeChatViewProps) {
  return (
    <section
      className={`${
        !started
          ? "fixed bottom-[224px] left-0 right-0 top-[3.75rem] z-10 max-w-none md:static md:inset-auto md:z-auto md:w-full md:max-w-none"
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

      <div className={`${started ? "mt-0" : "mt-4 sm:mt-5"} flex min-h-0 flex-1 flex-col overflow-hidden border-y border-[#2c2f37] bg-[#111216] text-left shadow-2xl shadow-black/30`}>
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
                    </div>
                    <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
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
            {projectObject && (
              <article className="border border-cyan-300/25 bg-cyan-300/5 px-4 py-4" aria-label="Generated project object">
                <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-cyan-200">
                      <CheckCircle className="h-3.5 w-3.5" />
                      Project object loaded
                    </div>
                    <h2 className="mt-2 break-anywhere text-sm font-semibold text-white">{projectObject.title}</h2>
                    <p className="mt-2 max-w-3xl break-anywhere text-xs leading-5 text-slate-400">{projectObject.description}</p>
                  </div>
                  <div className="shrink-0 text-right font-mono text-[10px] leading-5 text-slate-500">
                    <div>{projectObject.partsCount} parts</div>
                    {projectObject.namespaceCount !== null && projectObject.namespaceCount !== undefined && (
                      <div>{projectObject.namespaceCount} namespaces</div>
                    )}
                    {projectObject.revision !== null && projectObject.revision !== undefined && (
                      <div>revision {projectObject.revision}</div>
                    )}
                  </div>
                </div>
                <div className="mt-3 truncate border-t border-cyan-300/15 pt-3 font-mono text-[10px] text-slate-600" title={projectObject.projectId}>
                  {projectObject.projectId}
                </div>
                {projectObject.namespaces?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {projectObject.namespaces.map((namespace) => (
                      <span key={namespace} className="border border-cyan-300/15 px-2 py-1 text-[10px] text-slate-500">
                        {namespace}
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            )}
            <div ref={endRef} />
          </div>
        )}

        {!started && (
          <div className="mt-auto shrink-0 bg-[#111216] px-3 py-3 sm:border-t sm:border-[#2c2f37] sm:px-4">
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

        <form onSubmit={onSubmit} className="fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain border-y border-[#2c2f37] bg-[#141519]/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:p-4 md:sticky md:bottom-0 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible md:border-b-0 md:pb-4">
          {pendingContext && (
            <div className="mb-3 border border-cyan-300/25 bg-cyan-300/5 p-3 sm:p-4">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <div className="inline-flex h-8 items-center gap-2 border border-cyan-300/30 bg-cyan-300/10 px-3 text-[10px] font-black uppercase tracking-[0.18em] text-cyan-100">
                  <Info className="h-3.5 w-3.5" />
                  Human Context Checkpoint
                </div>
                <div className="min-w-0 break-anywhere text-xs leading-5 text-slate-500">Optional: answer what matters, or use safe prototype defaults.</div>
              </div>
              <div className="break-anywhere mt-3 max-h-24 overflow-y-auto border border-[#2c2f37] bg-[#0f1014] px-3 py-2 text-xs leading-5 text-slate-400">
                {pendingContext.basePrompt}
              </div>
              <div className="mt-3 grid max-h-[42dvh] gap-3 overflow-y-auto pr-1 md:max-h-none md:grid-cols-3 md:overflow-visible md:pr-0">
                {pendingContext.questions.map((question) => (
                  <label key={question.id} className="block min-w-0 border border-[#2c2f37] bg-[#111216] p-3">
                    <span className="break-anywhere text-[10px] font-black uppercase tracking-[0.16em] text-cyan-200">{question.label}</span>
                    <span className="break-anywhere mt-2 block text-xs leading-5 text-slate-300">{question.question}</span>
                    <textarea
                      value={pendingContext.answers[question.id] || ""}
                      onChange={(event) => onContextAnswer(question.id, event.target.value)}
                      placeholder={question.placeholder}
                      className="mt-3 min-h-[72px] w-full resize-none border border-[#2c2f37] bg-black px-3 py-2 text-xs leading-5 text-white outline-none placeholder:text-slate-700 focus:border-cyan-300 sm:min-h-[92px]"
                    />
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {question.suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => onContextAnswer(question.id, suggestion)}
                          className="break-anywhere max-w-full border border-[#2c2f37] px-2 py-1 text-left text-[10px] font-bold text-slate-500 hover:border-cyan-300 hover:text-cyan-100"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </label>
                ))}
              </div>
              <div className="mt-3 grid gap-2 sm:flex sm:flex-wrap sm:items-center">
                <button
                  type="submit"
                  disabled={isLoading || !generationReady}
                  className="inline-flex h-10 items-center justify-center gap-2 bg-white px-4 text-xs font-black uppercase text-black hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                  Build with context
                </button>
                <button
                  type="submit"
                  name="humanContextAction"
                  value="use-defaults"
                  disabled={isLoading || !generationReady}
                  className="inline-flex h-10 items-center justify-center gap-2 border border-cyan-300/40 px-4 text-xs font-black uppercase text-cyan-100 hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ArrowRight className="h-4 w-4" />
                  Skip — use defaults
                </button>
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={onClearContext}
                  className="inline-flex h-10 items-center justify-center gap-2 border border-[#2c2f37] px-4 text-xs font-black uppercase text-slate-400 hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Edit request
                </button>
              </div>
            </div>
          )}

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
              placeholder={pendingContext ? "Add more context…" : "Describe the product, constraints, references, and outputs you need…"}
              aria-invalid={Boolean(notice)}
              aria-describedby={notice ? "generation-input-notice" : undefined}
              className={`${pendingContext ? "min-h-[72px] sm:min-h-[96px]" : "min-h-[98px] sm:min-h-[104px]"} w-full resize-none border border-[#2c2f37] bg-[#0f1014] py-3 pl-14 pr-14 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300 sm:py-4 sm:pl-16 sm:pr-16 sm:leading-7`}
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
