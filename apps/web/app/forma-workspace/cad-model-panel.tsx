"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Box, Download, LoaderCircle } from "lucide-react";
import type { MeshPayload, OpenCadApiClient } from "opencad-viewport";

import { nativeStepArtifact, resolveCadModel } from "../../lib/cad-model";
import { webConfig } from "../../lib/config";

const OpenCadViewport = dynamic(
  () => import("opencad-viewport").then((module) => module.Viewport3D),
  {
    ssr: false,
    loading: () => <CadModelState icon={<LoaderCircle className="h-7 w-7 animate-spin" />} message="Loading CAD viewport..." />,
  },
);

type CadModelPanelProps = {
  cadModel: unknown;
  apiUrl?: string;
  getHeaders?: () => Promise<Record<string, string>>;
};

export default function CadModelPanel({ cadModel, apiUrl, getHeaders }: CadModelPanelProps) {
  const descriptor = useMemo(() => resolveCadModel(cadModel), [cadModel]);
  const [meshes, setMeshes] = useState<MeshPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setMeshes([]);
    setError(null);
    setLoading(false);

    if (!descriptor || descriptor.kind === "meshes") return;
    if (descriptor.kind === "unsupported") {
      setError(descriptor.reason);
      return;
    }

    const apiBaseUrl = descriptor.apiBaseUrl || webConfig.openCadBaseUrl;
    const kernelUrl = descriptor.kernelUrl || webConfig.openCadKernelUrl || undefined;
    if (!apiBaseUrl) {
      setError("OpenCAD backend is not configured for this CAD model source.");
      return;
    }

    setLoading(true);
    void (async () => {
      try {
        const { OpenCadApiClient } = await import("opencad-viewport");
        const api = new OpenCadApiClient(apiBaseUrl, kernelUrl);
        const mesh = descriptor.kind === "shape"
          ? await api.getMesh(descriptor.shapeId)
          : await loadFileMesh(api, descriptor.url, descriptor.filename);
        if (cancelled) return;
        setMeshes([mesh]);
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Could not load the CAD model.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [descriptor]);

  if (!descriptor) {
    return <CadModelState icon={<Box className="h-7 w-7" />} message="No CAD model attached to this project." />;
  }
  if (descriptor.kind === "unsupported") {
    return <CadModelState icon={<AlertTriangle className="h-7 w-7" />} message={descriptor.reason} />;
  }
  if (descriptor.kind === "meshes") {
    const artifact = nativeStepArtifact(cadModel);
    return <div className="flex h-full min-h-[420px] flex-col">
      {artifact && apiUrl && getHeaders && <StepDownload key={artifact.sha256} artifact={artifact} apiUrl={apiUrl} getHeaders={getHeaders} />}
      <div className="min-h-0 flex-1"><CadViewport meshes={descriptor.meshes} /></div>
    </div>;
  }
  if (loading) {
    return <CadModelState icon={<LoaderCircle className="h-7 w-7 animate-spin" />} message="Preparing CAD model..." />;
  }
  if (!error && !meshes.length) {
    return <CadModelState icon={<LoaderCircle className="h-7 w-7 animate-spin" />} message="Preparing CAD model..." />;
  }
  if (error) {
    return <CadModelState icon={<AlertTriangle className="h-7 w-7" />} message={error} />;
  }
  return <CadViewport meshes={meshes} />;
}

function StepDownload({ artifact, apiUrl, getHeaders }: {
  artifact: { projectId: string; sha256: string };
  apiUrl: string;
  getHeaders: () => Promise<Record<string, string>>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function download() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/opencode/projects/${artifact.projectId}/cad/${artifact.sha256}`, {
        headers: await getHeaders(), signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) throw new Error("The STEP file could not be downloaded. Refresh the project and try again.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "assembly.step";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError("The STEP file could not be downloaded. Refresh the project and try again.");
    } finally {
      setBusy(false);
    }
  }
  return <div className="flex items-center justify-end gap-3 border-b border-[var(--forma-border)] p-3 text-sm">
    {error && <span role="alert">{error}</span>}
    <button type="button" onClick={() => void download()} disabled={busy} className="flex items-center gap-2 rounded-md border border-[var(--forma-border)] px-3 py-2 disabled:opacity-50">
      {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
      {busy ? "Downloading…" : "Download STEP"}
    </button>
  </div>;
}

async function loadFileMesh(
  api: OpenCadApiClient,
  url: string,
  filename: string,
): Promise<MeshPayload> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not fetch CAD model (${response.status}).`);
  const blob = await response.blob();
  const file = new File([blob], filename, { type: blob.type || "application/octet-stream" });
  const imported = await api.importCadFile(file);
  return api.getMesh(imported.shape_id);
}

function CadViewport({ meshes }: { meshes: MeshPayload[] }) {
  return (
    <div className="forma-cad-viewport h-full min-h-[420px] w-full">
      <OpenCadViewport meshes={meshes} />
    </div>
  );
}

function CadModelState({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <div className="flex h-full min-h-[420px] w-full items-center justify-center bg-[var(--forma-page)] px-6 text-center">
      <div className="max-w-md">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] text-[var(--forma-text-muted)]">
          {icon}
        </div>
        <p className="mt-4 text-xs font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">{message}</p>
      </div>
    </div>
  );
}
