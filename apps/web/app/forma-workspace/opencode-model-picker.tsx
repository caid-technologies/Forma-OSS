"use client";

import { useEffect, useId, useState } from "react";
import { FORMA_AGENT_MODEL_STORAGE_KEY, normalizeOpenCodeModel } from "../../lib/opencode";

export function OpenCodeModelPicker() {
  const id = useId();
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const model = window.localStorage.getItem(FORMA_AGENT_MODEL_STORAGE_KEY) || "";
      setValue(model);
      setSaved(model);
      const choices: unknown = JSON.parse(window.localStorage.getItem(`${FORMA_AGENT_MODEL_STORAGE_KEY}.recent`) || "[]");
      if (Array.isArray(choices)) setRecent(choices.filter((item): item is string => typeof item === "string").slice(0, 8));
    } catch { setError("Your browser could not load the saved model choice."); }
  }, []);

  function save(next: string) {
    try {
      const model = normalizeOpenCodeModel(next) || "";
      window.localStorage.setItem(FORMA_AGENT_MODEL_STORAGE_KEY, model);
      const choices = model ? [model, ...recent.filter((item) => item !== model)].slice(0, 8) : recent;
      window.localStorage.setItem(`${FORMA_AGENT_MODEL_STORAGE_KEY}.recent`, JSON.stringify(choices));
      setRecent(choices);
      setValue(model);
      setSaved(model);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The model choice could not be saved.");
    }
  }

  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <label htmlFor={id} className="block text-xs font-medium text-zinc-200">Agent model</label>
      <select aria-label="Switch agent model" value={saved} onChange={(event) => save(event.target.value)}
        className="mt-1.5 h-8 w-full rounded-lg border border-white/15 bg-[#181b22] px-2 text-xs text-zinc-100">
        <option value="">Runtime default</option>
        {Array.from(new Set([saved, ...recent])).filter(Boolean).map((model) => <option key={model} value={model}>{model}</option>)}
      </select>
      <div className="mt-1.5 flex flex-wrap gap-2">
        <input id={id} value={value} maxLength={200} placeholder="Add a provider/model ID"
          aria-describedby={`${id}-help`} aria-invalid={Boolean(error)}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); save(value); } }}
          className="h-8 min-w-0 flex-1 rounded-lg border border-white/15 bg-[#181b22] px-2 text-xs text-zinc-100" />
        <button type="button" onClick={() => save(value)} className="rounded-lg border border-violet-300/25 px-3 py-1 text-xs text-violet-100">Apply</button>
        <button type="button" onClick={() => save("")} className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-300">Runtime default</button>
      </div>
      <p id={`${id}-help`} className="mt-1.5 text-xs leading-5 text-zinc-400">
        Next request: {saved || "runtime default"}. Enter a provider/model ID available on your runtime. Changes apply to new requests; image generation has its own model.
      </p>
      {error && <p role="alert" className="mt-1 text-xs text-rose-300">{error}</p>}
    </div>
  );
}
