import type { A2AJob } from "../use-admin-data";

export function withProjectResponseMetadata(ir: any, response: any) {
  if (!ir) return ir;
  const timingMetadata = generationTimingMetadataFromJob(response?.job);
  return {
    ...ir,
    assembly_metadata: {
      ...(ir.assembly_metadata || {}),
      project_id: ir.assembly_metadata?.project_id || response?.project_id,
      chat_id: ir.assembly_metadata?.chat_id || response?.chat_id,
      can_chat: Boolean(response?.can_chat ?? response?.canChat ?? ir.assembly_metadata?.can_chat ?? ir.assembly_metadata?.canChat),
      frontend_job_id: ir.assembly_metadata?.frontend_job_id || response?.job_id,
      source_prompt: ir.assembly_metadata?.source_prompt || response?.prompt,
      ...timingMetadata,
    },
  };
}

export function timestampMs(value: any): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

export function durationSecondsBetween(startValue: any, endValue: any): number | null {
  const start = timestampMs(startValue);
  const end = timestampMs(endValue);
  if (start === null || end === null || end < start) return null;
  return Math.max(1, Math.round((end - start) / 1000));
}

export function generationTimingMetadataFromJob(job: A2AJob | null | undefined): Record<string, any> {
  const seconds = durationSecondsBetween(job?.started_at, job?.completed_at);
  if (seconds === null) return {};
  return {
    total_generation_time_seconds: seconds,
    total_generation_started_at: job?.started_at || null,
    total_generation_completed_at: job?.completed_at || null,
  };
}

export function formatDurationSeconds(value: any) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  const totalSeconds = Math.max(1, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  if (hours) return `${hours}h ${minutes}m ${remainingSeconds}s`;
  if (minutes) return `${minutes}m ${remainingSeconds}s`;
  return `${remainingSeconds}s`;
}

export function projectIdFromIR(ir: any) {
  return ir?.assembly_metadata?.project_id || null;
}

export function chatIdFromIR(ir: any) {
  return ir?.assembly_metadata?.chat_id || null;
}

export function canChatWithProjectIR(ir: any) {
  return Boolean(ir?.assembly_metadata?.can_chat ?? ir?.assembly_metadata?.canChat);
}

export function chatIdFromJob(job: A2AJob) {
  const rawChatId = job.payload?.chat_id || job.result_summary?.chat_id;
  return typeof rawChatId === "string" ? rawChatId.trim() : "";
}
