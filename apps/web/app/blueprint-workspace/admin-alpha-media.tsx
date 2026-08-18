"use client";

import { useEffect, useState } from "react";
import { ImagePlus, RefreshCw, ShieldCheck } from "lucide-react";

type AdminAlphaMediaProps = {
  apiUrl: string;
  projectId: string | null;
  hasGeneratedImage: boolean;
  disabled?: boolean;
  getRequestHeaders: () => HeadersInit | Promise<HeadersInit>;
  readError: (response: Response) => Promise<string>;
  onGenerated: (projectIR: unknown, response: unknown) => void;
};

export default function AdminAlphaMedia({
  apiUrl,
  projectId,
  hasGeneratedImage,
  disabled = false,
  getRequestHeaders,
  readError,
  onGenerated,
}: AdminAlphaMediaProps) {
  const [status, setStatus] = useState<"idle" | "loading" | "succeeded" | "failed">("idle");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setStatus("idle");
    setMessage(null);
  }, [projectId]);

  const generateMissingImage = async () => {
    if (!projectId || hasGeneratedImage || disabled || status === "loading") return;
    setStatus("loading");
    setMessage("Generating one project image with GMI GPT Image 2.");
    try {
      const response = await fetch(
        `${apiUrl}/admin-alpha/projects/${encodeURIComponent(projectId)}/image`,
        {
          method: "POST",
          headers: await getRequestHeaders(),
        },
      );
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      onGenerated(data?.project_ir ?? null, data);
      setStatus("succeeded");
      setMessage("Project image generated and saved. It is now available as a video source.");
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "Project image generation failed.");
    }
  };

  return (
    <section className="border-b border-[#2a2c33] bg-[#101115] p-4 sm:p-5">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-amber-300" />
            <h2 className="text-xs font-black uppercase tracking-[0.16em] text-white">
              Temporary admin-alpha media tool
            </h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Manual only. Generate a missing still with GMI GPT Image 2, then use the controls below to animate the Docs assembly steps.
          </p>
          {message && (
            <p className={`mt-2 text-xs leading-5 ${status === "failed" ? "text-rose-300" : "text-slate-500"}`}>
              {message}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={generateMissingImage}
          disabled={!projectId || hasGeneratedImage || disabled || status === "loading"}
          className="inline-flex h-11 shrink-0 items-center justify-center gap-2 border border-amber-300/40 px-4 text-xs font-black uppercase tracking-[0.12em] text-amber-100 transition hover:bg-amber-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
        >
          {status === "loading" ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
          {hasGeneratedImage ? "Project image ready" : "Generate missing image"}
        </button>
      </div>
    </section>
  );
}
