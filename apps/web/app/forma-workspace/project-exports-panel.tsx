"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Download, FileBox, Loader2, Printer, RefreshCw, TriangleAlert } from "lucide-react";

import { webConfig } from "../../lib/config";
import { useFormaAuth } from "../../lib/forma-auth";


type ExportStep = {
  filename: string;
  sha256: string;
  size_bytes?: number | null;
  download_url: string;
};

type ExportPrinter = {
  printer_id: string;
  display_name: string;
  nozzle_mm: number;
  material: string;
  layer_height_mm: number;
  available: boolean;
  unavailable_reason?: string | null;
};

type ProjectExportsManifest = {
  project_id: string;
  step: ExportStep;
  printers: ExportPrinter[];
};

type GcodeExportResult = {
  status: "completed";
  project_id: string;
  source_step_sha256: string;
  printer_id: string;
  printer: string;
  material?: string | null;
  nozzle_mm?: number | null;
  layer_height_mm: number;
  slicer: string;
  profile_name?: string | null;
  profile_sha256: string;
  gcode: {
    filename: string;
    sha256: string;
    size_bytes: number;
    download_url: string;
    preview: string;
  };
  report_sha256?: string | null;
  estimated_print_time_seconds?: number | null;
  estimated_filament_grams?: number | null;
  layer_count?: number | null;
  warnings?: string[];
};

type SliceUiState = "idle" | "queued" | "running" | "completed" | "failed";


function normalizeApiUrl(value: string): string {
  // Normalize a configured API origin to the same /api boundary used by FormaWorkspace.
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

const API_URL = normalizeApiUrl(webConfig.apiBaseUrl);


function formatBytes(value?: number | null): string {
  // Format an artifact byte count for the export UI.
  if (!value || value < 1) return "Size unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}


function formatDuration(seconds?: number | null): string | null {
  // Format an optional slicer duration estimate.
  if (!seconds || seconds <= 0) return null;
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  if (hours) return `${hours}h ${minutes}m`;
  return `${Math.max(1, minutes)}m`;
}


function errorMessage(payload: unknown, fallback: string): string {
  // Extract Forma's structured API error message without exposing server internals.
  if (!payload || typeof payload !== "object") return fallback;
  const value = payload as Record<string, unknown>;
  const detail = value.detail;
  if (detail && typeof detail === "object") {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  if (typeof value.message === "string" && value.message.trim()) return value.message;
  return fallback;
}


export default function ProjectExportsPanel({ projectId }: { projectId: string }) {
  // Download canonical STEP or create printer-specific G-code for one project.
  const { authRequired, getToken, isLoaded, isSignedIn, openSignIn } = useFormaAuth();
  const [manifest, setManifest] = useState<ProjectExportsManifest | null>(null);
  const [selectedPrinterId, setSelectedPrinterId] = useState("");
  const [result, setResult] = useState<GcodeExportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [sliceState, setSliceState] = useState<SliceUiState>("idle");
  const [error, setError] = useState<string | null>(null);

  const requestHeaders = useCallback(async (json = false): Promise<Record<string, string>> => {
    const token = await getToken();
    return {
      Accept: "application/json",
      ...(json ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, [getToken]);

  const fetchManifest = useCallback(async () => {
    if (!projectId || !isLoaded || (authRequired && !isSignedIn)) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/exports`, {
        headers: await requestHeaders(),
        cache: "no-store",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorMessage(payload, `Exports request failed (${response.status}).`));
      const next = payload as ProjectExportsManifest;
      setManifest(next);
      setSelectedPrinterId((current) => current || next.printers.find((printer) => printer.available)?.printer_id || next.printers[0]?.printer_id || "");
    } catch (cause) {
      setManifest(null);
      setError(cause instanceof Error ? cause.message : "Project exports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [authRequired, isLoaded, isSignedIn, projectId, requestHeaders]);

  useEffect(() => {
    void fetchManifest();
  }, [fetchManifest]);

  useEffect(() => {
    setResult(null);
    setSliceState("idle");
    setError(null);
    if (!projectId || !selectedPrinterId || typeof window === "undefined") return;
    const stored = window.localStorage.getItem(`forma.export.${projectId}.${selectedPrinterId}`);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as GcodeExportResult;
      if (parsed?.gcode?.sha256 && parsed.printer_id === selectedPrinterId) {
        setResult(parsed);
        setSliceState("completed");
      }
    } catch {
      window.localStorage.removeItem(`forma.export.${projectId}.${selectedPrinterId}`);
    }
  }, [projectId, selectedPrinterId]);

  const selectedPrinter = useMemo(
    () => manifest?.printers.find((printer) => printer.printer_id === selectedPrinterId) || null,
    [manifest, selectedPrinterId],
  );

  const downloadAuthenticated = useCallback(async (relativeUrl: string, filename: string) => {
    setError(null);
    const response = await fetch(`${API_URL}${relativeUrl}`, {
      headers: await requestHeaders(),
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(errorMessage(payload, `Download failed (${response.status}).`));
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }, [requestHeaders]);

  const generateGcode = useCallback(async () => {
    if (!selectedPrinterId) return;
    if (authRequired && !isSignedIn) {
      openSignIn({ redirectUrl: window.location.href });
      return;
    }
    setResult(null);
    setError(null);
    setSliceState("queued");
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    setSliceState("running");
    try {
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/exports/gcode`, {
        method: "POST",
        headers: await requestHeaders(true),
        body: JSON.stringify({ printer_id: selectedPrinterId }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorMessage(payload, `G-code generation failed (${response.status}).`));
      const next = payload as GcodeExportResult;
      setResult(next);
      setSliceState("completed");
      if (typeof window !== "undefined") {
        window.localStorage.setItem(`forma.export.${projectId}.${selectedPrinterId}`, JSON.stringify(next));
      }
    } catch (cause) {
      setSliceState("failed");
      setError(cause instanceof Error ? cause.message : "G-code generation failed.");
    }
  }, [authRequired, isSignedIn, openSignIn, projectId, requestHeaders, selectedPrinterId]);

  if (authRequired && isLoaded && !isSignedIn) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="max-w-md rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-6 text-center">
          <FileBox className="mx-auto mb-3 h-7 w-7 text-[var(--forma-text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--forma-text-strong)]">Sign in to export this project</h3>
          <p className="mt-2 text-xs leading-5 text-[var(--forma-text-muted)]">STEP and generated G-code remain authenticated project artifacts.</p>
          <button type="button" className="mt-4 rounded-lg border border-[var(--forma-border)] px-3 py-2 text-xs font-medium" onClick={() => openSignIn({ redirectUrl: window.location.href })}>Sign in</button>
        </div>
      </div>
    );
  }

  if (loading && !manifest) {
    return <div className="flex h-full items-center justify-center gap-2 text-xs text-[var(--forma-text-muted)]"><Loader2 className="h-4 w-4 animate-spin" />Loading exports…</div>;
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--forma-page)] p-4 sm:p-6">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Manufacturing exports</p>
          <h2 className="mt-1 text-lg font-semibold text-[var(--forma-text-strong)]">Take the design out of Forma</h2>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--forma-text-muted)]">Download the canonical STEP model, or prepare validated printer-specific G-code from the same geometry.</p>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-500/5 p-3 text-xs text-red-200">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <button type="button" className="shrink-0 underline" onClick={() => void fetchManifest()}>Retry</button>
          </div>
        )}

        <section className="rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <FileBox className="mt-0.5 h-5 w-5 text-[var(--forma-text-muted)]" />
              <div>
                <h3 className="text-sm font-semibold text-[var(--forma-text-strong)]">STEP geometry</h3>
                <p className="mt-1 text-xs text-[var(--forma-text-muted)]">{manifest?.step.filename || "assembly.step"} · {formatBytes(manifest?.step.size_bytes)}</p>
                {manifest?.step.sha256 && <p className="mt-1 font-mono text-[10px] text-[var(--forma-text-muted)]">sha256:{manifest.step.sha256.slice(0, 16)}…</p>}
              </div>
            </div>
            <button
              type="button"
              disabled={!manifest?.step}
              onClick={() => manifest?.step && void downloadAuthenticated(manifest.step.download_url, manifest.step.filename).catch((cause) => setError(cause instanceof Error ? cause.message : "STEP download failed."))}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--forma-border)] px-3 py-2 text-xs font-medium text-[var(--forma-text-body)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download className="h-4 w-4" />Download STEP
            </button>
          </div>
        </section>

        <section className="rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4">
          <div className="flex items-start gap-3">
            <Printer className="mt-0.5 h-5 w-5 text-[var(--forma-text-muted)]" />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-[var(--forma-text-strong)]">Printer G-code</h3>
              <p className="mt-1 text-xs leading-5 text-[var(--forma-text-muted)]">Select a validated demo printer profile. Forma slices the stored STEP deterministically; the agent does not write raw G-code.</p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--forma-text-muted)]">Printer</span>
              <select
                value={selectedPrinterId}
                onChange={(event) => setSelectedPrinterId(event.target.value)}
                className="w-full rounded-lg border border-[var(--forma-border)] bg-[var(--forma-page)] px-3 py-2.5 text-sm text-[var(--forma-text-body)]"
              >
                {(manifest?.printers || []).map((printer) => (
                  <option key={printer.printer_id} value={printer.printer_id}>{printer.display_name} · 0.4 mm</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={!selectedPrinter || !selectedPrinter.available || sliceState === "queued" || sliceState === "running"}
              onClick={() => void generateGcode()}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-4 py-2 text-xs font-semibold text-[var(--forma-text-strong)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sliceState === "queued" || sliceState === "running" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {sliceState === "queued" ? "Queued…" : sliceState === "running" ? "Generating…" : result ? "Regenerate G-code" : "Generate G-code"}
            </button>
          </div>

          {selectedPrinter && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--forma-text-muted)]">
              <span>PLA</span><span>{selectedPrinter.nozzle_mm.toFixed(1)} mm nozzle</span><span>{selectedPrinter.layer_height_mm.toFixed(2)} mm Standard</span>
            </div>
          )}
          {selectedPrinter && !selectedPrinter.available && (
            <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3 text-xs leading-5 text-amber-100">
              This printer profile is not configured on the current fabrication worker. {selectedPrinter.unavailable_reason || "OrcaSlicer system profiles are required."}
            </div>
          )}

          {sliceState === "failed" && !error && <p className="mt-3 text-xs text-red-200">G-code generation failed.</p>}

          {result && sliceState === "completed" && (
            <div className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-300" />
                  <div>
                    <p className="text-sm font-semibold text-[var(--forma-text-strong)]">G-code generated</p>
                    <p className="mt-1 text-xs text-[var(--forma-text-muted)]">{result.printer} · {result.profile_name || "0.20 mm Standard"} · {formatBytes(result.gcode.size_bytes)}</p>
                    <div className="mt-1 flex flex-wrap gap-x-3 text-[10px] text-[var(--forma-text-muted)]">
                      {formatDuration(result.estimated_print_time_seconds) && <span>Est. {formatDuration(result.estimated_print_time_seconds)}</span>}
                      {result.estimated_filament_grams ? <span>{result.estimated_filament_grams.toFixed(1)} g filament</span> : null}
                      {result.layer_count ? <span>{result.layer_count} layers</span> : null}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void downloadAuthenticated(result.gcode.download_url, result.gcode.filename).catch((cause) => setError(cause instanceof Error ? cause.message : "G-code download failed."))}
                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-300/20 px-3 py-2 text-xs font-medium text-emerald-100"
                >
                  <Download className="h-4 w-4" />Download G-code
                </button>
              </div>

              <details className="mt-4">
                <summary className="cursor-pointer text-xs font-medium text-[var(--forma-text-body)]">View G-code preview</summary>
                <pre className="mt-2 max-h-72 overflow-auto rounded-lg border border-[var(--forma-border)] bg-black/20 p-3 text-[10px] leading-4 text-[var(--forma-text-muted)]">{result.gcode.preview}</pre>
              </details>
              <p className="mt-3 text-[10px] leading-4 text-[var(--forma-text-muted)]">Profile fingerprint: {result.profile_sha256.slice(0, 16)}… · Review printer-specific G-code before starting a physical print.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}