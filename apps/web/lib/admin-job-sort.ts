export type AdminJobSortMode =
  | "last_occurred_desc"
  | "last_occurred_asc"
  | "created_desc"
  | "created_asc";

export type SortableAdminJob = {
  job_id: string;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export const ADMIN_JOB_SORT_OPTIONS: Array<{ value: AdminJobSortMode; label: string }> = [
  { value: "last_occurred_desc", label: "Last occurred: recent" },
  { value: "last_occurred_asc", label: "Last occurred: oldest" },
  { value: "created_desc", label: "Created: newest" },
  { value: "created_asc", label: "Created: oldest" },
];

function timestampMs(value?: string | null): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const valueMs = new Date(value).getTime();
  return Number.isNaN(valueMs) ? null : valueMs;
}

export function adminJobLastOccurredMs(job: SortableAdminJob): number | null {
  const timestamps = [job.created_at, job.started_at, job.updated_at, job.completed_at]
    .map(timestampMs)
    .filter((value): value is number => value !== null);
  return timestamps.length ? Math.max(...timestamps) : null;
}

export function adminJobLastOccurredAt(job: SortableAdminJob): string | null {
  const occurredMs = adminJobLastOccurredMs(job);
  return occurredMs === null ? null : new Date(occurredMs).toISOString();
}

function compareOptionalTimestamps(left: number | null, right: number | null, ascending: boolean) {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return ascending ? left - right : right - left;
}

export function sortAdminJobs<T extends SortableAdminJob>(jobs: T[], mode: AdminJobSortMode): T[] {
  const ascending = mode.endsWith("_asc");
  const byCreated = mode.startsWith("created_");
  return [...jobs].sort((left, right) => {
    const leftTimestamp = byCreated ? timestampMs(left.created_at) : adminJobLastOccurredMs(left);
    const rightTimestamp = byCreated ? timestampMs(right.created_at) : adminJobLastOccurredMs(right);
    const timestampOrder = compareOptionalTimestamps(leftTimestamp, rightTimestamp, ascending);
    return timestampOrder || left.job_id.localeCompare(right.job_id);
  });
}
