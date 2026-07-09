"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Clock,
  Database,
  Eye,
  Radio,
  RefreshCw,
  Terminal,
} from "lucide-react";

const DEFAULT_API_URL = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_API_URL);
const POLL_INTERVAL_MS = 5000;

type StreamSummary = {
  stream_id: string;
  path: string;
  updated_at?: string | null;
  job_count: number;
  result_count: number;
  event_count: number;
  pending_count: number;
  succeeded_count: number;
  failed_count: number;
  latest_job_id?: string | null;
  latest_provider?: string | null;
  latest_model?: string | null;
  latest_status?: string | null;
  latest_output_preview?: string;
};

type StreamJobResult = {
  status: string;
  duration_seconds?: number | null;
  character_count: number;
  event_count: number;
  error_message?: string | null;
  completed_at?: string | null;
  agent_output_names: string[];
};

type StreamJob = {
  stream_id: string;
  job_id: string;
  provider: string;
  model: string;
  status: string;
  prompt: string;
  reason: string;
  created_by: string;
  created_at?: string | null;
  max_output_tokens?: number | null;
  metadata: Record<string, any>;
  result?: StreamJobResult | null;
  output_text: string;
  output_preview: string;
  output_truncated: boolean;
};

type StreamAgentOutput = {
  stream_id: string;
  agent_name: string;
  kind: string;
  created_at?: string | null;
  source_event_id?: string | null;
  payload: Record<string, any>;
};

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function statusTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded") return "border-emerald-500/40 bg-emerald-950/25 text-emerald-300";
  if (normalized === "failed") return "border-rose-500/40 bg-rose-950/25 text-rose-300";
  if (normalized === "running") return "border-cyan-500/40 bg-cyan-950/25 text-cyan-300";
  return "border-slate-500/30 bg-slate-950/30 text-slate-400";
}

function StatusIcon({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded") return <CheckCircle className="h-3.5 w-3.5" />;
  if (normalized === "failed") return <AlertTriangle className="h-3.5 w-3.5" />;
  return <Clock className="h-3.5 w-3.5" />;
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return "-";
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const payload = await response.json();
      detail = typeof payload?.detail === "string" ? payload.detail : detail;
    } catch {
      // Keep fallback.
    }
    throw new Error(detail);
  }
  return response.json();
}

function streamLabel(streamId: string) {
  return streamId === "__root__" ? "root stream" : streamId;
}

export default function ListeningJobsPage() {
  const [streams, setStreams] = useState<StreamSummary[]>([]);
  const [selectedStreamId, setSelectedStreamId] = useState<string>("");
  const [jobs, setJobs] = useState<StreamJob[]>([]);
  const [agents, setAgents] = useState<StreamAgentOutput[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loadingStreams, setLoadingStreams] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const selectedStream = useMemo(
    () => streams.find((stream) => stream.stream_id === selectedStreamId) || null,
    [streams, selectedStreamId]
  );
  const selectedJob = useMemo(
    () => jobs.find((job) => job.job_id === selectedJobId) || jobs[0] || null,
    [jobs, selectedJobId]
  );
  const selectedJobAgents = useMemo(
    () => agents.filter((agent) => !selectedJob?.job_id || agent.source_event_id || agent.payload),
    [agents, selectedJob?.job_id]
  );

  const loadStreams = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!options.silent) setLoadingStreams(true);
    setError(null);
    try {
      const payload = await fetchJson<StreamSummary[]>(`${API_URL}/streams?limit=100`);
      setStreams(payload);
      setSelectedStreamId((current) => {
        if (current && payload.some((stream) => stream.stream_id === current)) return current;
        return payload.find((stream) => stream.stream_id === "blue-sentinel-e2e-v2")?.stream_id || payload[0]?.stream_id || "";
      });
      setLastUpdatedAt(new Date().toISOString());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Streams are unavailable.");
    } finally {
      if (!options.silent) setLoadingStreams(false);
    }
  }, []);

  const loadStreamDetails = useCallback(async (streamId: string, options: { silent?: boolean } = {}) => {
    if (!streamId) return;
    if (!options.silent) setLoadingJobs(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "200", max_output_chars: "30000" });
      if (statusFilter !== "all") params.set("status", statusFilter);
      const [jobPayload, agentPayload] = await Promise.all([
        fetchJson<StreamJob[]>(`${API_URL}/streams/${encodeURIComponent(streamId)}/jobs?${params.toString()}`),
        fetchJson<StreamAgentOutput[]>(`${API_URL}/streams/${encodeURIComponent(streamId)}/agents?limit=120`),
      ]);
      setJobs(jobPayload);
      setAgents(agentPayload);
      setSelectedJobId((current) => {
        if (current && jobPayload.some((job) => job.job_id === current)) return current;
        return jobPayload[0]?.job_id || "";
      });
      setLastUpdatedAt(new Date().toISOString());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Stream jobs are unavailable.");
    } finally {
      if (!options.silent) setLoadingJobs(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadStreams();
  }, [loadStreams]);

  useEffect(() => {
    if (!selectedStreamId) return;
    loadStreamDetails(selectedStreamId);
  }, [loadStreamDetails, selectedStreamId]);

  useEffect(() => {
    const poll = () => {
      if (document.visibilityState !== "visible") return;
      loadStreams({ silent: true });
      if (selectedStreamId) loadStreamDetails(selectedStreamId, { silent: true });
    };
    const intervalId = window.setInterval(poll, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", poll);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [loadStreams, loadStreamDetails, selectedStreamId]);

  const refresh = () => {
    loadStreams();
    if (selectedStreamId) loadStreamDetails(selectedStreamId);
  };

  return (
    <main className="min-h-screen bg-[#141519] text-slate-200">
      <header className="border-b border-[#282a30] bg-[#17181d] px-4 py-4">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              className="inline-flex h-10 shrink-0 items-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-slate-400 hover:bg-white hover:text-black"
            >
              <ArrowLeft className="h-4 w-4" />
              Home
            </Link>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Radio className="h-4 w-4 text-cyan-300" />
                <h1 className="truncate text-lg font-black uppercase tracking-wide text-white">Listening Jobs</h1>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Continuous LLM stream jobs from `.spacebase`, separate from generated projects.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex h-10 items-center justify-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black"
          >
            <RefreshCw className={`h-4 w-4 ${loadingStreams || loadingJobs ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[330px_minmax(0,1fr)]">
        <aside className="min-w-0 border border-[#2a2c33] bg-[#17181d]">
          <div className="border-b border-[#2a2c33] p-4">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-cyan-300" />
              <h2 className="text-sm font-black uppercase text-white">Streams</h2>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {streams.length} streams found. Polling every {Math.round(POLL_INTERVAL_MS / 1000)}s.
            </p>
          </div>
          <div className="max-h-[calc(100vh-190px)] overflow-auto p-2">
            {streams.map((stream) => (
              <button
                key={stream.stream_id}
                type="button"
                onClick={() => setSelectedStreamId(stream.stream_id)}
                className={`mb-2 block w-full border p-3 text-left ${
                  selectedStreamId === stream.stream_id
                    ? "border-cyan-300 bg-cyan-300/10"
                    : "border-[#2a2c33] bg-[#141519] hover:border-slate-500"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-black uppercase text-white">{streamLabel(stream.stream_id)}</span>
                  <span className={`shrink-0 border px-2 py-0.5 text-[10px] font-black uppercase ${statusTone(stream.latest_status || "pending")}`}>
                    {stream.latest_status || "pending"}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] uppercase text-slate-500">
                  <span>{stream.job_count} jobs</span>
                  <span>{stream.succeeded_count} pass</span>
                  <span>{stream.failed_count} fail</span>
                </div>
                {stream.latest_output_preview && (
                  <p className="mt-3 line-clamp-3 break-words text-[11px] leading-5 text-slate-500">{stream.latest_output_preview}</p>
                )}
              </button>
            ))}
            {!streams.length && (
              <div className="p-4 text-sm text-slate-500">
                {loadingStreams ? "Loading streams..." : "No continuous streams found."}
              </div>
            )}
          </div>
        </aside>

        <section className="min-w-0">
          <div className="mb-4 border border-[#2a2c33] bg-[#17181d] p-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <h2 className="truncate text-base font-black uppercase text-white">
                  {selectedStream ? streamLabel(selectedStream.stream_id) : "No stream selected"}
                </h2>
                <p className="mt-2 break-all font-mono text-[11px] text-slate-500">
                  {selectedStream ? `${API_URL}/streams/${encodeURIComponent(selectedStream.stream_id)}/jobs` : `${API_URL}/streams`}
                </p>
                {lastUpdatedAt && <p className="mt-2 text-[11px] text-slate-600">Updated {formatTime(lastUpdatedAt)}</p>}
              </div>
              <div className="grid grid-cols-4 gap-2 text-center text-[11px] uppercase sm:min-w-[360px]">
                <Metric label="Jobs" value={selectedStream?.job_count ?? 0} />
                <Metric label="Events" value={selectedStream?.event_count ?? 0} />
                <Metric label="Pending" value={selectedStream?.pending_count ?? 0} />
                <Metric label="Failed" value={selectedStream?.failed_count ?? 0} />
              </div>
            </div>
          </div>

          {error && (
            <div className="mb-4 flex gap-2 border border-rose-500/30 bg-rose-950/25 p-3 text-sm text-rose-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="mb-4 flex flex-wrap gap-2">
            {["all", "pending", "succeeded", "failed"].map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`border px-3 py-2 text-xs font-black uppercase ${
                  statusFilter === status
                    ? "border-white bg-white text-black"
                    : "border-[#2a2c33] bg-[#17181d] text-slate-500 hover:border-slate-500 hover:text-white"
                }`}
              >
                {status}
              </button>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
            <div className="min-w-0 space-y-3">
              {jobs.map((job) => (
                <button
                  key={job.job_id}
                  type="button"
                  onClick={() => setSelectedJobId(job.job_id)}
                  className={`block w-full border p-4 text-left ${
                    selectedJob?.job_id === job.job_id
                      ? "border-cyan-300 bg-cyan-300/10"
                      : "border-[#2a2c33] bg-[#17181d] hover:border-slate-500"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] font-black uppercase ${statusTone(job.status)}`}>
                      <StatusIcon status={job.status} />
                      {job.status}
                    </span>
                    <span className="border border-[#2a2c33] px-2 py-1 text-[11px] font-black uppercase text-cyan-200">
                      {job.provider}/{job.model}
                    </span>
                  </div>
                  <h3 className="mt-3 truncate text-sm font-black text-white">{job.job_id}</h3>
                  <p className="mt-2 line-clamp-3 break-words text-xs leading-5 text-slate-500">{job.prompt}</p>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] uppercase text-slate-500">
                    <span>{formatTime(job.created_at)}</span>
                    <span>{formatDuration(job.result?.duration_seconds)}</span>
                    <span>{job.result?.character_count ?? 0} chars</span>
                  </div>
                  {job.result?.error_message && (
                    <p className="mt-3 break-words border border-rose-500/25 bg-rose-950/20 p-2 text-xs leading-5 text-rose-300">
                      {job.result.error_message}
                    </p>
                  )}
                </button>
              ))}
              {loadingJobs && !jobs.length && (
                <div className="border border-[#2a2c33] bg-[#17181d] p-5 text-sm text-slate-500">Loading stream jobs...</div>
              )}
              {!loadingJobs && !jobs.length && (
                <div className="border border-[#2a2c33] bg-[#17181d] p-5 text-sm text-slate-500">No jobs for this stream/filter.</div>
              )}
            </div>

            <div className="min-w-0 border border-[#2a2c33] bg-[#17181d]">
              <div className="border-b border-[#2a2c33] p-4">
                <div className="flex min-w-0 items-center gap-2">
                  <Eye className="h-4 w-4 text-cyan-300" />
                  <h2 className="truncate text-sm font-black uppercase text-white">
                    {selectedJob ? selectedJob.job_id : "Select a job"}
                  </h2>
                </div>
                {selectedJob && (
                  <p className="mt-2 break-all font-mono text-[11px] text-slate-500">
                    {`jq -r 'select(.metadata.job_id=="${selectedJob.job_id}") | .payload.content' .spacebase/streams/${selectedStreamId}/events.jsonl`}
                  </p>
                )}
              </div>

              {selectedJob ? (
                <div className="min-w-0 p-4">
                  <section className="mb-4">
                    <h3 className="mb-2 text-xs font-black uppercase text-slate-400">Prompt</h3>
                    <p className="whitespace-pre-wrap break-words border border-[#2a2c33] bg-black/25 p-3 text-xs leading-5 text-slate-300">
                      {selectedJob.prompt}
                    </p>
                  </section>

                  <section className="mb-4">
                    <h3 className="mb-2 text-xs font-black uppercase text-slate-400">Model Output</h3>
                    <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words border border-[#2a2c33] bg-black p-4 font-mono text-[12px] leading-5 text-slate-200">
                      {selectedJob.output_text || "No streamed output recorded for this job."}
                    </pre>
                    {selectedJob.output_truncated && (
                      <p className="mt-2 text-xs text-amber-300">Output truncated by API response limit. Increase max_output_chars programmatically.</p>
                    )}
                  </section>

                  <section>
                    <div className="mb-2 flex items-center gap-2">
                      <Terminal className="h-4 w-4 text-cyan-300" />
                      <h3 className="text-xs font-black uppercase text-slate-400">Recent Agent Notes</h3>
                    </div>
                    <div className="space-y-2">
                      {selectedJobAgents.slice(0, 8).map((agent, index) => (
                        <details key={`${agent.agent_name}-${agent.created_at}-${index}`} className="border border-[#2a2c33] bg-black/20 p-3 text-xs">
                          <summary className="cursor-pointer font-black uppercase text-slate-300">
                            {agent.agent_name} · {agent.kind || "agent output"} · {formatTime(agent.created_at)}
                          </summary>
                          <pre className="mt-3 max-h-52 overflow-auto whitespace-pre-wrap break-words border border-white/10 bg-black/30 p-3 text-[11px] leading-4 text-slate-300">
                            {JSON.stringify(agent.payload, null, 2)}
                          </pre>
                        </details>
                      ))}
                      {!selectedJobAgents.length && <p className="text-xs text-slate-500">No agent notes recorded.</p>}
                    </div>
                  </section>
                </div>
              ) : (
                <div className="flex min-h-[360px] items-center justify-center p-8 text-center text-sm text-slate-500">
                  Select a stream job to view its prompt, output, result, and agent notes.
                </div>
              )}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border border-[#2a2c33] bg-[#141519] px-2 py-3">
      <div className="text-sm font-black text-white">{value}</div>
      <div className="mt-1 text-[10px] font-bold text-slate-500">{label}</div>
    </div>
  );
}
