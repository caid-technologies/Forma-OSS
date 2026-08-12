"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Copy } from "lucide-react";

import { copyText } from "../../lib/clipboard";

type CopyState = "idle" | "copied" | "error";

const RESET_DELAY_MS = 2000;

export default function CitationCopyButton({ value, label }: { value: string; label: string }) {
  const [state, setState] = useState<CopyState>("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const copied = await copyText(value);
    setState(copied ? "copied" : "error");

    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setState("idle"), RESET_DELAY_MS);
  }, [value]);

  const buttonLabel = state === "copied" ? "Copied" : state === "error" ? "Try again" : label;

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex h-9 shrink-0 items-center gap-2 border border-[#343740] px-3 text-[11px] font-black uppercase tracking-widest text-slate-400 transition hover:border-slate-400 hover:text-white focus-visible:border-cyan-300 focus-visible:outline-none"
      aria-live="polite"
    >
      {state === "copied" ? (
        <Check className="h-3.5 w-3.5 text-emerald-300" aria-hidden="true" />
      ) : state === "error" ? (
        <AlertTriangle className="h-3.5 w-3.5 text-rose-300" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {buttonLabel}
    </button>
  );
}
