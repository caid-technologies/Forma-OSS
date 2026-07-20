"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Briefcase,
  CheckCircle,
  Clock3,
  Copy,
  CreditCard,
  KeyRound,
  ListChecks,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Terminal,
  Trash2,
} from "lucide-react";

const DEFAULT_API_URL = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_API_URL);
const BASE_URL = API_URL.replace(/\/api$/, "");
const API_KEY_PLACEHOLDER = "bp_live_YOUR_API_KEY";

type UserSettingsPayload = {
  owner_user_id: string;
  model_training_opt_out: boolean;
  updated_at: string | null;
};

type ApiKeyRecord = {
  key_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  status: string;
  rate_limit_per_minute: number;
  daily_quota: number;
  daily_usage_count: number;
  last_used_at: string | null;
  created_at: string;
  secret?: string;
};

type ApiKeysPayload = {
  owner_user_id: string;
  defaults: {
    scopes: string[];
    rate_limit_per_minute: number;
    daily_quota: number;
  };
  keys: ApiKeyRecord[];
  created_key?: ApiKeyRecord;
};

type CreditPackage = {
  package_id: string;
  name: string;
  credits: number;
  unit_amount_cents: number;
  currency: string;
};

type CreditTransaction = {
  id: number | null;
  credit_delta: number;
  balance_after: number;
  source: string;
  stripe_checkout_session_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

type CreditsPayload = {
  owner_user_id: string;
  credit_balance: number;
  updated_at: string | null;
  packages: CreditPackage[];
  transactions: CreditTransaction[];
};

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatMoney(cents: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency || "usd",
  }).format((cents || 0) / 100);
}

async function apiErrorMessage(response: Response, fallback: string) {
  const text = await response.text();
  if (response.status === 404) {
    return `${fallback} The backend route was not found at ${API_URL}; restart the backend with the latest code and apply migrations.`;
  }
  try {
    const payload = JSON.parse(text);
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // Keep the raw response below.
  }
  return text || fallback;
}

const apiExamples = {
  llms: `curl ${BASE_URL}/api/v1/llms \\
  -H "Authorization: Bearer ${API_KEY_PLACEHOLDER}"`,
  createJob: `curl ${BASE_URL}/api/v1/jobs \\
  -H "Authorization: Bearer ${API_KEY_PLACEHOLDER}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "A compact USB-C powered LED tester with a button and status indicator",
    "workflow": "default",
    "provider": "baseten",
    "model": "zai-org/GLM-5.2",
    "generate_image": false
  }'`,
  pollJob: `curl ${BASE_URL}/api/v1/jobs/JOB_ID_HERE \\
  -H "Authorization: Bearer ${API_KEY_PLACEHOLDER}"`,
  listJobs: `curl "${BASE_URL}/api/v1/jobs?limit=20" \\
  -H "Authorization: Bearer ${API_KEY_PLACEHOLDER}"`,
  syncGenerate: `curl ${BASE_URL}/api/v1/generate \\
  -H "Authorization: Bearer ${API_KEY_PLACEHOLDER}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "A battery-powered plant watering monitor with soil sensing and an OLED display",
    "workflow": "default",
    "provider": "baseten",
    "model": "zai-org/GLM-5.2",
    "generate_image": false
  }'`,
};

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = code;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="relative min-w-0 border border-[#2c2f37] bg-black">
      <button
        type="button"
        onClick={copyCode}
        className="absolute right-2 top-2 z-10 inline-flex h-9 w-9 items-center justify-center border border-[#343741] bg-[#141519] text-slate-300 hover:border-cyan-300 hover:bg-cyan-300 hover:text-black"
        aria-label={copied ? "Command copied" : "Copy command"}
        title={copied ? "Copied" : "Copy command"}
      >
        {copied ? <CheckCircle className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </button>
      <span className="sr-only" aria-live="polite">{copied ? "Command copied" : ""}</span>
      <pre className="max-w-full select-text overflow-x-auto p-4 pr-14 text-xs leading-6 text-slate-200">
        <code className="whitespace-pre">{code}</code>
      </pre>
    </div>
  );
}

function ApiStep({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-[#2c2f37] bg-[#141519]">
      <div className="flex items-center gap-2 border-b border-[#2c2f37] p-4 text-xs font-black uppercase tracking-wide text-white">
        {icon}
        {title}
      </div>
      <div className="grid gap-3 p-4">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { getToken, isSignedIn } = useAuth();
  const [settings, setSettings] = useState<UserSettingsPayload | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeysPayload | null>(null);
  const [credits, setCredits] = useState<CreditsPayload | null>(null);
  const [newKeyName, setNewKeyName] = useState("Default API key");
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [checkoutPackageId, setCheckoutPackageId] = useState<string | null>(null);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!isSignedIn) return {};
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken, isSignedIn]);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = await authHeaders();
      const [creditsResponse, settingsResponse, keysResponse] = await Promise.all([
        fetch(`${API_URL}/user/billing/credits`, { cache: "no-store", headers }),
        fetch(`${API_URL}/user/settings`, { cache: "no-store", headers }),
        fetch(`${API_URL}/user/api-keys`, { cache: "no-store", headers }),
      ]);
      if (!creditsResponse.ok) throw new Error(await apiErrorMessage(creditsResponse, "Failed to load credits."));
      if (!settingsResponse.ok) throw new Error(await apiErrorMessage(settingsResponse, "Failed to load settings."));
      if (!keysResponse.ok) throw new Error(await apiErrorMessage(keysResponse, "Failed to load API keys."));
      setCredits((await creditsResponse.json()) as CreditsPayload);
      setSettings((await settingsResponse.json()) as UserSettingsPayload);
      setApiKeys((await keysResponse.json()) as ApiKeysPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  async function updateTrainingOptOut(enabled: boolean) {
    setSavingSettings(true);
    setError(null);
    setNotice(null);
    try {
      const headers = await authHeaders();
      const response = await fetch(`${API_URL}/user/settings`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ model_training_opt_out: enabled }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Failed to save privacy setting."));
      setSettings((await response.json()) as UserSettingsPayload);
      setNotice(enabled ? "Training opt-out enabled." : "Training opt-out disabled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save privacy setting.");
    } finally {
      setSavingSettings(false);
    }
  }

  async function createApiKey() {
    setCreatingKey(true);
    setError(null);
    setNotice(null);
    setNewKeySecret(null);
    try {
      const headers = await authHeaders();
      const response = await fetch(`${API_URL}/user/api-keys`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newKeyName,
          scopes: apiKeys?.defaults.scopes || ["generate:project", "read:job"],
          rate_limit_per_minute: apiKeys?.defaults.rate_limit_per_minute || 30,
          daily_quota: apiKeys?.defaults.daily_quota || 100,
        }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Failed to create API key."));
      const data = (await response.json()) as ApiKeysPayload;
      setApiKeys(data);
      setNewKeySecret(data.created_key?.secret || null);
      setNotice("API key created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create API key.");
    } finally {
      setCreatingKey(false);
    }
  }

  async function revokeApiKey(keyId: string) {
    setRevokingKeyId(keyId);
    setError(null);
    setNotice(null);
    try {
      const headers = await authHeaders();
      const response = await fetch(`${API_URL}/user/api-keys/${encodeURIComponent(keyId)}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Failed to revoke API key."));
      setApiKeys((await response.json()) as ApiKeysPayload);
      setNotice("API key revoked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke API key.");
    } finally {
      setRevokingKeyId(null);
    }
  }

  async function startCheckout(packageId: string) {
    setCheckoutPackageId(packageId);
    setError(null);
    setNotice(null);
    try {
      const headers = await authHeaders();
      const response = await fetch(`${API_URL}/user/billing/checkout-sessions`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          package_id: packageId,
          quantity: 1,
          success_url: `${window.location.origin}/settings?credits=success`,
          cancel_url: `${window.location.origin}/settings?credits=cancelled`,
        }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Failed to start Stripe Checkout."));
      const data = (await response.json()) as { checkout_url?: string };
      if (!data.checkout_url) throw new Error("Stripe did not return a Checkout URL.");
      window.location.href = data.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Stripe Checkout.");
      setCheckoutPackageId(null);
    }
  }

  async function copySecret(value: string) {
    await navigator.clipboard.writeText(value);
    setNotice("API key copied.");
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
                <Settings className="h-4 w-4 text-cyan-300" />
                <h1 className="truncate text-lg font-black uppercase tracking-wide text-white">Settings</h1>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Account preferences, privacy controls, and developer access.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={loadSettings}
            disabled={loading}
            className="inline-flex h-11 shrink-0 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Reload
          </button>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-7xl gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-5">
          {error && (
            <div className="border border-rose-500/40 bg-rose-950/30 p-4 text-sm leading-6 text-rose-200">
              <div className="flex items-center gap-2 font-black uppercase tracking-wide">
                <AlertTriangle className="h-4 w-4" />
                Error
              </div>
              <p className="mt-2 break-words">{error}</p>
            </div>
          )}

          {notice && (
            <div className="border border-emerald-500/40 bg-emerald-950/30 p-4 text-sm leading-6 text-emerald-200">
              <div className="flex items-center gap-2 font-black uppercase tracking-wide">
                <CheckCircle className="h-4 w-4" />
                Saved
              </div>
              <p className="mt-2">{notice}</p>
            </div>
          )}

          <article className="border border-[#2c2f37] bg-[#17181d]">
            <div className="flex flex-col gap-4 border-b border-[#2c2f37] p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                  <CreditCard className="h-4 w-4 text-cyan-300" />
                  Credits
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  Current balance: <span className="font-mono text-cyan-200">{credits?.credit_balance ?? 0}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={loadSettings}
                disabled={loading}
                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>
            <div className="grid gap-4 p-5">
              <div className="grid gap-3 md:grid-cols-3">
                {(credits?.packages || []).map((pack) => (
                  <div key={pack.package_id} className="border border-[#2c2f37] bg-[#141519] p-4">
                    <div className="text-xs font-black uppercase tracking-wide text-white">{pack.name}</div>
                    <div className="mt-3 font-mono text-2xl font-black text-cyan-200">{pack.credits}</div>
                    <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">credits</p>
                    <p className="mt-3 text-sm font-black text-white">{formatMoney(pack.unit_amount_cents, pack.currency)}</p>
                    <button
                      type="button"
                      onClick={() => startCheckout(pack.package_id)}
                      disabled={Boolean(checkoutPackageId)}
                      className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 bg-white px-3 text-xs font-black uppercase tracking-widest text-black hover:bg-slate-200 disabled:cursor-wait disabled:opacity-50"
                    >
                      <CreditCard className="h-4 w-4" />
                      {checkoutPackageId === pack.package_id ? "Opening" : "Buy"}
                    </button>
                  </div>
                ))}
              </div>
              {credits?.transactions.length ? (
                <div className="border border-[#2c2f37]">
                  {credits.transactions.map((transaction) => (
                    <div key={`${transaction.source}-${transaction.created_at}-${transaction.credit_delta}`} className="flex flex-col gap-2 border-b border-[#2c2f37] p-3 last:border-b-0 md:flex-row md:items-center md:justify-between">
                      <div className="min-w-0">
                        <div className="text-xs font-black uppercase tracking-wide text-white">+{transaction.credit_delta} credits</div>
                        <p className="mt-1 break-all font-mono text-[11px] text-slate-500">{transaction.source} · {transaction.stripe_checkout_session_id || "manual"}</p>
                      </div>
                      <div className="text-xs text-slate-500 md:text-right">
                        <div>{formatTimestamp(transaction.created_at)}</div>
                        <div className="mt-1 font-mono">balance {transaction.balance_after}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border border-[#2c2f37] p-4 text-sm text-slate-500">No credit activity yet.</div>
              )}
            </div>
          </article>

          <article className="border border-[#2c2f37] bg-[#17181d]">
            <div className="border-b border-[#2c2f37] p-5">
              <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                <KeyRound className="h-4 w-4 text-cyan-300" />
                API Keys
              </div>
            </div>
            <div className="grid gap-3 p-4">
              {apiKeys?.keys.length ? (
                apiKeys.keys.map((key) => (
                  <div key={key.key_id} className="border border-[#2c2f37] bg-[#141519] p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-sm font-black uppercase tracking-wide text-white">{key.name}</h3>
                          <span className={`border px-2 py-1 text-[10px] font-black uppercase ${key.status === "active" ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300" : "border-rose-400/40 bg-rose-500/10 text-rose-200"}`}>
                            {key.status}
                          </span>
                        </div>
                        <p className="mt-2 break-all font-mono text-xs text-slate-500">{key.key_prefix}... · {key.key_id}</p>
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          {key.daily_usage_count || 0}/{key.daily_quota} today · {key.rate_limit_per_minute}/min · last used {formatTimestamp(key.last_used_at)}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {key.scopes.map((scope) => (
                            <span key={scope} className="border border-[#2c2f37] px-2 py-1 font-mono text-[10px] text-slate-400">{scope}</span>
                          ))}
                        </div>
                      </div>
                      {key.status === "active" && (
                        <button
                          type="button"
                          onClick={() => revokeApiKey(key.key_id)}
                          disabled={revokingKeyId === key.key_id}
                          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 border border-rose-400/40 px-3 text-xs font-black uppercase tracking-widest text-rose-200 hover:bg-rose-500 hover:text-white disabled:cursor-wait disabled:opacity-50"
                        >
                          <Trash2 className="h-4 w-4" />
                          Revoke
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="border border-[#2c2f37] p-4 text-sm text-slate-500">No API keys yet.</div>
              )}
            </div>
          </article>

          <article className="border border-[#2c2f37] bg-[#17181d]">
            <div className="border-b border-[#2c2f37] p-5">
              <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                <ShieldCheck className="h-4 w-4 text-cyan-300" />
                Privacy
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                Owner: <span className="font-mono text-slate-400">{settings?.owner_user_id || "loading"}</span>
              </p>
            </div>
            <div className="p-5">
              <label className="flex cursor-pointer items-start justify-between gap-4 border border-[#2c2f37] bg-[#141519] p-4">
                <div className="min-w-0">
                  <div className="text-sm font-black uppercase tracking-wide text-white">Opt out of model training</div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    Generated outputs are marked as excluded from model-training datasets.
                  </p>
                  <p className="mt-2 text-xs text-slate-600">Updated {formatTimestamp(settings?.updated_at)}</p>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(settings?.model_training_opt_out)}
                  disabled={savingSettings || loading}
                  onChange={(event) => updateTrainingOptOut(event.target.checked)}
                  className="mt-1 h-5 w-5 shrink-0 accent-cyan-300"
                />
              </label>
            </div>
          </article>

          <article className="border border-[#2c2f37] bg-[#17181d]">
            <div className="border-b border-[#2c2f37] p-5">
              <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                <KeyRound className="h-4 w-4 text-cyan-300" />
                Key Storage
              </div>
            </div>
            <div className="grid gap-3 p-5 text-xs leading-5 text-slate-500">
              <p>
                Blueprint user API keys are production database records. The full secret is shown once, then discarded; only a keyed HMAC hash, prefix, owner, scopes, quotas, status, and audit timestamps are stored.
              </p>
              <p>
                Production deployments must set <span className="font-mono text-slate-300">BLUEPRINT_API_KEY_PEPPER</span>. Rotating that pepper invalidates existing keys, so rotate by issuing replacement keys before changing it.
              </p>
              <p>
                Provider credentials like OpenAI or Anthropic are not user API keys. In production they belong in deployment secrets or a KMS-backed vault because the backend must decrypt/use them; the local JSON integration store is disabled for deployed environments.
              </p>
            </div>
          </article>

          <article className="border border-[#2c2f37] bg-[#17181d]">
            <div className="border-b border-[#2c2f37] p-5">
              <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                <BookOpen className="h-4 w-4 text-cyan-300" />
                API Management
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                Base URL: <span className="break-all font-mono text-cyan-200">{BASE_URL}/api/v1</span>
              </p>
            </div>
            <div className="grid gap-4 p-5">
              <div className="grid gap-3 text-xs leading-5 text-slate-500 md:grid-cols-3">
                <div className="flex gap-2 border border-[#2c2f37] bg-[#141519] p-3">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                  <span>Use Authorization Bearer or X-API-Key headers.</span>
                </div>
                <div className="flex gap-2 border border-[#2c2f37] bg-[#141519] p-3">
                  <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
                  <span>Create async jobs and poll for production clients.</span>
                </div>
                <div className="flex gap-2 border border-[#2c2f37] bg-[#141519] p-3">
                  <Briefcase className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
                  <span>Job APIs require the read:job key scope.</span>
                </div>
              </div>

              <ApiStep icon={<ListChecks className="h-4 w-4 text-cyan-300" />} title="List Available Models">
                <p className="text-xs leading-5 text-slate-500">Returns deployment-enabled providers and models.</p>
                <CodeBlock code={apiExamples.llms} />
              </ApiStep>

              <ApiStep icon={<Clock3 className="h-4 w-4 text-cyan-300" />} title="Create Async Job">
                <p className="text-xs leading-5 text-slate-500">Returns immediately with job_id, status, and poll_url. This example uses GLM through Baseten.</p>
                <CodeBlock code={apiExamples.createJob} />
              </ApiStep>

              <div className="grid gap-4">
                <ApiStep icon={<RefreshCw className="h-4 w-4 text-cyan-300" />} title="Poll Job Status">
                  <p className="text-xs leading-5 text-slate-500">Poll until status is succeeded or failed.</p>
                  <CodeBlock code={apiExamples.pollJob} />
                </ApiStep>

                <ApiStep icon={<Briefcase className="h-4 w-4 text-cyan-300" />} title="List Jobs">
                  <p className="text-xs leading-5 text-slate-500">Lists jobs for the calling API key.</p>
                  <CodeBlock code={apiExamples.listJobs} />
                </ApiStep>
              </div>

              <ApiStep icon={<Terminal className="h-4 w-4 text-cyan-300" />} title="Synchronous Generate">
                <p className="text-xs leading-5 text-slate-500">Blocks until generation finishes. Keep async jobs as the default for app clients.</p>
                <CodeBlock code={apiExamples.syncGenerate} />
              </ApiStep>
            </div>
          </article>

        </div>

        <aside className="border border-[#2c2f37] bg-[#17181d] p-5">
          <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
            <Plus className="h-4 w-4 text-cyan-300" />
            New API Key
          </div>
          <div className="mt-5 grid gap-4">
            <label className="grid gap-2 text-xs font-black uppercase tracking-wide text-slate-400">
              Name
              <input
                value={newKeyName}
                onChange={(event) => setNewKeyName(event.target.value)}
                className="h-11 border border-[#2c2f37] bg-black px-3 text-sm normal-case tracking-normal text-white outline-none focus:border-cyan-300"
              />
            </label>
            <button
              type="button"
              onClick={createApiKey}
              disabled={creatingKey}
              className="inline-flex h-11 items-center justify-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-widest text-black hover:bg-slate-200 disabled:cursor-wait disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              Create Key
            </button>
          </div>

          {newKeySecret && (
            <div className="mt-5 border border-cyan-300/40 bg-cyan-950/20 p-4">
              <div className="text-xs font-black uppercase tracking-widest text-cyan-200">New secret</div>
              <input readOnly value={newKeySecret} className="mt-3 h-11 w-full border border-[#2c2f37] bg-black px-3 font-mono text-xs text-white" />
              <button
                type="button"
                onClick={() => copySecret(newKeySecret)}
                className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 border border-cyan-300/40 px-3 text-xs font-black uppercase tracking-widest text-cyan-100 hover:bg-cyan-300 hover:text-black"
              >
                <Copy className="h-4 w-4" />
                Copy
              </button>
              <p className="mt-2 text-xs leading-5 text-slate-500">This full secret is only shown once.</p>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
