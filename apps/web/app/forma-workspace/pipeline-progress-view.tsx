"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle, ChevronDown, Cpu, RefreshCw, Square } from "lucide-react";

import type { AgentPipelineProgress, ChatMessage } from "./types";
import {
  activePipelineStep,
  completedPipelineStepCount,
  formatPipelineAge,
  formatPipelineDetails,
  isCompletedPipelineStatus,
  isFailedPipelineStatus,
  latestPipelineEvent,
  normalizeAgentPipelineEvents,
  pipelineEventTimestampMs,
  pipelineStepStatus,
} from "./lib/agent-pipeline";
import { formatDurationSeconds, timestampMs } from "./lib/project-metadata";
import { defaultAgentPipelineSteps, PIPELINE_STALE_AFTER_MS } from "./workspace-constants";

export function PipelineStepDot({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "border-emerald-400 bg-emerald-400"
      : status === "failed"
        ? "border-rose-400 bg-rose-400"
        : status === "skipped"
          ? "border-slate-600 bg-slate-800"
          : status === "active"
            ? "border-cyan-300 bg-cyan-300"
            : "border-slate-700 bg-black";
  return <span className={`h-2.5 w-2.5 shrink-0 border ${tone}`} />;
}

export function AgentPipelineEventsDisclosure({
  eventCount,
  children,
}: {
  eventCount: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="group mt-3 border-t border-white/5 pt-3"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <ChevronDown className="h-3 w-3 shrink-0 -rotate-90 text-zinc-600 transition-transform group-open:rotate-0" />
          <span className="text-[10px] font-medium text-zinc-600">Recent events</span>
        </span>
        <span className="font-mono text-[10px] text-zinc-600">{eventCount}</span>
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

export function AgentPipelineProgressView({
  progress,
  status,
  compact = false,
  onStop,
  onReset,
  resetting = false,
}: {
  progress?: AgentPipelineProgress | null;
  status?: ChatMessage["status"];
  compact?: boolean;
  onStop?: () => void;
  onReset?: () => void;
  resetting?: boolean;
}) {
  if (!progress) return null;

  const steps = progress.steps.length ? progress.steps : defaultAgentPipelineSteps;
  const events = normalizeAgentPipelineEvents(progress.events);
  const lastEvent = latestPipelineEvent(events);
  const activeStep = activePipelineStep({ ...progress, steps });
  const activeStepId = activeStep?.id || null;
  const nowMs = Date.now();
  const startedMs = timestampMs(progress.startedAt);
  const elapsedSeconds = startedMs === null ? null : Math.max(1, Math.round((nowMs - startedMs) / 1000));
  const lastEventMs = pipelineEventTimestampMs(lastEvent);
  const quietMs = lastEventMs === null ? null : nowMs - lastEventMs;
  const isLoading = status === "loading";
  const isSuccess = status === "success";
  const isCancelled = status === "cancelled";
  // Progress events are an audit trail and may include a failed attempt that
  // the backend subsequently retries. Only the terminal message state means
  // the whole pipeline failed.
  const isError = status === "error";
  const waitingForFirstEvent = isLoading && !events.length && startedMs !== null && nowMs - startedMs >= PIPELINE_STALE_AFTER_MS;
  const backendQuiet = isLoading && quietMs !== null && quietMs >= PIPELINE_STALE_AFTER_MS;
  const completedCount = completedPipelineStepCount({ ...progress, steps });
  const progressPercent = Math.min(100, Math.max(6, Math.round((completedCount / Math.max(steps.length, 1)) * 100)));
  const visibleEvents = events.slice(compact ? -4 : -6);
  const signalLabel = isError
    ? "failed"
    : isCancelled
    ? "stopped"
    : isSuccess
    ? "completed"
    : progress.synced
    ? backendQuiet
      ? "waiting on provider"
      : "backend synced"
    : waitingForFirstEvent
      ? "starting"
      : "estimated";
  const signalTone = isError
    ? "border-rose-400/35 bg-rose-950/25 text-rose-200"
    : isCancelled
    ? "border-amber-300/35 bg-amber-950/20 text-amber-100"
    : isSuccess
    ? "border-emerald-300/35 bg-emerald-950/20 text-emerald-100"
    : backendQuiet || waitingForFirstEvent
    ? "border-emerald-500/25 bg-emerald-950/25 text-emerald-100"
    : progress.synced
      ? "border-emerald-500/25 bg-emerald-950/25 text-emerald-100"
      : "border-slate-500/25 bg-black/25 text-slate-400";

  return (
    <div className="mt-3 rounded-xl border border-white/5 bg-black/25 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-medium text-zinc-500">Agent pipeline</span>
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium ${signalTone}`}>
              {isError ? <AlertTriangle className="h-3 w-3" /> : isCancelled ? <Square className="h-3 w-3 fill-current" /> : isLoading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
              {signalLabel}
            </span>
          </div>
          {progress.jobId && (
            <div className="mt-1 truncate font-mono text-[10px] text-zinc-600">{progress.jobId}</div>
          )}
        </div>
        <div className="flex shrink-0 items-start gap-2">
          {isLoading && onStop && (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-amber-300/40 px-2 text-[10px] font-medium text-amber-100 transition-colors hover:bg-amber-300/10"
              aria-label="Stop agent pipeline"
              title="Stop agent pipeline"
            >
              <Square className="h-3 w-3 fill-current" />
              Stop
            </button>
          )}
          {isError && onReset && (
            <button
              type="button"
              onClick={onReset}
              disabled={resetting}
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 text-[10px] font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:cursor-wait disabled:opacity-60"
              aria-label="Reset failed generation job"
              title="Reset failed generation job and try again"
            >
              <RefreshCw className={`h-3 w-3 ${resetting ? "animate-spin" : ""}`} />
              {resetting ? "Resetting" : "Reset job"}
            </button>
          )}
          <div className="text-right">
            <div className="font-mono text-[11px] font-semibold text-zinc-300">{completedCount}/{steps.length}</div>
            <div className="text-[10px] text-zinc-600">{formatDurationSeconds(elapsedSeconds)}</div>
          </div>
        </div>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#111216]">
        <div
          className={`h-full rounded-full ${isError ? "bg-rose-300" : isCancelled ? "bg-amber-300" : "bg-emerald-400"} ${isLoading ? "animate-pulse" : ""}`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <div className="mt-3 flex min-w-0 items-start gap-2 rounded-lg border border-white/5 bg-[#111216] p-3">
        {isError ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" /> : isCancelled ? <Square className="mt-0.5 h-4 w-4 shrink-0 fill-current text-amber-300" /> : isLoading ? <RefreshCw className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-emerald-400" /> : <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400" />}
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-zinc-100">{activeStep?.label || "Preparing job"}</div>
          <div className="mt-1 truncate text-[11px] font-medium text-emerald-400">{activeStep?.agent || "Forma runtime"}</div>
          {activeStep?.description && !compact && (
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-zinc-500">{activeStep.description}</div>
          )}
          {lastEvent && (
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-zinc-500">
              <span>Last: {lastEvent.label || lastEvent.step_id}</span>
              <span>{String(lastEvent.status).replace(/_/g, " ")}</span>
              <span>{formatPipelineAge(lastEvent.observed_at, nowMs)} ago</span>
            </div>
          )}
        </div>
      </div>

      {(backendQuiet || waitingForFirstEvent) && (
        <div className="mt-2 flex gap-2 rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-2 text-[11px] leading-4 text-emerald-100">
          <RefreshCw className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" />
          <span>
            {events.length
              ? `Still working. The active provider or backend call has been running for ${formatDurationSeconds(Math.round((quietMs || 0) / 1000))} since the last progress update.`
              : "Still starting. The job poller is active and waiting for the first backend progress update."}
          </span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {steps.map((step) => (
          <span
            key={step.id}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-[#111216] px-2 py-1 text-[10px] text-zinc-500"
            title={`${step.agent}: ${step.label}`}
          >
            <PipelineStepDot status={pipelineStepStatus({ ...progress, steps }, step, activeStepId, isLoading)} />
            <span className="max-w-[120px] truncate">{step.label}</span>
          </span>
        ))}
      </div>

      {!isLoading && (
        <AgentPipelineEventsDisclosure eventCount={events.length}>
          {visibleEvents.length ? (
            <div className="space-y-1.5">
              {visibleEvents.map((event, index) => {
                const details = formatPipelineDetails(event.details);
                return (
                  <div key={`${event.step_id}-${event.status}-${event.observed_at || index}`} className="min-w-0 rounded-lg border border-white/5 bg-[#0f1014] px-2 py-1.5">
                    <div className="flex min-w-0 flex-wrap items-center gap-2 text-[10px]">
                      <span className="max-w-[160px] truncate font-medium text-zinc-300">{event.label || event.step_id}</span>
                      <span className={`${isFailedPipelineStatus(event.status) ? "text-rose-300" : isCompletedPipelineStatus(event.status) ? "text-emerald-300" : "text-emerald-400"}`}>
                        {String(event.status).replace(/_/g, " ")}
                      </span>
                      <span className="text-zinc-600">{formatPipelineAge(event.observed_at, nowMs)} ago</span>
                    </div>
                    {details && !compact && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-zinc-500">{details}</div>}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-white/5 bg-[#0f1014] px-2 py-2 text-[11px] leading-4 text-zinc-500">
              Polling job metadata. Backend pipeline events will appear here as agents report progress.
            </div>
          )}
        </AgentPipelineEventsDisclosure>
      )}
    </div>
  );
}
