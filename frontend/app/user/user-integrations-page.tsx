"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  KeyRound,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";

const DEFAULT_API_URL = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_API_URL);

type IntegrationFieldStatus = {
  id: string;
  label: string;
  env_names: string[];
  secret: boolean;
  placeholder: string;
  help: string;
  configured: boolean;
  saved: boolean;
  source: "saved" | "environment" | "unset" | string;
  masked_value: string | null;
  value: string | null;
};

type IntegrationStatus = {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
  saved: boolean;
  configured: boolean;
  updated_at: string | null;
  fields: IntegrationFieldStatus[];
};

type IntegrationsPayload = {
  version: number;
  config_path: string;
  updated_at: string;
  integrations: IntegrationStatus[];
};

type IntegrationFormState = {
  enabled: boolean;
  fields: Record<string, string>;
};

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function formFromIntegration(integration: IntegrationStatus): IntegrationFormState {
  const fields = integration.fields.reduce<Record<string, string>>((acc, field) => {
    acc[field.id] = field.secret ? "" : field.value || "";
    return acc;
  }, {});
  return { enabled: integration.enabled, fields };
}

function sourceLabel(field: IntegrationFieldStatus) {
  if (field.source === "saved") return "Saved local";
  if (field.source === "environment") return "Environment";
  return "Unset";
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Never saved";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function UserIntegrationsPage() {
  const [payload, setPayload] = useState<IntegrationsPayload | null>(null);
  const [forms, setForms] = useState<Record<string, IntegrationFormState>>({});
  const [selectedId, setSelectedId] = useState<string>("runtime");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedIntegration = useMemo(() => {
    if (!payload?.integrations.length) return null;
    return payload.integrations.find((integration) => integration.id === selectedId) || payload.integrations[0];
  }, [payload, selectedId]);

  const loadIntegrations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations`, { cache: "no-store" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as IntegrationsPayload;
      setPayload(data);
      setForms(Object.fromEntries(data.integrations.map((integration) => [integration.id, formFromIntegration(integration)])));
      setSelectedId((current) => data.integrations.some((integration) => integration.id === current) ? current : data.integrations[0]?.id || "runtime");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  function updateField(integrationId: string, fieldId: string, value: string) {
    setForms((current) => ({
      ...current,
      [integrationId]: {
        enabled: current[integrationId]?.enabled ?? true,
        fields: {
          ...(current[integrationId]?.fields || {}),
          [fieldId]: value,
        },
      },
    }));
  }

  function updateEnabled(integrationId: string, enabled: boolean) {
    setForms((current) => ({
      ...current,
      [integrationId]: {
        enabled,
        fields: current[integrationId]?.fields || {},
      },
    }));
  }

  async function saveIntegration(integration: IntegrationStatus, clearFields: string[] = []) {
    const form = forms[integration.id] || formFromIntegration(integration);
    const fields: Record<string, string> = {};
    const clearFieldSet = new Set(clearFields);
    integration.fields.forEach((field) => {
      if (clearFieldSet.has(field.id)) return;
      const value = form.fields[field.id] || "";
      if (field.secret && !value.trim()) return;
      fields[field.id] = value;
    });

    setSavingId(integration.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/${encodeURIComponent(integration.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: form.enabled,
          fields,
          clear_fields: clearFields,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as IntegrationsPayload;
      setPayload(data);
      setForms(Object.fromEntries(data.integrations.map((item) => [item.id, formFromIntegration(item)])));
      setNotice(`${integration.label} saved and applied to runtime.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to save ${integration.label}.`);
    } finally {
      setSavingId(null);
    }
  }

  async function clearIntegration(integration: IntegrationStatus) {
    setSavingId(integration.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/${encodeURIComponent(integration.id)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as IntegrationsPayload;
      setPayload(data);
      setForms(Object.fromEntries(data.integrations.map((item) => [item.id, formFromIntegration(item)])));
      setNotice(`${integration.label} saved config cleared.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to clear ${integration.label}.`);
    } finally {
      setSavingId(null);
    }
  }

  async function reloadRuntime() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/reload`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as IntegrationsPayload;
      setPayload(data);
      setForms(Object.fromEntries(data.integrations.map((integration) => [integration.id, formFromIntegration(integration)])));
      setNotice("Saved integrations reloaded into runtime.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reload integrations.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#141519] font-sans text-slate-100">
      <header className="border-b border-[#292b31] bg-[#141519]/95 px-4 py-4">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              className="inline-flex h-11 shrink-0 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black"
            >
              <ArrowLeft className="h-4 w-4" />
              Home
            </Link>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-cyan-300" />
                <h1 className="truncate text-lg font-black uppercase tracking-wide text-white">User Integrations</h1>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Local API keys and provider defaults saved outside git, then applied during backend runtime.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={reloadRuntime}
            disabled={loading}
            className="inline-flex h-11 shrink-0 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Reload
          </button>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-7xl gap-5 px-4 py-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="min-h-0 border border-[#2c2f37] bg-[#17181d]">
          <div className="border-b border-[#2c2f37] p-4">
            <div className="inline-flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
              <KeyRound className="h-4 w-4 text-cyan-300" />
              Providers
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-500">
              {payload?.integrations.length || 0} integrations. Config file:{" "}
              <span className="break-all font-mono text-slate-400">{payload?.config_path || "loading"}</span>
            </p>
          </div>

          <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-3">
            {loading && !payload ? (
              <div className="border border-[#2c2f37] p-4 text-sm text-slate-500">Loading integrations...</div>
            ) : (
              payload?.integrations.map((integration) => (
                <button
                  key={integration.id}
                  type="button"
                  onClick={() => setSelectedId(integration.id)}
                  className={`mb-3 block w-full border p-4 text-left transition ${
                    selectedIntegration?.id === integration.id
                      ? "border-cyan-300 bg-cyan-300/10"
                      : "border-[#2c2f37] bg-[#141519] hover:border-slate-500"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-black uppercase tracking-wide text-white">{integration.label}</span>
                    <span
                      className={`shrink-0 border px-2 py-1 text-[10px] font-black uppercase ${
                        integration.configured
                          ? integration.enabled
                            ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                            : "border-amber-400/40 bg-amber-500/10 text-amber-300"
                          : "border-[#2c2f37] text-slate-500"
                      }`}
                    >
                      {integration.configured ? (integration.enabled ? "Ready" : "Off") : "Unset"}
                    </span>
                  </div>
                  <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">{integration.description}</p>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="min-w-0">
          {error && (
            <div className="mb-4 border border-rose-500/40 bg-rose-950/30 p-4 text-sm leading-6 text-rose-200">
              <div className="flex items-center gap-2 font-black uppercase tracking-wide">
                <AlertTriangle className="h-4 w-4" />
                Error
              </div>
              <p className="mt-2 break-words">{error}</p>
            </div>
          )}

          {notice && (
            <div className="mb-4 border border-emerald-500/40 bg-emerald-950/30 p-4 text-sm leading-6 text-emerald-200">
              <div className="flex items-center gap-2 font-black uppercase tracking-wide">
                <CheckCircle className="h-4 w-4" />
                Applied
              </div>
              <p className="mt-2">{notice}</p>
            </div>
          )}

          {selectedIntegration ? (
            <article className="border border-[#2c2f37] bg-[#17181d]">
              <div className="flex flex-col gap-4 border-b border-[#2c2f37] p-5 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-black uppercase tracking-wide text-white">{selectedIntegration.label}</h2>
                    <span
                      className={`border px-2 py-1 text-[10px] font-black uppercase ${
                        selectedIntegration.configured
                          ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                          : "border-[#2c2f37] text-slate-500"
                      }`}
                    >
                      {selectedIntegration.configured ? "Configured" : "Not configured"}
                    </span>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{selectedIntegration.description}</p>
                  <p className="mt-2 text-xs text-slate-500">Updated {formatTimestamp(selectedIntegration.updated_at)}</p>
                </div>

                <div className="flex shrink-0 flex-wrap gap-2">
                  <label className="inline-flex h-11 cursor-pointer items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-300">
                    <input
                      type="checkbox"
                      checked={forms[selectedIntegration.id]?.enabled ?? selectedIntegration.enabled}
                      onChange={(event) => updateEnabled(selectedIntegration.id, event.target.checked)}
                      className="h-4 w-4 accent-cyan-300"
                    />
                    Enabled
                  </label>
                  <button
                    type="button"
                    onClick={() => saveIntegration(selectedIntegration)}
                    disabled={savingId === selectedIntegration.id}
                    className="inline-flex h-11 items-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-widest text-black hover:bg-slate-200 disabled:cursor-wait disabled:opacity-50"
                  >
                    <Save className="h-4 w-4" />
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={() => clearIntegration(selectedIntegration)}
                    disabled={savingId === selectedIntegration.id}
                    className="inline-flex h-11 items-center gap-2 border border-rose-400/40 px-4 text-xs font-black uppercase tracking-widest text-rose-200 hover:bg-rose-500 hover:text-white disabled:cursor-wait disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    Clear
                  </button>
                </div>
              </div>

              <div className="grid gap-4 p-5">
                {selectedIntegration.fields.map((field) => {
                  const fieldValue = forms[selectedIntegration.id]?.fields[field.id] || "";
                  const placeholder = field.secret && field.masked_value
                    ? `Saved: ${field.masked_value}`
                    : field.placeholder || field.env_names[0] || "";
                  return (
                    <div key={field.id} className="border border-[#2c2f37] bg-[#141519] p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="min-w-0">
                          <label htmlFor={`${selectedIntegration.id}-${field.id}`} className="text-sm font-black uppercase tracking-wide text-white">
                            {field.label}
                          </label>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <span className="border border-[#2c2f37] px-2 py-1 text-[10px] font-black uppercase text-slate-500">
                              {sourceLabel(field)}
                            </span>
                            {field.secret && (
                              <span className="border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[10px] font-black uppercase text-cyan-200">
                                Secret
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="min-w-0 text-left md:text-right">
                          <p className="break-all font-mono text-[11px] leading-5 text-slate-500">
                            {field.env_names.join(", ")}
                          </p>
                        </div>
                      </div>

                      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                        <input
                          id={`${selectedIntegration.id}-${field.id}`}
                          type={field.secret ? "password" : "text"}
                          value={fieldValue}
                          onChange={(event) => updateField(selectedIntegration.id, field.id, event.target.value)}
                          placeholder={placeholder}
                          autoComplete="off"
                          className="h-11 min-w-0 flex-1 border border-[#2c2f37] bg-black px-3 font-mono text-sm text-white outline-none placeholder:text-slate-700 focus:border-cyan-300"
                        />
                        {field.saved && (
                          <button
                            type="button"
                            onClick={() => saveIntegration(selectedIntegration, [field.id])}
                            disabled={savingId === selectedIntegration.id}
                            className="inline-flex h-11 items-center justify-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
                          >
                            <Trash2 className="h-4 w-4" />
                            Clear saved
                          </button>
                        )}
                      </div>
                      {field.help && <p className="mt-2 text-xs leading-5 text-slate-500">{field.help}</p>}
                    </div>
                  );
                })}
              </div>
            </article>
          ) : (
            <div className="border border-[#2c2f37] bg-[#17181d] p-6 text-slate-500">No integrations found.</div>
          )}
        </section>
      </section>
    </main>
  );
}
