import type { A2AJob } from "../use-admin-data";
import type { AgentPipelineEvent, AgentPipelineProgress, AgentPipelineStep, ChatMessage } from "../types";
import {
  CHAT_DIAGNOSTIC_CHARACTER_LIMIT,
  defaultAgentPipelineSteps,
  optionalImagePipelineStep,
  PIPELINE_STALE_AFTER_MS,
  PIPELINE_UI_HEARTBEAT_MS,
} from "../workspace-constants";
import { chatTimestamp } from "./chat-ids";
import { formatDurationSeconds, timestampMs } from "./project-metadata";

export function normalizeAgentPipelineStep(value: any): AgentPipelineStep | null {
  if (!value || typeof value !== "object") return null;
  const id = typeof value.id === "string" && value.id.trim() ? value.id.trim() : "";
  const label = typeof value.label === "string" && value.label.trim() ? value.label.trim() : "";
  if (!id || !label) return null;
  return {
    id,
    label,
    agent: typeof value.agent === "string" && value.agent.trim() ? value.agent.trim() : label,
    description: typeof value.description === "string" ? value.description : "",
    duration_ms: Number.isFinite(Number(value.duration_ms)) ? Math.max(1000, Number(value.duration_ms)) : undefined,
    optional: Boolean(value.optional),
  };
}

export function normalizeAgentPipelineSteps(value: any): AgentPipelineStep[] {
  const rawSteps = Array.isArray(value?.steps) ? value.steps : Array.isArray(value) ? value : [];
  const steps = rawSteps.map(normalizeAgentPipelineStep).filter(Boolean) as AgentPipelineStep[];
  return steps.length ? steps : defaultAgentPipelineSteps;
}

export function normalizeAgentPipelineProgress(value: any): AgentPipelineProgress | null {
  if (!value || typeof value !== "object") return null;
  const steps = normalizeAgentPipelineSteps(value.steps);
  const events = normalizeAgentPipelineEvents(value.events);
  return {
    startedAt: typeof value.startedAt === "string" && value.startedAt ? value.startedAt : chatTimestamp(),
    steps,
    currentStepIndex: Math.min(Math.max(Number(value.currentStepIndex || 0), 0), Math.max(steps.length - 1, 0)),
    estimated: value.estimated !== false,
    synced: Boolean(value.synced),
    jobId: typeof value.jobId === "string" ? value.jobId : null,
    events,
    uiUpdatedAt: typeof value.uiUpdatedAt === "string" && value.uiUpdatedAt ? value.uiUpdatedAt : chatTimestamp(),
  };
}

export function normalizeAgentPipelineEvents(value: any): AgentPipelineEvent[] {
  const rawEvents = Array.isArray(value) ? value : [];
  return rawEvents
    .map((event) => {
      if (!event || typeof event !== "object" || typeof event.step_id !== "string") return null;
      return {
        workflow: typeof event.workflow === "string" ? event.workflow : undefined,
        step_id: event.step_id,
        status: typeof event.status === "string" ? event.status : "started",
        agent: typeof event.agent === "string" ? event.agent : undefined,
        label: typeof event.label === "string" ? event.label : undefined,
        description: typeof event.description === "string" ? event.description : undefined,
        observed_at: typeof event.observed_at === "string" ? event.observed_at : undefined,
        details: event.details && typeof event.details === "object" ? event.details : undefined,
      };
    })
    .filter(Boolean) as AgentPipelineEvent[];
}

export function stepsForPipelineRun(steps: AgentPipelineStep[], includeImage: boolean) {
  const normalized = steps.length ? steps : defaultAgentPipelineSteps;
  const baseSteps = normalized.filter((step) => !step.optional || includeImage);
  if (includeImage && !baseSteps.some((step) => step.id === optionalImagePipelineStep.id)) {
    return [...baseSteps, optionalImagePipelineStep];
  }
  return baseSteps;
}

export function createAgentPipelineProgress(
  steps: AgentPipelineStep[],
  includeImage: boolean,
  startedAt: string = chatTimestamp(),
  jobId: string | null = null
): AgentPipelineProgress {
  return {
    startedAt,
    steps: stepsForPipelineRun(steps, includeImage),
    currentStepIndex: 0,
    estimated: true,
    synced: false,
    jobId,
    events: [],
    uiUpdatedAt: startedAt,
  };
}

export function shouldPulsePipelineUi(progress: AgentPipelineProgress, nowMs: number) {
  const lastUiMs = timestampMs(progress.uiUpdatedAt);
  return lastUiMs === null || nowMs - lastUiMs >= PIPELINE_UI_HEARTBEAT_MS;
}

export function agentPipelineStepIndex(progress: AgentPipelineProgress, nowMs: number) {
  const startedMs = Date.parse(progress.startedAt);
  const elapsedMs = Math.max(0, nowMs - (Number.isNaN(startedMs) ? nowMs : startedMs));
  let accumulatedMs = 0;
  for (let index = 0; index < progress.steps.length; index += 1) {
    accumulatedMs += progress.steps[index].duration_ms || 5500;
    if (elapsedMs < accumulatedMs) return index;
  }
  return Math.max(0, progress.steps.length - 1);
}

export function advanceAgentPipelineProgress(progress: AgentPipelineProgress, nowMs: number): AgentPipelineProgress {
  if (progress.synced || progress.estimated === false) {
    return shouldPulsePipelineUi(progress, nowMs)
      ? { ...progress, uiUpdatedAt: new Date(nowMs).toISOString() }
      : progress;
  }
  const currentStepIndex = agentPipelineStepIndex(progress, nowMs);
  if (currentStepIndex !== progress.currentStepIndex) {
    return { ...progress, currentStepIndex, uiUpdatedAt: new Date(nowMs).toISOString() };
  }
  return shouldPulsePipelineUi(progress, nowMs)
    ? { ...progress, uiUpdatedAt: new Date(nowMs).toISOString() }
    : progress;
}

export function pipelineEventCursor(events: AgentPipelineEvent[] | undefined) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  const lastEvent = normalizedEvents[normalizedEvents.length - 1];
  return [
    normalizedEvents.length,
    lastEvent?.observed_at || "",
    lastEvent?.step_id || "",
    lastEvent?.status || "",
  ].join(":");
}

export function isFailedPipelineStatus(status: any) {
  return String(status || "").toLowerCase().includes("failed");
}

export function isCompletedPipelineStatus(status: any) {
  const normalized = String(status || "").toLowerCase();
  return normalized === "completed" || normalized === "provider_response_received";
}

export function failedPipelineEvent(events: AgentPipelineEvent[] | undefined) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  return [...normalizedEvents].reverse().find((event) => isFailedPipelineStatus(event.status)) || null;
}

export function pipelineEventsFromWorkerTask(task: any): AgentPipelineEvent[] {
  if (!Array.isArray(task?.progress)) return [];
  return normalizeAgentPipelineEvents(
    task.progress.map((item: any) => item?.metadata?.pipeline_event).filter(Boolean),
  );
}

export function compactDiagnosticText(value: any, limit: number = CHAT_DIAGNOSTIC_CHARACTER_LIMIT) {
  const original = String(value || "").trim();
  if (!original) return "";

  const normalized = original
    .replace(/\r\n/g, "\n")
    .replace(/https:\/\/errors\.pydantic\.dev\/\S+/g, "")
    .replace(/,\s*input_value=(?:'[^']*'|"[^"]*"|[^\]\n]*)/g, "")
    .replace(/,\s*input_type=[^\]\n]+/g, "")
    .replace(/\[type=([^,\]\s]+)[^\]]*\]/g, "[type=$1]");

  const lines = normalized
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .filter((line) => !/^for further information visit/i.test(line))
    .filter((line) => !/^input_(value|type)=/i.test(line));
  const text = lines.join("\n") || original;

  if (text.length <= limit) return text;
  const clipped = text.slice(0, limit).replace(/\s+\S*$/, "").trimEnd();
  return `${clipped || text.slice(0, limit).trimEnd()}...`;
}

export function generationFailureChatMessage(message: string, includeJobsHint = false) {
  const compact = compactDiagnosticText(message);
  const content = compact
    ? /^generation failed\b/i.test(compact)
      ? compact
      : `Generation failed: ${compact}`
    : "Generation failed.";
  return includeJobsHint ? `${content}\nFull diagnostics are available in Jobs.` : content;
}

export function jobFailureMessage(job: A2AJob) {
  const event = failedPipelineEvent(job.progress_events);
  const eventDetails = event?.details || {};
  const reason = job.error || eventDetails.error || eventDetails.reason || eventDetails.message;
  if (reason) return String(reason);
  if (event?.label) return `${event.label} failed.`;
  return "Generation failed.";
}

export function terminalJobMessagePatch(job: A2AJob, message: ChatMessage): Partial<Omit<ChatMessage, "id">> | null {
  if (message.status !== "loading") return null;
  if (["cancelled", "canceled"].includes(String(job.status || "").toLowerCase())) {
    return {
      content: "Generation stopped by you.",
      status: "cancelled",
    };
  }
  if (job.status === "failed") {
    return {
      content: generationFailureChatMessage(jobFailureMessage(job), true),
      status: "error",
    };
  }
  if (job.status === "succeeded") {
    const title = job.result_summary?.title || "Project";
    const projectId = typeof job.result_summary?.project_id === "string" ? job.result_summary.project_id : null;
    return {
      content: `${title} is ready.`,
      status: "success",
      projectId,
    };
  }
  return null;
}

export function patchChangesMessage(message: ChatMessage, patch: Partial<Omit<ChatMessage, "id">> | null) {
  if (!patch) return false;
  return Object.entries(patch).some(([key, value]) => (message as any)[key] !== value);
}

export function sameAgentPipelineProgress(left: AgentPipelineProgress | null | undefined, right: AgentPipelineProgress | null | undefined) {
  if (left === right) return true;
  if (!left || !right) return false;
  return (
    left.currentStepIndex === right.currentStepIndex &&
    left.estimated === right.estimated &&
    Boolean(left.synced) === Boolean(right.synced) &&
    (left.jobId || null) === (right.jobId || null) &&
    pipelineEventCursor(left.events) === pipelineEventCursor(right.events)
  );
}

export function progressFromJobEvents(
  job: A2AJob | null,
  fallback: AgentPipelineProgress,
  includeImage: boolean
): AgentPipelineProgress | null {
  const events = normalizeAgentPipelineEvents(job?.progress_events);
  if (!events.length) return null;
  const previousEvents = normalizeAgentPipelineEvents(fallback.events);
  if (fallback.synced && previousEvents.length > events.length) return fallback;
  const steps = stepsForPipelineRun(fallback.steps, includeImage);
  const indexByStep = new Map(steps.map((step, index) => [step.id, index]));
  let currentStepIndex = fallback.currentStepIndex;
  for (const event of events) {
    const eventIndex = indexByStep.get(event.step_id);
    if (eventIndex === undefined) continue;
    if (isCompletedPipelineStatus(event.status) || event.status === "skipped") {
      currentStepIndex = Math.min(eventIndex + 1, Math.max(steps.length - 1, 0));
    } else {
      currentStepIndex = eventIndex;
    }
  }
  if (fallback.synced && previousEvents.length >= events.length && currentStepIndex < fallback.currentStepIndex) {
    return fallback;
  }
  return {
    ...fallback,
    startedAt: job?.started_at || fallback.startedAt,
    steps,
    currentStepIndex,
    estimated: false,
    synced: true,
    jobId: job?.job_id || fallback.jobId || null,
    events,
    uiUpdatedAt: chatTimestamp(),
  };
}

export function mergeMessagePipelineProgressFromJob(
  message: ChatMessage,
  job: A2AJob,
  seedProgress: AgentPipelineProgress,
  includeImage: boolean
) {
  const nextProgress = progressFromJobEvents(job, message.pipelineProgress || seedProgress, includeImage);
  const terminalPatch = terminalJobMessagePatch(job, message);
  const progressChanged = Boolean(nextProgress && !sameAgentPipelineProgress(message.pipelineProgress, nextProgress));
  const patchChanged = patchChangesMessage(message, terminalPatch);
  if (!progressChanged && !patchChanged) return message;
  return {
    ...message,
    ...(terminalPatch || {}),
    pipelineProgress: nextProgress || message.pipelineProgress || null,
    timestamp: chatTimestamp(),
  };
}

export function progressIncludesImageStep(progress: AgentPipelineProgress | null | undefined) {
  return Boolean(progress?.steps?.some((step) => step.id === optionalImagePipelineStep.id || step.optional));
}

export function mergeMessagesWithJobs(
  messages: ChatMessage[],
  jobsById: Map<string, A2AJob>,
  includeImageDefault: boolean
) {
  let changed = false;
  const nextMessages = messages.map((message) => {
    const jobId = message.pipelineProgress?.jobId;
    if (!jobId) return message;
    const job = jobsById.get(jobId);
    if (!job || !message.pipelineProgress) return message;
    const includeImage = includeImageDefault || progressIncludesImageStep(message.pipelineProgress);
    const nextMessage = mergeMessagePipelineProgressFromJob(message, job, message.pipelineProgress, includeImage);
    if (nextMessage !== message) changed = true;
    return nextMessage;
  });
  return changed ? nextMessages : messages;
}

export function advancePipelineMessages(messages: ChatMessage[], nowMs: number) {
  let changed = false;
  const nextMessages = messages.map((message) => {
    if (message.status !== "loading" || !message.pipelineProgress) return message;
    const nextProgress = advanceAgentPipelineProgress(message.pipelineProgress, nowMs);
    if (nextProgress === message.pipelineProgress) return message;
    changed = true;
    return { ...message, pipelineProgress: nextProgress };
  });
  return changed ? nextMessages : messages;
}

export function pipelineEventTimestampMs(event: AgentPipelineEvent | null | undefined): number | null {
  return timestampMs(event?.observed_at);
}

export function latestPipelineEvent(events: AgentPipelineEvent[]) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  return normalizedEvents[normalizedEvents.length - 1] || null;
}

export function pipelineStepForEvent(progress: AgentPipelineProgress, event: AgentPipelineEvent | null | undefined) {
  if (!event) return null;
  return progress.steps.find((step) => step.id === event.step_id) || null;
}

export function activePipelineStep(progress: AgentPipelineProgress) {
  const events = normalizeAgentPipelineEvents(progress.events);
  const lastEvent = latestPipelineEvent(events);
  const stepFromEvent = pipelineStepForEvent(progress, lastEvent);
  if (lastEvent && !isCompletedPipelineStatus(lastEvent.status) && lastEvent.status !== "skipped") {
    return stepFromEvent || progress.steps[progress.currentStepIndex] || progress.steps[0] || null;
  }
  return progress.steps[progress.currentStepIndex] || stepFromEvent || progress.steps[0] || null;
}

export function completedPipelineStepCount(progress: AgentPipelineProgress) {
  const completed = new Set<string>();
  normalizeAgentPipelineEvents(progress.events).forEach((event) => {
    if (isCompletedPipelineStatus(event.status) || event.status === "skipped") completed.add(event.step_id);
    if (isFailedPipelineStatus(event.status)) completed.delete(event.step_id);
  });
  if (completed.size) return completed.size;
  return progress.estimated ? Math.max(0, progress.currentStepIndex) : 0;
}

export function pipelineStepStatus(
  progress: AgentPipelineProgress,
  step: AgentPipelineStep,
  activeStepId: string | null,
  isRunning: boolean = false
) {
  const events = normalizeAgentPipelineEvents(progress.events);
  const stepEvents = events.filter((event) => event.step_id === step.id);
  const lastStepEvent = stepEvents[stepEvents.length - 1];
  // A failed attempt may be followed by a retry while the job remains active.
  // Keep the current step neutral until the job itself reaches a failed state.
  if (isRunning && activeStepId === step.id) return "active";
  if (isFailedPipelineStatus(lastStepEvent?.status)) return "failed";
  if (lastStepEvent?.status === "skipped") return "skipped";
  if (isCompletedPipelineStatus(lastStepEvent?.status)) return "completed";
  if (activeStepId === step.id) return "active";
  return "pending";
}

export function formatPipelineAge(value?: string | null, nowMs: number = Date.now()) {
  const ms = timestampMs(value);
  if (ms === null) return "-";
  return formatDurationSeconds(Math.max(1, Math.round((nowMs - ms) / 1000)));
}

export function formatPipelineDetails(details: Record<string, any> | undefined) {
  if (!details || typeof details !== "object") return "";
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 3)
    .map(([key, value]) => {
      const rawText = typeof value === "string" ? value : JSON.stringify(value);
      const text = typeof rawText === "string" ? rawText : String(value);
      return `${key.replace(/_/g, " ")}: ${text.length > 80 ? `${text.slice(0, 77)}...` : text}`;
    })
    .join(" / ");
}
