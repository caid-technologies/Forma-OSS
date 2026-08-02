"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Copy } from "lucide-react";

import { copyText } from "../lib/clipboard";

type CopyState = "idle" | "copied" | "error";

const RESET_DELAY_MS = 2000;

type CopyButtonProps = {
  value: string;
  /** Accessible name for the idle button. */
  label?: string;
  className?: string;
};

/** Icon button that copies `value` and reports the outcome to sighted and screen reader users. */
export default function CopyButton({ value, label = "Copy message", className = "" }: CopyButtonProps) {
  const [state, setState] = useState<CopyState>("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const copied = await copyText(value);
    if (!mounted.current) return;

    setState(copied ? "copied" : "error");
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => {
      if (mounted.current) setState("idle");
    }, RESET_DELAY_MS);
  }, [value]);

  if (!value.trim()) return null;

  const hint = state === "copied" ? "Copied" : state === "error" ? "Copy failed" : label;

  return (
    <span className={`inline-flex items-center ${className}`}>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={label}
        title={hint}
        className="inline-flex h-6 w-6 shrink-0 items-center justify-center border border-transparent text-slate-500 transition hover:border-[#2c2f37] hover:bg-white/5 hover:text-white focus-visible:border-cyan-300 focus-visible:text-white focus-visible:outline-none"
      >
        {state === "copied" ? (
          <Check className="h-3.5 w-3.5 text-emerald-300" />
        ) : state === "error" ? (
          <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {state === "copied" ? "Message copied to clipboard" : state === "error" ? "Copying the message failed" : ""}
      </span>
    </span>
  );
}
