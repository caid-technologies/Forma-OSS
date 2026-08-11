"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AlertTriangle,
  CheckCircle,
  Cpu,
  Database,
  Download,
  Eye,
  FileArchive,
  FileSpreadsheet,
  History,
  Info,
  RefreshCw,
  Sparkles,
  Terminal,
} from "lucide-react";

import {
  type A2AJob,
  type AgentPipelineEvent,
  type BackendLogs,
  type JobMetricBucket,
  type JobMetrics,
  type JobMetricsWindow,
} from "./use-admin-data";
import {
  ADMIN_JOB_SORT_OPTIONS,
  adminJobLastOccurredAt,
  sortAdminJobs,
  type AdminJobSortMode,
} from "../../lib/admin-job-sort";
import CopyButton from "../../components/copy-button";

const DEFAULT_LOG_POLL_INTERVAL_MS = 5000;

type ContributionInventory = {
  count: number;
  files: Array<{
    file_number: number;
    component_count: number;
    net_count: number;
  }>;
};

export function ContributionExportPanel({
  apiUrl,
  getHeaders,
  readError,
}: {
  apiUrl: string;
  getHeaders: () => HeadersInit | Promise<HeadersInit>;
  readError: (response: Response) => Promise<string>;
}) {
  const [inventory, setInventory] = useState<ContributionInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<"xlsx" | "zip" | null>(null);

  const fetchInventory = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/admin/contribution-exports/inventory`, {
        headers: await getHeaders(),
        signal,
      });
      if (!response.ok) throw new Error(await readError(response));
      setInventory(await response.json());
    } catch (fetchError) {
      if (fetchError instanceof DOMException && fetchError.name === "AbortError") return;
      setError(fetchError instanceof Error ? fetchError.message : "Unable to load contribution exports.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [apiUrl, getHeaders, readError]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchInventory(controller.signal);
    return () => controller.abort();
  }, [fetchInventory]);

  const downloadExport = async (format: "xlsx" | "zip") => {
    setExportingFormat(format);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/admin/contribution-exports?format=${format}`, {
        headers: await getHeaders(),
      });
      if (!response.ok) throw new Error(await readError(response));
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
        || `forma-anonymized-projects.${format}`;
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Unable to download the contribution export.");
    } finally {
      setExportingFormat(null);
    }
  };

  const files = inventory?.files || [];
  const exportableCount = inventory?.count || 0;

  return (
    <section className="mb-6 border border-[#2c2f37] bg-[#17181d] p-4 sm:p-5">
      <div className="flex flex-col gap-4 border-b border-[#2a2c33] pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Download className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-black uppercase text-white">Opted-in data exports</h2>
          </div>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-500">
            Download every active project across all users except accounts that opted out. User and project data is anonymized when the export is generated.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void downloadExport("xlsx")}
            disabled={!exportableCount || Boolean(exportingFormat)}
            className="flex items-center gap-2 border border-[#34363f] px-3 py-2 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FileSpreadsheet className="h-4 w-4" />
            {exportingFormat === "xlsx" ? "Preparing..." : "Excel"}
          </button>
          <button
            type="button"
            onClick={() => void downloadExport("zip")}
            disabled={!exportableCount || Boolean(exportingFormat)}
            className="flex items-center gap-2 border border-[#34363f] px-3 py-2 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FileArchive className="h-4 w-4" />
            {exportingFormat === "zip" ? "Preparing..." : "ZIP"}
          </button>
        </div>
      </div>

      <div className="my-4 grid gap-2 sm:grid-cols-2">
        <JobMetric label="Eligible projects" value={inventory?.count ?? "-"} />
        <JobMetric label="Anonymization" value="At download" />
      </div>

      {error && (
        <div className="mb-4 flex gap-2 border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !inventory ? (
        <div className="border border-[#2a2c33] p-4 text-xs text-slate-500">Loading eligible projects...</div>
      ) : files.length ? (
        <div className="space-y-2">
          {files.slice(0, 25).map((file) => (
              <div key={file.file_number} className="flex flex-col gap-2 border border-[#2a2c33] bg-[#141519] p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-slate-300">Eligible project {file.file_number}</span>
                  <span className="border border-emerald-500/30 px-2 py-1 text-[10px] font-black uppercase text-emerald-300">Ready</span>
                </div>
                <p className="text-[11px] leading-5 text-slate-500">
                  {file.component_count} components · {file.net_count} nets
                </p>
              </div>
          ))}
          {files.length > 25 && (
            <p className="text-[11px] text-slate-600">Showing 25 of {files.length} eligible projects.</p>
          )}
        </div>
      ) : (
        <div className="border border-[#2a2c33] p-4 text-xs leading-5 text-slate-500">
          No active projects belong to users who have not opted out.
        </div>
      )}
    </section>
  );
}

function normalizeAdminPipelineEvents(value: any): AgentPipelineEvent[] {
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

function isFailedAdminPipelineStatus(status: any) {
  return String(status || "").toLowerCase().includes("failed");
}

function isCompletedAdminPipelineStatus(status: any) {
  const normalized = String(status || "").toLowerCase();
  return normalized === "completed" || normalized === "provider_response_received";
}

function chatIdFromJob(job: A2AJob) {
  const rawChatId = job.payload?.chat_id || job.result_summary?.chat_id;
  return typeof rawChatId === "string" ? rawChatId.trim() : "";
}

function timestampMs(value: any): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

function durationSecondsBetween(startValue: any, endValue: any): number | null {
  const start = timestampMs(startValue);
  const end = timestampMs(endValue);
  if (start === null || end === null || end < start) return null;
  return Math.max(1, Math.round((end - start) / 1000));
}

function formatDurationSeconds(value: any) {
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

export function LogsPanel({
  logs,
  loading,
  error,
  lastUpdatedAt,
  onRefresh,
  pollIntervalMs = DEFAULT_LOG_POLL_INTERVAL_MS,
  compact = false,
}: {
  logs: BackendLogs | null;
  loading: boolean;
  error: string | null;
  lastUpdatedAt: string | null;
  onRefresh: () => void;
  pollIntervalMs?: number;
  compact?: boolean;
}) {
  const lines = Array.isArray(logs?.lines) ? logs.lines : [];
  const visibleLines = compact ? lines.slice(-10) : lines;
  const enabled = logs?.enabled !== false;
  const message = logs?.message || (enabled ? null : "Backend logging is not enabled.");

  return (
    <div className={`min-w-0 overflow-x-hidden ${compact ? "border border-[#2c2f37] bg-[#17181d] p-4" : "h-full min-h-0 overflow-hidden bg-[#141519] p-4 sm:p-6"}`}>
      <div className={`${compact ? "mb-3 pb-3" : "mb-4 pb-4"} flex items-start justify-between gap-4 border-b border-[#2a2c33]`}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-black uppercase text-white">Backend Logs</h2>
          </div>
          {!compact && (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Showing recent backend and uvicorn log lines. Polling every {Math.round(pollIntervalMs / 1000)}s while this tab is open.
            </p>
          )}
          {lastUpdatedAt && (
            <p className="mt-1 text-[11px] leading-5 text-slate-600">Updated {formatJobTime(lastUpdatedAt)}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="flex h-10 w-10 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
          title="Refresh logs"
          aria-label="Refresh logs"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {!compact && (
        <div className="mb-3 grid gap-2 text-[11px] sm:grid-cols-4">
          <JobMetric label="File" value={logs?.path || "-"} />
          <JobMetric label="Size" value={formatBytes(Number(logs?.size_bytes || 0))} />
          <JobMetric label="Lines" value={logs?.line_count ?? visibleLines.length} />
          <JobMetric label="Truncated" value={logs?.truncated ? "yes" : "no"} />
        </div>
      )}

      {error && (
        <div className="mb-3 flex gap-2 border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="mb-3 flex gap-2 border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{message}</span>
        </div>
      )}

      <div className={`${compact ? "max-h-[260px]" : "h-[calc(100%-132px)] min-h-[360px]"} overflow-auto border border-[#25272e] bg-black p-3`}>
        {visibleLines.length ? (
          <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-slate-300">
            {visibleLines.join("\n")}
          </pre>
        ) : (
          <div className="flex h-full min-h-32 items-center justify-center text-center text-xs leading-5 text-slate-600">
            {loading ? "Loading logs..." : "No backend log lines available."}
          </div>
        )}
      </div>
    </div>
  );
}

export function JobsPanel({
  jobs,
  metrics,
  metricsError,
  metricsWindow = "7d",
  onMetricsWindowChange,
  loading,
  error,
  statusFilter,
  onStatusFilterChange,
  onRefresh,
  onOpenProject,
  findProjectForJob,
  lastUpdatedAt,
  pollIntervalMs,
  compact = false,
  title = "Jobs",
  description,
  emptyMessage = "No jobs recorded for this filter.",
  onViewAllProjects,
  compactActionLabel = "View jobs",
  formatLlmLabel,
}: {
  jobs: A2AJob[];
  metrics?: JobMetrics | null;
  metricsError?: string | null;
  metricsWindow?: JobMetricsWindow;
  onMetricsWindowChange?: (window: JobMetricsWindow) => void;
  loading: boolean;
  error: string | null;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  onRefresh: () => void;
  onOpenProject: (job: A2AJob) => void;
  findProjectForJob: (job: A2AJob) => any;
  lastUpdatedAt: string | null;
  pollIntervalMs: number;
  compact?: boolean;
  title?: string;
  description?: string;
  emptyMessage?: string;
  onViewAllProjects?: () => void;
  compactActionLabel?: string;
  formatLlmLabel: (provider: string, model: string) => string;
}) {
  const [userFilter, setUserFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<AdminJobSortMode>("last_occurred_desc");
  const userOptions = useMemo(() => {
    const users = new Map<string, { id: string; label: string }>();
    jobs.forEach((job) => {
      const id = job.owner_user_id || job.payload?.owner_user_id;
      if (typeof id !== "string" || !id.trim()) return;
      const normalizedId = id.trim();
      const label = formatJobOwnerUsername(job) || normalizedId;
      users.set(normalizedId, { id: normalizedId, label });
    });
    return Array.from(users.values()).sort((left, right) => left.label.localeCompare(right.label));
  }, [jobs]);
  const filteredJobs = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return jobs.filter((job) => {
      const ownerUserId = String(job.owner_user_id || job.payload?.owner_user_id || "");
      if (userFilter !== "all" && ownerUserId !== userFilter) return false;
      if (!query) return true;
      const searchable = [
        job.payload?.prompt,
        job.result_summary?.title,
        job.job_id,
        job.owner_display_name,
        job.owner_email,
        job.owner_github_username,
        ownerUserId,
      ];
      return searchable.some((value) => String(value || "").toLowerCase().includes(query));
    });
  }, [jobs, searchQuery, userFilter]);
  const sortedJobs = useMemo(() => sortAdminJobs(filteredJobs, sortMode), [filteredJobs, sortMode]);
  const visibleJobs = compact ? sortedJobs.slice(0, 2) : sortedJobs;
  const filters = ["all", "queued", "running", "succeeded", "failed"];
  const panelDescription = description || `Generation and example job metadata. Polling every ${Math.round(pollIntervalMs / 1000)}s.`;

  return (
    <div className={`min-w-0 overflow-x-hidden ${compact ? "border border-[#2c2f37] bg-[#17181d] p-4" : "h-full overflow-y-auto bg-[#141519] p-4 sm:p-6"}`}>
      <div className={`${compact ? "mb-3 pb-3" : "mb-5 pb-4"} flex items-start justify-between gap-4 border-b border-[#2a2c33]`}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-black uppercase text-white">{title}</h2>
          </div>
          {!compact && (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {panelDescription}
            </p>
          )}
          {lastUpdatedAt && !compact && (
            <p className="mt-1 text-[11px] leading-5 text-slate-600">Updated {formatJobTime(lastUpdatedAt)}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="flex h-10 w-10 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
          title="Refresh jobs"
          aria-label="Refresh jobs"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {!compact && metrics !== undefined && (
        <JobMetricsPanel
          metrics={metrics || null}
          error={metricsError || null}
          metricsWindow={metricsWindow}
          onMetricsWindowChange={onMetricsWindowChange}
        />
      )}

      {!compact && (
        <div className="mb-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            {filters.map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => onStatusFilterChange(filter)}
                className={`border px-3 py-2 text-xs font-bold uppercase ${
                  statusFilter === filter
                    ? "border-white bg-white text-black"
                    : "border-[#2a2c33] bg-[#141519] text-slate-500 hover:border-slate-500 hover:text-white"
                }`}
              >
                {filter}
              </button>
            ))}
          </div>
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(190px,0.35fr)_minmax(190px,0.35fr)]">
            <label className="min-w-0">
              <span className="sr-only">Search jobs and prompts</span>
              <input
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search prompts, users, or job IDs"
                className="h-10 w-full border border-[#2a2c33] bg-[#141519] px-3 text-xs text-white outline-none placeholder:text-slate-600 focus:border-cyan-400"
              />
            </label>
            <label className="min-w-0">
              <span className="sr-only">Filter jobs by user</span>
              <select
                value={userFilter}
                onChange={(event) => setUserFilter(event.target.value)}
                className="h-10 w-full border border-[#2a2c33] bg-[#141519] px-3 text-xs font-bold text-slate-300 outline-none focus:border-cyan-400"
              >
                <option value="all">All users ({userOptions.length})</option>
                {userOptions.map((user) => (
                  <option key={user.id} value={user.id}>{user.label}</option>
                ))}
              </select>
            </label>
            <label className="min-w-0">
              <span className="sr-only">Sort jobs</span>
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as AdminJobSortMode)}
                className="h-10 w-full border border-[#2a2c33] bg-[#141519] px-3 text-xs font-bold text-slate-300 outline-none focus:border-cyan-400"
              >
                {ADMIN_JOB_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 flex gap-2 border border-amber-500/30 bg-amber-950/25 p-3 text-xs leading-5 text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !visibleJobs.length ? (
        <div className="border border-[#2a2c33] bg-[#141519] p-5 text-sm text-slate-500">Loading jobs...</div>
      ) : visibleJobs.length ? (
        <div className="space-y-3">
          {visibleJobs.map((job) => (
            <JobRow
              key={job.job_id}
              job={job}
              project={findProjectForJob(job)}
              onOpenProject={() => onOpenProject(job)}
              compact={compact}
              formatLlmLabel={formatLlmLabel}
            />
          ))}
        </div>
      ) : (
        <div className="border border-[#2a2c33] bg-[#141519] p-5 text-sm leading-6 text-slate-500">
          {jobs.length && (searchQuery || userFilter !== "all") ? "No jobs match these user or prompt filters." : emptyMessage}
        </div>
      )}

      {compact && jobs.length > visibleJobs.length && (
        <button
          type="button"
          onClick={onViewAllProjects || (() => onStatusFilterChange(statusFilter))}
          className="group mt-4 flex w-full items-center justify-center gap-2 border border-[#2a2c33] px-4 py-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black"
        >
          <Database className="h-4 w-4" />
          <span>{jobs.length} total jobs</span>
          {onViewAllProjects && <span className="text-slate-500 group-hover:text-black">{compactActionLabel}</span>}
        </button>
      )}
    </div>
  );
}

const JOB_METRICS_WINDOW_OPTIONS: Array<{ value: JobMetricsWindow; label: string }> = [
  { value: "1h", label: "1 hour" },
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
];
const JOB_METRICS_WINDOW_HOURS: Record<JobMetricsWindow, number> = { "1h": 1, "24h": 24, "7d": 168 };

function JobMetricsPanel({
  metrics,
  error,
  metricsWindow,
  onMetricsWindowChange,
}: {
  metrics: JobMetrics | null;
  error: string | null;
  metricsWindow: JobMetricsWindow;
  onMetricsWindowChange?: (window: JobMetricsWindow) => void;
}) {
  const selectedMetrics = metrics?.interval_hours === JOB_METRICS_WINDOW_HOURS[metricsWindow] ? metrics : null;

  if (error && !selectedMetrics) {
    return (
      <div className="mb-4 border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">
        {error}
      </div>
    );
  }
  if (!selectedMetrics) {
    return <div className="mb-4 border border-[#2a2c33] bg-[#17181d] p-4 text-xs text-slate-500">Loading job metrics...</div>;
  }

  const intervalLabel = JOB_METRICS_WINDOW_OPTIONS.find((option) => option.value === metricsWindow)?.label || metricsWindow;
  const chartUsesDays = metricsWindow === "7d";

  return (
    <section className="mb-5 space-y-3" aria-label="Job metrics">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Metrics interval</span>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Job metrics interval">
          {JOB_METRICS_WINDOW_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onMetricsWindowChange?.(option.value)}
              aria-pressed={metricsWindow === option.value}
              className={`border px-3 py-1.5 text-[10px] font-black uppercase ${
                metricsWindow === option.value
                  ? "border-white bg-white text-black"
                  : "border-[#2a2c33] text-slate-500 hover:border-slate-500 hover:text-white"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <JobMetricSummary label={`Jobs · ${intervalLabel}`} value={selectedMetrics.total_jobs} detail="Created in selected interval" />
        <JobMetricSummary
          label="Completed"
          value={selectedMetrics.completed_jobs}
          detail={`${selectedMetrics.failed_jobs} failed`}
          danger={selectedMetrics.failed_jobs > 0}
        />
        <JobMetricSummary
          label={`${intervalLabel} failure rate`}
          value={`${Number(selectedMetrics.failure_rate || 0).toFixed(1)}%`}
          detail={`${selectedMetrics.failed_jobs} failed / ${selectedMetrics.completed_jobs} completed`}
          danger={selectedMetrics.failure_rate > 0}
        />
      </div>
      <JobVolumeChart
        title={chartUsesDays ? "Jobs per day" : "Jobs per hour"}
        buckets={chartUsesDays ? selectedMetrics.daily : selectedMetrics.hourly}
        unit={chartUsesDays ? "day" : "hour"}
      />
      {error && <p className="text-[11px] text-amber-300">Showing the last available metrics. {error}</p>}
    </section>
  );
}

function JobMetricSummary({
  label,
  value,
  detail,
  danger = false,
}: {
  label: string;
  value: string | number;
  detail: string;
  danger?: boolean;
}) {
  return (
    <div className={`border bg-[#17181d] p-4 ${danger ? "border-rose-500/30" : "border-[#2a2c33]"}`}>
      <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className={`mt-2 text-2xl font-black ${danger ? "text-rose-300" : "text-white"}`}>{value}</div>
      <div className="mt-1 text-[11px] text-slate-600">{detail}</div>
    </div>
  );
}

function JobVolumeChart({
  title,
  buckets,
  unit,
}: {
  title: string;
  buckets: JobMetricBucket[];
  unit: "day" | "hour";
}) {
  const maximum = Math.max(1, ...buckets.map((bucket) => Number(bucket.count || 0)));
  return (
    <div className="min-w-0 border border-[#2a2c33] bg-[#17181d] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">{title}</h3>
        <span className="text-[10px] text-slate-600">UTC</span>
      </div>
      <div className="flex h-28 items-end gap-1" role="img" aria-label={`${title} in UTC`}>
        {buckets.map((bucket, index) => {
          const count = Number(bucket.count || 0);
          const height = count ? Math.max(6, Math.round((count / maximum) * 100)) : 2;
          const showLabel = unit === "day" || index % 4 === 0 || index === buckets.length - 1;
          return (
            <div key={bucket.period} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`${formatMetricPeriod(bucket.period, unit)}: ${count} jobs`}>
              <div className="mb-1 text-center text-[9px] font-bold text-slate-500">{count || ""}</div>
              <div className="w-full bg-cyan-400/80" style={{ height: `${height}%` }} />
              <div className="mt-2 truncate text-center text-[8px] text-slate-600">
                {showLabel ? formatMetricAxisLabel(bucket.period, unit) : ""}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatMetricPeriod(value: string, unit: "day" | "hour") {
  const date = new Date(unit === "day" ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    ...(unit === "hour" ? { hour: "numeric", hour12: true } : {}),
  });
}

function formatMetricAxisLabel(value: string, unit: "day" | "hour") {
  const date = new Date(unit === "day" ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return unit === "day"
    ? date.toLocaleDateString([], { timeZone: "UTC", weekday: "short" })
    : date.toLocaleTimeString([], { timeZone: "UTC", hour: "numeric", hour12: true }).replace(" ", "");
}

export function JobRow({
  job,
  project,
  onOpenProject,
  compact,
  formatLlmLabel,
}: {
  job: A2AJob;
  project: any;
  onOpenProject: () => void;
  compact?: boolean;
  formatLlmLabel: (provider: string, model: string) => string;
}) {
  const tone = statusTone(job.status);
  const summary = job.result_summary || {};
  const title = summary.title || job.payload?.prompt || job.action;
  const userPrompt = typeof job.payload?.prompt === "string" ? job.payload.prompt : "";
  const prompt = userPrompt || job.correlation_id || job.job_id;
  const sourceUsage = getJobSourceUsage(job);
  const sourceLabel = formatSourceUsageLabel(sourceUsage);
  const SourceIcon = sourceUsage.web_research || sourceUsage.firecrawl ? Sparkles : Database;
  const llmInfo = getJobLlmInfo(job, formatLlmLabel);
  const hasChatTarget = Boolean(chatIdFromJob(job));
  const hasProjectTarget = Boolean(project?.project_id);
  const isOpenable = hasChatTarget || hasProjectTarget;
  const imageStatusLabel = formatJobImageStatus(summary);
  const operations = getJobOperations(summary);
  const imageOperation = operations.find((operation) => operation.id === "image_generation") || {};
  const imageFailed = Boolean(
    summary.image_output_failed
    || summary.image_output_status === "failed"
    || imageOperation.status === "failed"
  );
  const imageFailureOutput = firstString(
    summary.image_output_error,
    summary.product_image_error,
    imageOperation.error,
    summary.image_output_reason,
    imageOperation.reason,
  ) || "Image generation failed without an error message.";
  const ownerUserId = job.owner_user_id || job.payload?.owner_user_id || "";
  const ownerLabel = formatJobOwnerUsername(job) || ownerUserId || "Unknown user";
  const lastOccurredAt = adminJobLastOccurredAt(job);

  return (
    <article className={`border border-[#2a2c33] bg-[#141519] ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] font-black uppercase ${tone}`}>
              {job.status === "succeeded" ? <CheckCircle className="h-3.5 w-3.5" /> : job.status === "failed" ? <AlertTriangle className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {job.status}
            </span>
            {sourceLabel !== "-" && (
              <span className="inline-flex max-w-full items-center gap-1.5 truncate border border-cyan-300/25 bg-cyan-300/10 px-2 py-1 text-[11px] font-black uppercase text-cyan-200">
                <SourceIcon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{sourceLabel}</span>
              </span>
            )}
            {llmInfo.label !== "-" && (
              <span className="inline-flex max-w-full items-center gap-1.5 truncate border border-violet-300/25 bg-violet-300/10 px-2 py-1 text-[11px] font-black uppercase text-violet-100">
                <Cpu className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{llmInfo.label}</span>
              </span>
            )}
            <span className="min-w-0 max-w-full truncate text-[11px] font-bold text-slate-500">{job.sender} {"->"} {job.recipient}</span>
            {ownerUserId && (
              <span className="inline-flex max-w-full items-center truncate border border-sky-300/25 bg-sky-300/10 px-2 py-1 text-[11px] font-black text-sky-200" title={ownerUserId}>
                {ownerLabel}
              </span>
            )}
          </div>
          <h3 className="truncate text-sm font-black text-white">{title}</h3>
          <div className="mt-2 flex min-w-0 items-start gap-2">
            <p className="min-w-0 flex-1 line-clamp-2 break-words text-xs leading-5 text-slate-500">{prompt}</p>
            <CopyButton value={userPrompt} label="Copy user prompt" className="shrink-0" />
          </div>
        </div>

        <button
          type="button"
          onClick={onOpenProject}
          disabled={!isOpenable}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-35"
        >
          <Eye className="h-4 w-4" />
          {hasChatTarget ? "Open chat" : "Open"}
        </button>
      </div>

      {!compact && (
        <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-2 lg:grid-cols-5 xl:grid-cols-10">
          <JobMetric label="User" value={ownerLabel} />
          <JobMetric label="Job" value={job.job_id} />
          <JobMetric label="Created" value={formatJobTime(job.created_at)} />
          <JobMetric label="Last occurred" value={formatJobTime(lastOccurredAt)} />
          <JobMetric label="Duration" value={formatJobDuration(job)} />
          <JobMetric label="Source" value={sourceLabel} />
          <JobMetric label="LLM" value={llmInfo.label} />
          <JobMetric label="Parts" value={summary.component_count ?? "-"} />
          <JobMetric label="Valid" value={summary.is_valid === undefined ? "-" : summary.is_valid ? "yes" : "no"} />
          <JobMetric label="Image" value={imageStatusLabel} />
        </div>
      )}

      {!compact && userPrompt && (
        <details className="mt-3 border border-[#25272e] bg-black/20 p-3">
          <summary className="cursor-pointer text-[10px] font-black uppercase tracking-[0.14em] text-cyan-300">
            View full user prompt
          </summary>
          <div className="mt-3 whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">{userPrompt}</div>
          {ownerUserId && (
            <div className="mt-3 border-t border-white/10 pt-2 font-mono text-[10px] text-slate-600">
              User ID: {ownerUserId}
            </div>
          )}
        </details>
      )}

      <JobPipelineEventList events={job.progress_events || []} jobStatus={job.status} compact={compact} />

      <OperationStatusList operations={operations} compact={compact} />

      {imageFailed && (
        <div className="break-anywhere mt-3 border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
          Image generation failed: {imageFailureOutput}
          {summary.image_output_debug && (
            <pre className="break-anywhere mt-2 max-h-40 overflow-auto whitespace-pre-wrap border border-amber-500/20 bg-black/25 p-2 font-mono text-[10px] leading-4 text-amber-100">
              {JSON.stringify(summary.image_output_debug, null, 2)}
            </pre>
          )}
        </div>
      )}

      {job.error && (
        <div className="break-anywhere mt-3 border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          {job.error}
        </div>
      )}

      {job.error_debug && (
        <details className="mt-3 border border-rose-500/30 bg-black/25 p-3 text-xs text-rose-100">
          <summary className="cursor-pointer font-black uppercase text-rose-300">
            Debug trace{job.error_debug.error_type ? `: ${job.error_debug.error_type}` : ""}
          </summary>
          {job.error_debug.error && (
            <div className="break-anywhere mt-3 text-rose-200">{String(job.error_debug.error)}</div>
          )}
          {job.error_debug.context && (
            <pre className="break-anywhere mt-3 max-h-48 overflow-auto whitespace-pre-wrap border border-white/10 bg-black/30 p-3 text-[11px] leading-4 text-slate-300">
              {JSON.stringify(job.error_debug.context, null, 2)}
            </pre>
          )}
          {job.error_debug.traceback && (
            <pre className="break-anywhere mt-3 max-h-64 overflow-auto whitespace-pre-wrap border border-white/10 bg-black/30 p-3 text-[11px] leading-4 text-slate-300">
              {String(job.error_debug.traceback)}
            </pre>
          )}
        </details>
      )}
    </article>
  );
}

function formatJobOwnerUsername(job: A2AJob) {
  const githubUsername = String(job.owner_github_username || "").trim().replace(/^@+/, "");
  if (githubUsername) return `@${githubUsername}`;
  return String(job.owner_username || job.owner_email || job.owner_display_name || "").trim();
}

function getJobOperations(summary: Record<string, any>) {
  return Array.isArray(summary.operation_statuses)
    ? summary.operation_statuses.filter((operation: any) => operation && typeof operation === "object")
    : [];
}

function firstString(...values: any[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function getJobLlmInfo(job: A2AJob, formatLlmLabel: (provider: string, model: string) => string) {
  const summary = job.result_summary || {};
  const operations = getJobOperations(summary);
  const generationOperation = operations.find((operation) => operation.provider || operation.model) || {};
  const eventDetails = normalizeAdminPipelineEvents(job.progress_events)
    .map((event) => event.details || {})
    .reverse();
  const eventProvider = firstString(...eventDetails.map((details) => details.runtime_provider || details.provider));
  const eventModel = firstString(...eventDetails.map((details) => details.runtime_model || details.actual_model || details.model));
  const provider = firstString(
    summary.runtime_provider,
    summary.llm_provider,
    summary.requested_provider,
    job.payload?.provider,
    generationOperation.provider,
    eventProvider
  );
  const model = firstString(
    summary.runtime_model,
    summary.actual_model,
    summary.model_name,
    summary.requested_model,
    job.payload?.model,
    generationOperation.model,
    eventModel
  );

  return {
    provider,
    model,
    label: provider && model ? formatLlmLabel(provider, model) : provider || model || "-",
  };
}

function pipelineEventTone(status: string) {
  if (isCompletedAdminPipelineStatus(status)) return "border-emerald-500/25 bg-emerald-950/15 text-emerald-300";
  if (isFailedAdminPipelineStatus(status)) return "border-rose-500/30 bg-rose-950/20 text-rose-300";
  if (status === "skipped") return "border-slate-500/20 bg-slate-950/20 text-slate-500";
  return "border-cyan-500/25 bg-cyan-950/15 text-cyan-300";
}

function JobPipelineEventList({
  events,
  jobStatus,
  compact = false,
}: {
  events: AgentPipelineEvent[];
  jobStatus: string;
  compact?: boolean;
}) {
  const normalizedEvents = normalizeAdminPipelineEvents(events);
  if (!normalizedEvents.length) return null;
  const visibleEvents = compact ? normalizedEvents.slice(-3) : normalizedEvents.slice(-12);
  const jobIsTerminal = isTerminalJobStatus(jobStatus);

  return (
    <div className={`${compact ? "mt-3" : "mt-4"} border border-[#25272e] bg-black/20 p-3`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Core pipeline events</span>
        <span className="font-mono text-[10px] text-slate-600">{normalizedEvents.length}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {visibleEvents.map((event, index) => {
          const label = event.label || event.step_id;
          const time = event.observed_at ? formatJobTime(event.observed_at) : "";
          const isActiveStartedEvent = event.status === "started" && !jobIsTerminal;
          return (
            <span key={`${event.step_id}-${event.status}-${event.observed_at || index}`} className={`inline-flex max-w-full items-center gap-1.5 border px-2 py-1 text-[10px] font-black uppercase ${pipelineEventTone(String(event.status))}`}>
              {isCompletedAdminPipelineStatus(event.status) ? <CheckCircle className="h-3 w-3 shrink-0" /> : isFailedAdminPipelineStatus(event.status) ? <AlertTriangle className="h-3 w-3 shrink-0" /> : <RefreshCw className={`h-3 w-3 shrink-0 ${isActiveStartedEvent ? "animate-spin" : ""}`} />}
              <span className="truncate">{label}</span>
              <span className="text-slate-500">{String(event.status).replace(/_/g, " ")}</span>
              {time && !compact && <span className="text-slate-600">{time}</span>}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function operationStatusTone(status: string) {
  if (status === "succeeded") return "border-emerald-500/30 bg-emerald-950/25 text-emerald-300";
  if (status === "failed") return "border-rose-500/30 bg-rose-950/20 text-rose-300";
  if (status === "pending") return "border-cyan-500/30 bg-cyan-950/20 text-cyan-300";
  if (status === "not_requested") return "border-slate-500/20 bg-slate-950/20 text-slate-500";
  return "border-slate-500/25 bg-slate-950/25 text-slate-400";
}

function compactOperationDetails(details: Record<string, any> | undefined) {
  if (!details || typeof details !== "object") return "";
  const imageDebug = details.image_output_debug && typeof details.image_output_debug === "object" ? details.image_output_debug : null;
  const source = imageDebug || details;
  const importantKeys = [
    "provider",
    "model_name",
    "base_url",
    "enabled",
    "configured",
    "reason",
    "inference_provider",
    "size",
    "output_format",
  ];
  return importantKeys
    .filter((key) => source[key] !== undefined && source[key] !== null && source[key] !== "")
    .map((key) => `${key}: ${String(source[key])}`)
    .join(" | ");
}

function OperationStatusList({ operations, compact = false }: { operations: Record<string, any>[]; compact?: boolean }) {
  if (!operations.length) return null;
  const visibleOperations = compact
    ? operations.filter((operation) => operation.status === "failed").slice(0, 2)
    : operations;
  if (!visibleOperations.length) return null;

  return (
    <div className={`${compact ? "mt-3" : "mt-4"} grid gap-2 ${compact ? "" : "sm:grid-cols-2 xl:grid-cols-3"}`}>
      {visibleOperations.map((operation, index) => {
        const status = String(operation.status || "unknown");
        const providerModel = [operation.provider, operation.model].filter(Boolean).join("/");
        const error = operation.error || operation.reason;
        const details = compactOperationDetails(operation.details);
        return (
          <div key={`${operation.id || operation.label || "operation"}-${index}`} className={`min-w-0 border p-3 ${operationStatusTone(status)}`}>
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="truncate text-[11px] font-black uppercase">{operation.label || operation.id || "Operation"}</span>
              <span className="shrink-0 text-[10px] font-black uppercase">{status.replace(/_/g, " ")}</span>
            </div>
            {providerModel && (
              <div className="mt-1 truncate font-mono text-[10px] opacity-80">{providerModel}</div>
            )}
            {error && (
              <div className="break-anywhere mt-2 line-clamp-3 text-[11px] leading-4 opacity-90">
                {String(error)}
              </div>
            )}
            {details && !compact && (
              <div className="break-anywhere mt-2 border border-white/10 bg-black/20 p-2 font-mono text-[10px] leading-4 opacity-80">
                {details}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function getJobSourceUsage(job: A2AJob) {
  const summaryUsage = job.result_summary?.source_usage;
  const workflow = job.result_summary?.workflow || job.payload?.workflow;
  return normalizeJobSourceUsage(job.source_usage || summaryUsage || (workflow ? { workflow } : {}));
}

function normalizeJobSourceUsage(value: any) {
  const sourceUsage = value && typeof value === "object" ? value : {};
  const rawWorkflow = typeof sourceUsage.workflow === "string" ? sourceUsage.workflow : "";
  const workflow = rawWorkflow.trim().toLowerCase().replace(/-/g, "_");
  const catalog = Boolean(sourceUsage.catalog || sourceUsage.data_warehouse || sourceUsage.used_catalog || workflow === "default" || workflow === "catalog");
  const externalProvider = typeof sourceUsage.external_provider === "string" ? sourceUsage.external_provider.trim().toLowerCase() : "";
  const webResearch = Boolean(
    sourceUsage.web_research ||
    sourceUsage.external_sources ||
    sourceUsage.tavily ||
    sourceUsage.firecrawl ||
    sourceUsage.used_web_research ||
    workflow === "web_research" ||
    workflow === "web_search" ||
    workflow === "websearch" ||
    workflow === "research" ||
    workflow === "firecrawl"
  );
  const sourceLabels = Array.isArray(sourceUsage.source_labels)
    ? sourceUsage.source_labels.filter((label: any) => typeof label === "string" && label.trim())
    : [];
  const labels = sourceLabels.length ? sourceLabels : [
    ...(catalog ? ["Catalog"] : []),
    ...(webResearch ? [sourceUsage.tavily || externalProvider === "tavily" ? "Tavily" : sourceUsage.firecrawl || externalProvider === "firecrawl" ? "Firecrawl" : "Web Research"] : []),
  ];
  return {
    ...sourceUsage,
    workflow,
    catalog,
    web_research: webResearch,
    external_sources: webResearch,
    external_provider: externalProvider || (sourceUsage.tavily ? "tavily" : sourceUsage.firecrawl ? "firecrawl" : sourceUsage.external_provider),
    tavily: Boolean(sourceUsage.tavily || externalProvider === "tavily"),
    firecrawl: Boolean(sourceUsage.firecrawl || externalProvider === "firecrawl"),
    source_labels: labels,
  };
}

function formatSourceUsageLabel(sourceUsage: Record<string, any>) {
  const labels = Array.isArray(sourceUsage.source_labels) ? sourceUsage.source_labels : [];
  return labels.length ? labels.join(" + ") : "-";
}

function formatJobImageStatus(summary: Record<string, any>) {
  if (summary.image_output_failed || summary.image_output_status === "failed") return "failed";
  if (summary.has_product_image) return summary.product_image_model || "yes";
  if (summary.image_output_status === "succeeded") return summary.product_image_model || "done";
  if (summary.image_output_requested === true) return summary.image_output_status || "requested";
  if (typeof summary.image_output_status === "string" && summary.image_output_status) {
    return summary.image_output_status.replace(/_/g, " ");
  }
  return "-";
}

export function JobMetric({ label, value }: { label: string; value: any }) {
  return (
    <div className="min-w-0 border border-[#25272e] bg-[#17181d] px-3 py-2">
      <div className="text-[10px] font-black uppercase text-slate-600">{label}</div>
      <div className="mt-1 truncate text-xs font-bold text-slate-300">{String(value ?? "-")}</div>
    </div>
  );
}

export function statusTone(status: string) {
  if (status === "succeeded") return "border-emerald-500/30 bg-emerald-950/25 text-emerald-300";
  if (status === "failed") return "border-rose-500/30 bg-rose-950/25 text-rose-300";
  if (status === "running" || status === "loading" || status === "reviewing") return "border-cyan-500/30 bg-cyan-950/25 text-cyan-300";
  if (status === "queued") return "border-amber-500/30 bg-amber-950/25 text-amber-300";
  return "border-slate-500/30 bg-slate-900 text-slate-300";
}

function isTerminalJobStatus(status: string) {
  return ["succeeded", "success", "completed", "complete", "done", "failed", "failure", "error", "cancelled", "canceled"].includes(status);
}

export function isFinalVideoStatus(status: string) {
  return ["succeeded", "success", "completed", "complete", "done", "failed", "failure", "error", "cancelled", "canceled"].includes(status);
}

export function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value < 1024) return `${value} B`;
  const kb = value / 1024;
  if (kb < 1024) return `${kb.toFixed(kb >= 10 ? 0 : 1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
}

function formatJobTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatJobDuration(job: A2AJob) {
  if (!job.started_at || !job.completed_at) return job.status === "running" ? "running" : "-";
  return formatDurationSeconds(durationSecondsBetween(job.started_at, job.completed_at));
}
