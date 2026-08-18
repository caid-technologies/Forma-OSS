"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle,
  ChevronDown,
  FlaskConical,
  KeyRound,
  Moon,
  Palette,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Snowflake,
  Sun,
  Trash2,
} from "lucide-react";
import {
  gmiImageSettingFieldIds,
  IMAGE_MODEL_OPTIONS,
  modelOptionsForField,
  settingOptionsForField,
  type ProviderModelOption,
} from "../../lib/provider-model-catalog";
import { useFormaAuth } from "../../lib/forma-auth";
import { useTheme } from "../../lib/theme-provider";
import { arcticLight, solarizedLight } from "../../lib/theme";
import { webConfig } from "../../lib/config";
import { ProviderMarkTile } from "../../components/provider-mark";
import { imageOutputIsEnabled, parsePreferredLlmProvider, settingsNavBadge, type SettingsNavBadge as SettingsNavBadgeModel } from "../../lib/settings-nav-status";

const API_URL = normalizeApiUrl(webConfig.apiBaseUrl);

const FIELD_CONTROL_CLASS =
  "h-9 w-full rounded-lg border border-[#2c2f37] bg-[#101115] px-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-60";
const BUTTON_PRIMARY_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-lg bg-white px-3 text-xs font-medium text-black transition hover:bg-slate-200 disabled:cursor-wait disabled:opacity-50";
const BUTTON_OUTLINE_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-lg border border-[#2c2f37] px-3 text-xs font-medium text-slate-300 transition hover:bg-white/5 hover:text-white disabled:cursor-wait disabled:opacity-50";
const BUTTON_DANGER_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-lg border border-rose-400/30 px-3 text-xs font-medium text-rose-200 transition hover:bg-rose-500/15 disabled:cursor-wait disabled:opacity-50";
const CARD_SURFACE_CLASS = "rounded-xl border border-[#2c2f37] bg-[#181b22]";
const STATUS_PILL_CLASS = "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium";

type IntegrationFieldStatus = {
  id: string;
  label: string;
  env_names: string[];
  secret: boolean;
  placeholder: string;
  help: string;
  configured: boolean;
  saved: boolean;
  editable: boolean;
  policy_status: "enabled" | "conditional" | "disabled" | string;
  policy_blocked: boolean;
  policy_conditional: boolean;
  policy_notice: string;
  source: "saved" | "environment" | "unset" | string;
  masked_value: string | null;
  value: string | null;
};

type IntegrationStatus = {
  id: string;
  label: string;
  description: string;
  policy_status?: "enabled" | "conditional" | "disabled" | string;
  policy_notice?: string;
  enabled: boolean;
  saved: boolean;
  configured: boolean;
  updated_at: string | null;
  fields: IntegrationFieldStatus[];
};

type IntegrationsPayload = {
  version: number;
  updated_at: string;
  integrations: IntegrationStatus[];
  image_model_test_available?: boolean;
};

type DataUsagePreference = {
  allow_model_training: boolean;
  model_training_opt_out: boolean;
  source: "default" | "user";
  created_at: string | null;
  updated_at: string | null;
};

type ImageModelTestResult = {
  ok: boolean;
  provider: string;
  model: string;
  size: string;
  output_format: string;
  elapsed_ms: number;
  prompt: string;
  prompt_original_length: number | null;
  prompt_final_length: number | null;
  prompt_compacted: boolean;
  image_data_url: string;
  config: Record<string, unknown>;
};

type IntegrationFormState = {
  enabled: boolean;
  fields: Record<string, string>;
};

type ImageProviderOption = {
  id: string;
  label: string;
  integrationId: string | null;
  modelFieldId: string | null;
  models: ProviderModelOption[];
  preconfigured?: boolean;
  credentialFieldIds: string[];
  configFieldIds: string[];
  advancedFieldIds: string[];
  summary: string;
  tier: "basic" | "advanced";
};

const IMAGE_PROVIDER_OPTIONS: ImageProviderOption[] = [
  {
    id: "vertex",
    label: "Google Vertex AI",
    integrationId: "vertex",
    modelFieldId: "image_model",
    models: IMAGE_MODEL_OPTIONS.vertex,
    credentialFieldIds: ["project", "location"],
    configFieldIds: ["image_model"],
    advancedFieldIds: ["image_resolution", "image_aspect_ratio", "image_output_format", "image_timeout_seconds"],
    summary: "Nano Banana image generation using your Google Cloud project and Application Default Credentials.",
    tier: "advanced",
  },
  {
    id: "huggingface",
    label: "Hugging Face",
    integrationId: "huggingface",
    modelFieldId: "image_model",
    models: IMAGE_MODEL_OPTIONS.huggingface,
    credentialFieldIds: ["api_key", "token_scope_confirmation"],
    configFieldIds: ["image_model", "image_inference_provider"],
    advancedFieldIds: [
      "image_model_revision",
      "image_model_license",
      "image_size",
      "image_guidance_scale",
      "image_steps",
      "image_output_format",
      "image_gated_models_enabled",
      "image_timeout_seconds",
    ],
    summary: "Hosted Hugging Face image inference. Add a scoped HF token; Forma preselects FLUX.",
    tier: "advanced",
  },
  {
    id: "openai",
    label: "OpenAI",
    integrationId: "openai",
    modelFieldId: "image_model",
    models: IMAGE_MODEL_OPTIONS.openai,
    credentialFieldIds: ["api_key"],
    configFieldIds: ["image_model"],
    advancedFieldIds: ["image_size", "image_quality", "image_output_format", "image_timeout_seconds", "base_url"],
    summary: "OpenAI image generation. Add an OpenAI key where BYOK is allowed.",
    tier: "basic",
  },
  {
    id: "gmi",
    label: "GMI",
    integrationId: "gmi",
    modelFieldId: "image_model",
    models: IMAGE_MODEL_OPTIONS.gmi,
    credentialFieldIds: ["api_key", "key_delegation_confirmation"],
    configFieldIds: ["image_model"],
    advancedFieldIds: [
      "image_base_url",
      "image_size",
      "image_quality",
      "image_output_format",
      "image_output_compression",
      "image_background",
      "image_moderation",
      "image_resolution",
      "image_aspect_ratio",
      "image_timeout_seconds",
    ],
    summary: "GMI Cloud image generation through its native GPT Image endpoint or request queue, with model-specific settings.",
    tier: "advanced",
  },
  {
    id: "together",
    label: "Together AI",
    integrationId: "together",
    modelFieldId: "image_model",
    models: IMAGE_MODEL_OPTIONS.together,
    credentialFieldIds: ["api_key", "project_key_confirmation"],
    configFieldIds: ["image_model"],
    advancedFieldIds: ["image_base_url", "image_size", "image_steps", "image_output_format", "image_timeout_seconds"],
    summary: "Together AI image generation. Add a project-scoped key dedicated to Forma.",
    tier: "advanced",
  },
  {
    id: "openai-compatible",
    label: "OpenAI-compatible",
    integrationId: "image",
    modelFieldId: "model",
    models: IMAGE_MODEL_OPTIONS["openai-compatible"],
    credentialFieldIds: ["api_key", "base_url"],
    configFieldIds: ["model"],
    advancedFieldIds: ["size", "quality", "output_format", "timeout_seconds"],
    summary: "Generic OpenAI-compatible image endpoint. Add the provider key and base URL.",
    tier: "advanced",
  },
  {
    id: "none",
    label: "Off",
    integrationId: null,
    modelFieldId: null,
    models: [],
    credentialFieldIds: [],
    configFieldIds: [],
    advancedFieldIds: [],
    summary: "Disable generated product images.",
    tier: "basic",
  },
];

type IntegrationView = "all" | "llm" | "image";

type IntegrationNavigationDefinition = {
  integrationId: string;
  view: IntegrationView;
  label?: string;
  logo?: string;
  imageProviderId?: string;
};

type ProviderBrandNavDefinition = {
  id: string;
  label: string;
  logo: string;
  items: IntegrationNavigationDefinition[];
};

type IntegrationNavBlockDefinition =
  | { type: "items"; items: IntegrationNavigationDefinition[] }
  | { type: "brand"; brand: ProviderBrandNavDefinition };

type IntegrationNavSectionDefinition = {
  id: string;
  label: string;
  blocks: IntegrationNavBlockDefinition[];
};

const INTEGRATION_NAV_GROUPS: Array<{
  id: string;
  label: string;
  items?: IntegrationNavigationDefinition[];
  basic?: IntegrationNavigationDefinition[];
  advanced?: IntegrationNavigationDefinition[];
  sections?: IntegrationNavSectionDefinition[];
}> = [
  { id: "workspace", label: "Runtime defaults", items: [{ integrationId: "runtime", view: "all", label: "Runtime defaults" }] },
  {
    id: "llm",
    label: "Model providers",
    sections: [
      {
        id: "foundational",
        label: "Foundational models",
        blocks: [
          {
            type: "items",
            items: [
              { integrationId: "openai", view: "llm", label: "OpenAI", logo: "openai" },
              { integrationId: "anthropic", view: "llm", label: "Anthropic", logo: "anthropic" },
            ],
          },
          {
            type: "brand",
            brand: {
              id: "google",
              label: "Google",
              logo: "google",
              items: [
                { integrationId: "gemini", view: "llm", label: "Gemini", logo: "gemini" },
                { integrationId: "vertex", view: "llm", label: "Vertex AI", logo: "vertex" },
              ],
            },
          },
          {
            type: "items",
            items: [{ integrationId: "xai", view: "llm", label: "Grok", logo: "xai" }],
          },
        ],
      },
      {
        id: "inference",
        label: "Inference providers",
        blocks: [
          {
            type: "items",
            items: [
              { integrationId: "baseten", view: "llm", label: "Baseten", logo: "baseten" },
              { integrationId: "together", view: "llm", label: "Together AI", logo: "together" },
              { integrationId: "gmi", view: "llm", label: "GMI Cloud", logo: "gmi" },
              { integrationId: "huggingface", view: "llm", label: "Hugging Face", logo: "huggingface" },
              { integrationId: "cloudflare", view: "llm", label: "Cloudflare Workers AI", logo: "workersai" },
              { integrationId: "nvidia", view: "llm", label: "NVIDIA", logo: "nvidia" },
              { integrationId: "runpod", view: "llm", label: "Runpod", logo: "runpod" },
            ],
          },
        ],
      },
      {
        id: "custom",
        label: "Custom / open-source",
        blocks: [
          {
            type: "items",
            items: [{ integrationId: "ollama", view: "llm", label: "Ollama", logo: "ollama" }],
          },
        ],
      },
    ],
  },
  {
    id: "image",
    label: "Image / Video",
    basic: [
      { integrationId: "openai", view: "image", label: "OpenAI Images", logo: "openai", imageProviderId: "openai" },
    ],
    advanced: [
      { integrationId: "vertex", view: "image", label: "Vertex Nano Banana", logo: "vertex", imageProviderId: "vertex" },
      { integrationId: "gmi", view: "image", label: "GMI Cloud", logo: "gmi", imageProviderId: "gmi" },
      { integrationId: "huggingface", view: "image", label: "Hugging Face", logo: "huggingface", imageProviderId: "huggingface" },
      { integrationId: "together", view: "image", label: "Together AI", logo: "together", imageProviderId: "together" },
      { integrationId: "image", view: "image", label: "Custom / OpenAI-compatible", logo: "custom" },
    ],
  },
  { id: "tools", label: "Tool providers", basic: [{ integrationId: "firecrawl", view: "all", logo: "firecrawl" }] },
];

type IntegrationNavigationItem = IntegrationNavigationDefinition & {
  key: string;
  label: string;
  integration: IntegrationStatus;
};

type IntegrationNavBlock =
  | { type: "items"; items: IntegrationNavigationItem[] }
  | { type: "brand"; brand: { id: string; label: string; logo: string; items: IntegrationNavigationItem[] } };

type IntegrationNavSection = {
  id: string;
  label: string;
  blocks: IntegrationNavBlock[];
};

type IntegrationNavigationGroup = {
  id: string;
  label: string;
  items: IntegrationNavigationItem[];
  basic: IntegrationNavigationItem[];
  advanced: IntegrationNavigationItem[];
  sections: IntegrationNavSection[];
};

function navItemsFromDefs(defs: IntegrationNavigationDefinition[] | undefined, integrations: IntegrationStatus[]) {
  return (defs || []).flatMap((item) => {
    const integration = integrations.find((candidate) => candidate.id === item.integrationId);
    if (!integration) return [];
    return [{ ...item, key: `${item.integrationId}:${item.view}`, label: item.label || integration.label, integration }];
  });
}

function defsFromNavBlocks(blocks: IntegrationNavBlockDefinition[] | undefined) {
  return (blocks || []).flatMap((block) => (block.type === "brand" ? block.brand.items : block.items));
}

function resolveNavBlocks(blocks: IntegrationNavBlockDefinition[] | undefined, integrations: IntegrationStatus[]): IntegrationNavBlock[] {
  const resolved: IntegrationNavBlock[] = [];
  for (const block of blocks || []) {
    if (block.type === "brand") {
      const items = navItemsFromDefs(block.brand.items, integrations);
      if (items.length) resolved.push({ type: "brand", brand: { ...block.brand, items } });
      continue;
    }
    const items = navItemsFromDefs(block.items, integrations);
    if (items.length) resolved.push({ type: "items", items });
  }
  return resolved;
}

function navigationGroupItems(group: IntegrationNavigationGroup) {
  return [
    ...group.items,
    ...group.basic,
    ...group.advanced,
    ...group.sections.flatMap((section) =>
      section.blocks.flatMap((block) => (block.type === "brand" ? block.brand.items : block.items))
    ),
  ];
}

function aggregateNavBadge(badges: SettingsNavBadgeModel[]): SettingsNavBadgeModel {
  if (badges.some((badge) => badge.label === "Ready")) return { tone: "ready", label: "Ready" };
  if (badges.some((badge) => badge.label === "Off")) return { tone: "warn", label: "Off" };
  return { tone: "muted", label: "Unset" };
}

function integrationNavigationGroups(integrations: IntegrationStatus[]) {
  const includedIds = new Set<string>(
    INTEGRATION_NAV_GROUPS.flatMap((group) => [
      ...(group.items || []),
      ...(group.basic || []),
      ...(group.advanced || []),
      ...(group.sections || []).flatMap((section) => defsFromNavBlocks(section.blocks)),
    ]).map((item) => item.integrationId)
  );
  const groups: IntegrationNavigationGroup[] = INTEGRATION_NAV_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    items: navItemsFromDefs(group.items, integrations),
    basic: navItemsFromDefs(group.basic, integrations),
    advanced: navItemsFromDefs(group.advanced, integrations),
    sections: (group.sections || [])
      .map((section) => ({
        id: section.id,
        label: section.label,
        blocks: resolveNavBlocks(section.blocks, integrations),
      }))
      .filter((section) => section.blocks.length > 0),
  })).filter((group) => navigationGroupItems(group).length > 0);

  const other = integrations.filter((integration) => !includedIds.has(integration.id));
  if (other.length) {
    groups.push({
      id: "other",
      label: "Other",
      items: [],
      basic: [],
      advanced: other.map((integration) => ({
        integrationId: integration.id,
        view: "all" as const,
        key: `${integration.id}:all`,
        label: integration.label,
        integration,
      })),
      sections: [],
    });
  }
  return groups;
}

function navigationDescription(item: IntegrationNavigationItem | null) {
  if (!item) return "";
  if (item.view === "llm") return `Language model credentials, models, and connection settings for ${item.integration.label}.`;
  if (item.view === "image") return `Image generation credentials, models, and rendering settings for ${item.integration.label}.`;
  return item.integration.description;
}

function imageNavigationKey(provider: string) {
  const option = IMAGE_PROVIDER_OPTIONS.find((candidate) => candidate.id === provider);
  return `${option?.integrationId || "image"}:image`;
}

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

function isChooserField(field: IntegrationFieldStatus) {
  return ["model", "fallback_model", "llm_selector", "llm_model", "image_model"].includes(field.id);
}

function SettingsChip({
  label,
  active = false,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const className = `${STATUS_PILL_CLASS} ${
    active ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-slate-500"
  }`;
  if (!onClick) return <span className={className}>{label}</span>;
  return (
    <button type="button" onClick={onClick} className={`${className} transition hover:text-slate-200`}>
      {label}
    </button>
  );
}

function SettingsEnabledControl({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={`inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border border-[#2c2f37] px-2.5 text-xs font-medium ${
        checked ? "bg-emerald-500/10 text-emerald-400" : "text-slate-400"
      } ${disabled ? "cursor-wait opacity-60" : ""}`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 accent-emerald-400"
      />
      Enabled
    </label>
  );
}

function SettingsPaneHeader({
  title,
  description,
  meta,
  badges,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  badges?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 border-b border-[#2c2f37] px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
      <div className="min-w-0">
        <p className="text-xs text-slate-500">Settings</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
          {badges}
        </div>
        {description ? <div className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</div> : null}
        {meta}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

function SettingsNavSubhead({ children }: { children: React.ReactNode }) {
  return <div className="px-2 pb-1 pt-2 text-[11px] font-medium text-slate-500">{children}</div>;
}

function SettingsAdvancedDisclosure({
  open,
  onToggle,
  description,
  configuredCount = 0,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  description: string;
  configuredCount?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-[#2c2f37] bg-[#101115]/70">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <ChevronDown className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${open ? "" : "-rotate-90"}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-white">Advanced</span>
            <span className={`${STATUS_PILL_CLASS} ${configuredCount ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-slate-500"}`}>
              {configuredCount ? `${configuredCount} configured` : "Optional"}
            </span>
          </div>
          <p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p>
        </div>
      </button>
      {open ? <div className="space-y-8 border-t border-[#2c2f37] px-4 py-4">{children}</div> : null}
    </section>
  );
}

function SettingsFieldCard({
  title,
  chips,
  help,
  extraHelp,
  notice,
  children,
}: {
  title: string;
  chips?: React.ReactNode;
  help?: string;
  extraHelp?: string;
  notice?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-medium text-slate-300">{title}</h4>
        {chips ? <div className="flex flex-wrap items-center gap-1.5">{chips}</div> : null}
      </div>
      {children}
      {help ? <p className="mt-1.5 text-xs leading-5 text-slate-500">{help}</p> : null}
      {extraHelp ? <p className="mt-1 text-xs leading-5 text-slate-500">{extraHelp}</p> : null}
      {notice ? <p className="mt-1.5 text-xs leading-5 text-amber-200">{notice}</p> : null}
    </div>
  );
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Never saved";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function isConfirmationField(field: IntegrationFieldStatus) {
  return field.id.endsWith("_confirmation");
}

function isTruthyFieldValue(value: string | null | undefined) {
  return [
    "1",
    "true",
    "yes",
    "y",
    "confirmed",
    "fine-grained",
    "service-account",
    "project-scoped",
    "organization-scoped",
    "dedicated-project",
    "dedicated-to-forma",
  ].includes((value || "").trim().toLowerCase());
}

function confirmationLabel(integration: IntegrationStatus, field: IntegrationFieldStatus) {
  if (integration.id === "huggingface" && field.id === "token_scope_confirmation") {
    return "I confirm this is a fine-grained Hugging Face token with only Make calls to Inference Providers, or an enterprise service-account token with equivalent scope.";
  }
  if (integration.id === "gmi" && field.id === "key_delegation_confirmation") {
    return "I confirm this GMI key is scoped to a dedicated project or organization and may be stored server-side by Forma for requests from my account.";
  }
  if (integration.id === "together" && field.id === "project_key_confirmation") {
    return "I confirm this Together AI key is project-scoped, dedicated to Forma, and not a legacy or broad account key.";
  }
  return "I confirm this credential is scoped for this integration and does not include broad account, repository, organization, billing, deployment, or unrestricted access.";
}

function integrationField(integration: IntegrationStatus | undefined, fieldId: string) {
  return integration?.fields.find((field) => field.id === fieldId);
}

function formFieldValue(forms: Record<string, IntegrationFormState>, integration: IntegrationStatus | undefined, fieldId: string) {
  const formValue = integration ? forms[integration.id]?.fields[fieldId] : "";
  if (formValue) return formValue;
  return integrationField(integration, fieldId)?.value || "";
}

function newestConfiguredImageProvider(candidates: Array<{ provider: string; integration: IntegrationStatus | undefined; configured: boolean }>) {
  return candidates
    .filter((candidate) => candidate.integration?.enabled && candidate.configured)
    .sort((a, b) => String(b.integration?.updated_at || "").localeCompare(String(a.integration?.updated_at || "")))[0]?.provider || "";
}

function uniqueModelOptions(options: ProviderModelOption[]) {
  const values = new Set<string>();
  return options.filter((option) => {
    if (values.has(option.value)) return false;
    values.add(option.value);
    return true;
  });
}

async function responseErrorMessage(response: Response, fallback: string) {
  const text = await response.text();
  if (!text.trim()) return fallback;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item) => String(item?.msg || item)).join("; ");
    if (parsed.detail && typeof parsed.detail === "object") {
      const detail = parsed.detail as { code?: unknown; message?: unknown };
      const message = typeof detail.message === "string" ? detail.message : fallback;
      const code = typeof detail.code === "string" ? detail.code : "";
      return code ? `${message} (${code})` : message;
    }
  } catch {
    // Fall through to plain text.
  }
  return text;
}

function fieldPlaceholder(field: IntegrationFieldStatus) {
  if (field.policy_blocked) return "Not accepted in Forma Cloud";
  if (field.secret && field.masked_value) return `Saved: ${field.masked_value}`;
  return field.placeholder || "";
}

function providerFields(integration: IntegrationStatus | undefined, fieldIds: string[]) {
  return fieldIds.map((fieldId) => integrationField(integration, fieldId)).filter(Boolean) as IntegrationFieldStatus[];
}

function fieldHasValue(forms: Record<string, IntegrationFormState>, integration: IntegrationStatus | undefined, field: IntegrationFieldStatus) {
  if (!integration) return false;
  return Boolean((forms[integration.id]?.fields[field.id] || "").trim() || field.configured || field.saved);
}

type IntegrationFieldGroup = {
  id: string;
  label: string;
  description: string;
  level: "basic" | "advanced";
  fields: IntegrationFieldStatus[];
};

const BASIC_LANGUAGE_MODEL_FIELD_IDS = new Set(["model", "fallback_model", "max_tokens"]);
const ADVANCED_LANGUAGE_MODEL_FIELD_IDS = new Set([
  "model_revision",
  "model_license",
  "inference_provider",
  "gated_models_enabled",
]);

function integrationFieldGroups(integration: IntegrationStatus, view: IntegrationView = "all"): IntegrationFieldGroup[] {
  if (integration.id === "runtime") {
    const runtimeGroups = [
      {
        id: "language",
        label: "Language model defaults",
        description: "Choose the default LLM used for new work.",
        level: "basic" as const,
        fieldIds: ["llm_selector"],
      },
      {
        id: "image",
        label: "Image defaults",
        description: "Fallback image provider and model values for generated visuals.",
        level: "basic" as const,
        fieldIds: ["image_provider", "image_model"],
      },
      {
        id: "research",
        label: "Research tools",
        description: "Select the external source used for web research.",
        level: "basic" as const,
        fieldIds: ["external_source_provider"],
      },
      {
        id: "language-advanced",
        label: "Provider overrides",
        description: "Pin a provider, model, or allow-list instead of relying on the default selector.",
        level: "advanced" as const,
        fieldIds: ["llm_provider", "llm_model", "allowed_providers"],
      },
    ];
    return runtimeGroups
      .map((group) => ({
        ...group,
        fields: group.fieldIds
          .map((fieldId) => integration.fields.find((field) => field.id === fieldId))
          .filter(Boolean) as IntegrationFieldStatus[],
      }))
      .filter((group) => group.fields.length > 0);
  }

  const groups: IntegrationFieldGroup[] = [
    { id: "credentials", label: "Credentials", description: "Authentication and required credential-scope confirmations.", level: "basic", fields: [] },
    { id: "language", label: "Language models", description: "Primary text model and generation defaults.", level: "basic", fields: [] },
    { id: "image", label: "Image generation", description: "Default image model for this provider.", level: "basic", fields: [] },
    { id: "language-advanced", label: "Language model extras", description: "Revision, license, inference routing, and gated-model options.", level: "advanced", fields: [] },
    { id: "image-advanced", label: "Image rendering", description: "Size, quality, format, and other rendering overrides.", level: "advanced", fields: [] },
    { id: "video", label: "Video generation", description: "Video endpoints and model defaults.", level: "advanced", fields: [] },
    { id: "connection", label: "Connection", description: "Endpoint, timeout, storage, and provider-specific settings.", level: "advanced", fields: [] },
  ];
  const byId = new Map(groups.map((group) => [group.id, group]));

  integration.fields.forEach((field) => {
    if (field.secret || isConfirmationField(field)) {
      byId.get("credentials")?.fields.push(field);
    } else if (field.id.startsWith("video_") || field.id === "image_to_video_model") {
      byId.get("video")?.fields.push(field);
    } else if (integration.id === "image" || field.id.startsWith("image_")) {
      if (field.id === "image_model" || field.id === "model") byId.get("image")?.fields.push(field);
      else byId.get("image-advanced")?.fields.push(field);
    } else if (BASIC_LANGUAGE_MODEL_FIELD_IDS.has(field.id)) {
      byId.get("language")?.fields.push(field);
    } else if (ADVANCED_LANGUAGE_MODEL_FIELD_IDS.has(field.id)) {
      byId.get("language-advanced")?.fields.push(field);
    } else {
      byId.get("connection")?.fields.push(field);
    }
  });
  const populatedGroups = groups.filter((group) => group.fields.length > 0);
  if (view === "llm") return populatedGroups.filter((group) => ["credentials", "language", "language-advanced", "connection"].includes(group.id));
  if (view === "image") return populatedGroups.filter((group) => ["credentials", "image", "image-advanced"].includes(group.id));
  return populatedGroups;
}

function ModelCombobox({
  id,
  value,
  options,
  placeholder,
  disabled,
  suggestionType = "model",
  onChange,
}: {
  id: string;
  value: string;
  options: ProviderModelOption[];
  placeholder: string;
  disabled?: boolean;
  suggestionType?: "model" | "setting";
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const normalizedValue = value.trim().toLowerCase();
  const hasExactMatch = options.some((option) => option.value.toLowerCase() === normalizedValue);
  const filteredOptions = (normalizedValue && !hasExactMatch
    ? options.filter((option) => `${option.label} ${option.value} ${option.detail || ""}`.toLowerCase().includes(normalizedValue))
    : options
  ).slice(0, 100);
  const listId = `${id}-options`;

  return (
    <div
      className="relative min-w-0 flex-1"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <div className="flex h-9 rounded-lg border border-[#2c2f37] bg-[#101115] focus-within:border-emerald-500">
        <Search className="ml-3 h-4 w-4 shrink-0 self-center text-slate-600" />
        <input
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={open}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 disabled:cursor-not-allowed disabled:text-slate-600"
        />
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          disabled={disabled}
          aria-label={`Show ${suggestionType} suggestions`}
          className="inline-flex w-9 shrink-0 items-center justify-center text-slate-500 hover:text-white disabled:cursor-not-allowed"
        >
          <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      {open && !disabled && (
        <div id={listId} role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-[#2c2f37] bg-[#181b22] shadow-2xl">
          {filteredOptions.length ? (
            filteredOptions.map((option, index) => (
              <React.Fragment key={option.value}>
                {option.group && option.group !== filteredOptions[index - 1]?.group && (
                  <div className="sticky top-0 border-b border-[#2c2f37] bg-[#181b22] px-3 py-2 text-xs font-medium text-slate-400">
                    {option.group}
                  </div>
                )}
                <button
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`block w-full px-3 py-2.5 text-left hover:bg-white/5 ${
                    option.value === value ? "bg-emerald-500/10" : ""
                  }`}
                >
                  <span className="block text-sm font-medium text-white">{option.label}</span>
                  <span className="mt-0.5 block break-all font-mono text-[11px] text-slate-500">{option.value}</span>
                  {option.detail && <span className="mt-0.5 block text-[11px] text-slate-400">{option.detail}</span>}
                </button>
              </React.Fragment>
            ))
          ) : (
            <div className="px-3 py-3 text-xs leading-5 text-slate-400">No matching suggestion. Keep your custom model ID and save it.</div>
          )}
          <div className="sticky bottom-0 border-t border-[#2c2f37] bg-[#181b22] px-3 py-2 text-[11px] text-slate-500">
            {suggestionType === "model"
              ? `${options.length} suggestions · any model ID is allowed`
              : "Suggestions only · custom values are allowed"}
          </div>
        </div>
      )}
    </div>
  );
}

type ImageProviderSetupProps = {
  forms: Record<string, IntegrationFormState>;
  provider: string;
  providerOption: ImageProviderOption;
  providerIntegration: IntegrationStatus | undefined;
  imageIntegration: IntegrationStatus | undefined;
  model: string;
  modelOptions: ProviderModelOption[];
  saving: boolean;
  showAdvanced: boolean;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  onFieldChange: (integrationId: string, fieldId: string, value: string) => void;
  onEnabledChange: (integrationId: string, enabled: boolean) => void;
  onSave: () => void;
  onClear: (integration: IntegrationStatus) => void;
  onReload?: () => void;
  reloading?: boolean;
  onToggleAdvanced: () => void;
};

function ImageProviderSetup({
  forms,
  provider,
  providerOption,
  providerIntegration,
  imageIntegration,
  model,
  modelOptions,
  saving,
  showAdvanced,
  onProviderChange,
  onModelChange,
  onFieldChange,
  onEnabledChange,
  onSave,
  onClear,
  onReload,
  reloading,
  onToggleAdvanced,
}: ImageProviderSetupProps) {
  const enabled = provider !== "none" && (forms.image?.enabled ?? imageIntegration?.enabled ?? true);
  const credentialFields = providerFields(providerIntegration, providerOption.credentialFieldIds);
  const configFields = providerFields(providerIntegration, providerOption.configFieldIds).filter((field) => field.id !== providerOption.modelFieldId);
  const advancedFieldIds = provider === "gmi"
    ? ["image_base_url", ...gmiImageSettingFieldIds(model), "image_timeout_seconds"]
    : providerOption.advancedFieldIds;
  const advancedFields = providerFields(providerIntegration, advancedFieldIds);
  const missingRequiredFields = credentialFields.filter((field) => !fieldHasValue(forms, providerIntegration, field));
  const readyCount = credentialFields.filter((field) => fieldHasValue(forms, providerIntegration, field)).length;
  const requiredCount = credentialFields.length;
  const modelField = providerOption.modelFieldId ? integrationField(providerIntegration, providerOption.modelFieldId) : undefined;
  const canSave = !saving && provider !== "none" ? missingRequiredFields.length === 0 : !saving;

  return (
    <article className={CARD_SURFACE_CLASS}>
      <SettingsPaneHeader
        title="Image generation"
        description={providerOption.summary}
        badges={
          <>
            {providerOption.tier === "advanced" && <SettingsNavBadge tone="muted">Advanced</SettingsNavBadge>}
            <SettingsNavBadge tone={providerIntegration?.configured ? "ready" : "muted"}>
              {providerIntegration?.configured ? "Configured" : "Unset"}
            </SettingsNavBadge>
          </>
        }
        meta={
          <>
            {providerIntegration?.policy_notice && <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-200">{providerIntegration.policy_notice}</p>}
            {providerIntegration?.updated_at && (
              <p className="mt-2 text-xs text-slate-500">Updated {formatTimestamp(providerIntegration.updated_at)}</p>
            )}
          </>
        }
        actions={
          <>
            <SettingsEnabledControl
              checked={Boolean(enabled)}
              disabled={saving}
              onChange={(checked) => {
                onProviderChange(checked ? provider : "none");
                if (imageIntegration) onEnabledChange(imageIntegration.id, checked);
                if (providerIntegration) onEnabledChange(providerIntegration.id, checked);
              }}
            />
            <button type="button" onClick={onSave} disabled={!canSave} className={BUTTON_PRIMARY_CLASS}>
              <Save className="h-3.5 w-3.5" />
              Save
            </button>
            {providerIntegration?.configured && (
              <button type="button" onClick={() => onClear(providerIntegration)} disabled={saving} className={BUTTON_DANGER_CLASS}>
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </button>
            )}
            {onReload && (
              <button type="button" onClick={onReload} disabled={reloading} className={BUTTON_OUTLINE_CLASS}>
                <RefreshCw className={`h-3.5 w-3.5 ${reloading ? "animate-spin" : ""}`} />
                Reload integrations
              </button>
            )}
          </>
        }
      />

      <div className="space-y-8 p-5">
        <section>
          <h3 className="text-sm font-medium text-white">Provider</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">Pick the service used for generated product images.</p>
          <div className="mt-4">
            <SettingsFieldCard
              title="Image provider"
              extraHelp={requiredCount ? `${readyCount}/${requiredCount} required credential fields set.` : undefined}
            >
              <select
                value={provider}
                onChange={(event) => onProviderChange(event.target.value)}
                className={FIELD_CONTROL_CLASS}
              >
                <optgroup label="Basic">
                  {IMAGE_PROVIDER_OPTIONS.filter((option) => option.tier === "basic").map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Advanced">
                  {IMAGE_PROVIDER_OPTIONS.filter((option) => option.tier === "advanced").map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              </select>
            </SettingsFieldCard>
          </div>
          {missingRequiredFields.length > 0 && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
              Missing required setup: {missingRequiredFields.map((field) => field.label).join(", ")}.
            </div>
          )}
        </section>

        {provider === "none" ? (
          <p className="text-sm leading-6 text-slate-400">Image generation is off. Generated projects will skip product visuals.</p>
        ) : (
          <>
            <section>
              <h3 className="text-sm font-medium text-white">Required setup</h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">API credentials and required confirmations for this provider.</p>
              <div className="mt-4 grid gap-4">
                {credentialFields.length ? (
                  credentialFields.map((field) => (
                    <ImageSetupField
                      key={field.id}
                      integration={providerIntegration}
                      field={field}
                      forms={forms}
                      onFieldChange={onFieldChange}
                    />
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No credentials are required for this provider.</p>
                )}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-medium text-white">Model defaults</h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Use the preconfigured default now. Open advanced for rendering, timeout, and endpoint overrides.
              </p>
              <div className="mt-4 grid gap-4">
                {!providerOption.preconfigured && modelField && (
                  <SettingsFieldCard
                    title="Image model"
                    extraHelp="Search the suggestions or enter any model ID supported by this provider."
                    chips={!model.trim() ? undefined : <SettingsChip label="Unset" onClick={() => onModelChange("")} />}
                  >
                    <ModelCombobox
                      id={`image-model-${providerOption.id}`}
                      value={model}
                      onChange={onModelChange}
                      options={modelOptions}
                      placeholder={providerOption.models[0]?.value || modelField.placeholder || "provider/model-name"}
                    />
                  </SettingsFieldCard>
                )}

                {providerOption.preconfigured && (
                  <div className="rounded-lg bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-100">
                    Ready with provider defaults after credentials are saved.
                    {model ? <span className="font-mono"> Current override: {model}</span> : null}
                  </div>
                )}

                {configFields.map((field) => (
                  <ImageSetupField
                    key={field.id}
                    integration={providerIntegration}
                    field={field}
                    forms={forms}
                    onFieldChange={onFieldChange}
                  />
                ))}
              </div>
            </section>

            {advancedFields.length > 0 && (
              <SettingsAdvancedDisclosure
                open={showAdvanced}
                onToggle={onToggleAdvanced}
                description="Optional rendering, timeout, and provider-specific overrides."
                configuredCount={advancedFields.filter((field) => fieldHasValue(forms, providerIntegration, field)).length}
              >
                <div className="grid gap-4">
                  {advancedFields.map((field) => (
                    <ImageSetupField
                      key={field.id}
                      integration={providerIntegration}
                      field={field}
                      forms={forms}
                      onFieldChange={onFieldChange}
                    />
                  ))}
                </div>
              </SettingsAdvancedDisclosure>
            )}
          </>
        )}
      </div>
    </article>
  );
}

function FieldStatusChips({ field }: { field: IntegrationFieldStatus }) {
  return (
    <>
      {field.secret && <span className={`${STATUS_PILL_CLASS} bg-cyan-300/10 text-cyan-200`}>Secret</span>}
      {field.policy_blocked && <span className={`${STATUS_PILL_CLASS} bg-rose-500/10 text-rose-200`}>Not accepted in Cloud</span>}
      {!field.policy_blocked && field.policy_conditional && (
        <span className={`${STATUS_PILL_CLASS} bg-amber-500/10 text-amber-200`}>Conditional</span>
      )}
    </>
  );
}

function ImageSetupField({
  integration,
  field,
  forms,
  onFieldChange,
}: {
  integration: IntegrationStatus | undefined;
  field: IntegrationFieldStatus;
  forms: Record<string, IntegrationFormState>;
  onFieldChange: (integrationId: string, fieldId: string, value: string) => void;
}) {
  if (!integration) return null;
  const fieldValue = forms[integration.id]?.fields[field.id] || "";
  const confirmationField = isConfirmationField(field);
  const isModelField = isChooserField(field);
  const modelOptions = uniqueModelOptions(modelOptionsForField(integration.id, field.id));
  const selectedImageModel = forms[integration.id]?.fields.image_model || integrationField(integration, "image_model")?.value || "";
  const settingOptions = uniqueModelOptions(settingOptionsForField(integration.id, field.id, selectedImageModel));
  const hasSettingOptions = settingOptions.length > 0;
  const chooser = isModelField || hasSettingOptions;
  const inputId = `image-setup-${integration.id}-${field.id}`;
  const hasValue = Boolean(fieldValue.trim());

  return (
    <SettingsFieldCard
      title={field.label}
      help={field.help}
      extraHelp={isModelField || hasSettingOptions ? "Search the suggestions or enter any model ID supported by this provider." : undefined}
      notice={field.policy_notice}
      chips={
        <>
          {chooser && hasValue ? <SettingsChip label="Unset" onClick={() => onFieldChange(integration.id, field.id, "")} /> : null}
          <FieldStatusChips field={field} />
        </>
      }
    >
      {confirmationField ? (
        <label
          htmlFor={inputId}
          className="flex min-h-9 cursor-pointer items-start gap-3 rounded-lg border border-amber-400/35 bg-amber-500/10 px-3 py-2.5 text-sm leading-5 text-amber-100"
        >
          <input
            id={inputId}
            type="checkbox"
            checked={isTruthyFieldValue(fieldValue)}
            onChange={(event) => onFieldChange(integration.id, field.id, event.target.checked ? "confirmed" : "")}
            disabled={!field.editable}
            className="mt-0.5 h-4 w-4 shrink-0 accent-emerald-400"
          />
          <span>{confirmationLabel(integration, field)}</span>
        </label>
      ) : isModelField || hasSettingOptions ? (
        <ModelCombobox
          id={inputId}
          value={fieldValue}
          options={isModelField ? modelOptions : settingOptions}
          onChange={(value) => onFieldChange(integration.id, field.id, value)}
          placeholder={fieldPlaceholder(field)}
          disabled={!field.editable}
          suggestionType={isModelField ? "model" : "setting"}
        />
      ) : (
        <input
          id={inputId}
          type={field.secret ? "password" : "text"}
          value={fieldValue}
          onChange={(event) => onFieldChange(integration.id, field.id, event.target.value)}
          placeholder={fieldPlaceholder(field)}
          disabled={!field.editable}
          autoComplete="off"
          className={FIELD_CONTROL_CLASS}
        />
      )}
    </SettingsFieldCard>
  );
}

function IntegrationFieldEditor({
  integration,
  field,
  value,
  saving,
  onChange,
  onClearSaved,
}: {
  integration: IntegrationStatus;
  field: IntegrationFieldStatus;
  value: string;
  saving: boolean;
  onChange: (value: string) => void;
  onClearSaved: () => void;
}) {
  const confirmationField = isConfirmationField(field);
  const placeholder = field.policy_blocked
    ? "Not accepted in Forma Cloud"
    : field.secret && field.masked_value
    ? `Saved: ${field.masked_value}`
    : field.placeholder || field.env_names[0] || "";
  const chooser = isChooserField(field);
  const modelOptions = uniqueModelOptions(modelOptionsForField(integration.id, field.id));
  const inputId = `${integration.id}-${field.id}`;
  const hasValue = Boolean(value.trim());

  function unsetField() {
    if (saving) return;
    onChange("");
    if (field.saved) onClearSaved();
  }

  return (
    <SettingsFieldCard
      title={field.label}
      help={field.help}
      extraHelp={chooser ? "Search the suggestions or enter any model ID supported by this provider." : undefined}
      notice={field.policy_notice}
      chips={
        <>
          {chooser && hasValue ? <SettingsChip label="Unset" onClick={unsetField} /> : null}
          <FieldStatusChips field={field} />
        </>
      }
    >
      {confirmationField ? (
        <label
          htmlFor={inputId}
          className="flex min-h-9 cursor-pointer items-start gap-3 rounded-lg border border-amber-400/35 bg-amber-500/10 px-3 py-2.5 text-sm leading-5 text-amber-100"
        >
          <input
            id={inputId}
            type="checkbox"
            checked={isTruthyFieldValue(value)}
            onChange={(event) => onChange(event.target.checked ? "confirmed" : "")}
            disabled={!field.editable}
            className="mt-0.5 h-4 w-4 shrink-0 accent-emerald-400"
          />
          <span>{confirmationLabel(integration, field)}</span>
        </label>
      ) : chooser ? (
        <ModelCombobox
          id={inputId}
          value={value}
          options={modelOptions}
          onChange={onChange}
          placeholder={placeholder}
          disabled={!field.editable}
        />
      ) : (
        <input
          id={inputId}
          type={field.secret ? "password" : "text"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          disabled={!field.editable}
          autoComplete="off"
          className={FIELD_CONTROL_CLASS}
        />
      )}
    </SettingsFieldCard>
  );
}

function IntegrationFieldGroupList({
  groups,
  integration,
  forms,
  saving,
  onChange,
  onClearSaved,
}: {
  groups: IntegrationFieldGroup[];
  integration: IntegrationStatus;
  forms: Record<string, IntegrationFormState>;
  saving: boolean;
  onChange: (fieldId: string, value: string) => void;
  onClearSaved: (fieldId: string) => void;
}) {
  return (
    <>
      {groups.map((group) => (
        <section key={group.id}>
          <h3 className="text-sm font-medium text-white">{group.label}</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">{group.description}</p>
          <div className="mt-4 grid gap-4">
            {group.fields.map((field) => (
              <IntegrationFieldEditor
                key={field.id}
                integration={integration}
                field={field}
                value={forms[integration.id]?.fields[field.id] || ""}
                saving={saving}
                onChange={(value) => onChange(field.id, value)}
                onClearSaved={() => onClearSaved(field.id)}
              />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

function ImageModelTestPanel({
  provider,
  model,
  prompt,
  running,
  result,
  error,
  errorDetails,
  onPromptChange,
  onRun,
}: {
  provider: string;
  model: string;
  prompt: string;
  running: boolean;
  result: ImageModelTestResult | null;
  error: string | null;
  errorDetails: unknown;
  onPromptChange: (value: string) => void;
  onRun: () => void;
}) {
  const diagnostics = result
    ? {
        ...result,
        image_data_url: result.image_data_url.startsWith("data:")
          ? `<data URL omitted · ${result.image_data_url.length.toLocaleString()} characters>`
          : result.image_data_url,
      }
    : errorDetails;

  return (
    <article className={`mt-4 ${CARD_SURFACE_CLASS}`}>
      <SettingsPaneHeader
        title="Test image model"
        description="Makes one direct provider request. It does not run the main agent, create a project, or execute the image sequence."
        badges={<SettingsNavBadge tone="allowed">Local / preview only</SettingsNavBadge>}
        meta={<p className="mt-2 text-xs text-slate-500">{provider || "none"} / {model || "no model"}</p>}
        actions={
          <button
            type="button"
            onClick={onRun}
            disabled={running || !prompt.trim() || provider === "none" || !model}
            className={BUTTON_PRIMARY_CLASS}
          >
            <FlaskConical className={`h-3.5 w-3.5 ${running ? "animate-pulse" : ""}`} />
            {running ? "Testing model" : "Generate one test image"}
          </button>
        }
      />

      <div className="space-y-6 p-5">
        <section>
          <h3 className="text-sm font-medium text-white">Test prompt</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">Uses saved settings and may incur one provider image-generation charge.</p>
          <div className="mt-4">
            <SettingsFieldCard title="Prompt" extraHelp="Save provider/model changes above before testing.">
              <textarea
                id="image-model-test-prompt"
                value={prompt}
                onChange={(event) => onPromptChange(event.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="A clean studio product render of a compact electronics enclosure..."
                className="w-full resize-y rounded-lg border border-[#2c2f37] bg-[#101115] px-3 py-2.5 text-sm leading-6 text-slate-200 outline-none placeholder:text-slate-600 focus:border-emerald-500"
              />
            </SettingsFieldCard>
          </div>
        </section>

        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 p-4 text-sm leading-6 text-rose-200">
            <div className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4" />
              Test failed
            </div>
            <p className="mt-2 break-words">{error}</p>
          </div>
        )}

        {result && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="flex min-h-72 items-center justify-center rounded-lg border border-[#2c2f37] bg-[#101115] p-3">
              {/* Provider results can be data URLs or short-lived remote URLs, so Next image optimization is not appropriate here. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={result.image_data_url} alt="Direct image model test result" className="max-h-[640px] w-full object-contain" />
            </div>
            <div className="grid content-start gap-3">
              <div className="rounded-lg bg-emerald-500/10 p-3 text-emerald-100">
                <div className="text-xs font-medium">Request succeeded</div>
                <div className="mt-2 font-mono text-sm">{result.elapsed_ms.toLocaleString()} ms</div>
              </div>
              <div className="rounded-lg border border-[#2c2f37] p-3 font-mono text-xs leading-5 text-slate-400">
                <div><span className="text-slate-600">Provider:</span> {result.provider}</div>
                <div><span className="text-slate-600">Model:</span> {result.model}</div>
                <div><span className="text-slate-600">Size:</span> {result.size || "Provider default"}</div>
                <div><span className="text-slate-600">Format:</span> {result.output_format}</div>
              </div>
            </div>
          </div>
        )}

        {diagnostics != null && (
          <details className="rounded-lg border border-[#2c2f37] bg-[#101115]">
            <summary className="cursor-pointer px-3 py-2.5 text-xs font-medium text-slate-400">
              Raw diagnostics
            </summary>
            <pre className="max-h-96 overflow-auto border-t border-[#2c2f37] p-3 text-[11px] leading-5 text-slate-400">
              {JSON.stringify(diagnostics, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </article>
  );
}

function ThemeSettingsPanel() {
  const { theme, setTheme } = useTheme();
  const options = [
    {
      id: "light" as const,
      label: "Light",
      description: "Solarized Light: warm low-glare surfaces for daytime and high-ambient-light use.",
      icon: Sun,
      previewStyle: {
        backgroundColor: solarizedLight.base3,
        borderColor: solarizedLight.base1,
        color: solarizedLight.base01,
      },
    },
    {
      id: "arctic" as const,
      label: "Arctic",
      description: "Cool white panels on a slate page, for higher contrast than Solarized Light.",
      icon: Snowflake,
      previewStyle: {
        backgroundColor: arcticLight.surface,
        borderColor: arcticLight.border,
        color: arcticLight.textBody,
      },
    },
    {
      id: "dark" as const,
      label: "Dark",
      description: "Low-luminance surfaces with light text for focused or low-light use.",
      icon: Moon,
      previewStyle: { backgroundColor: "#0f1117", borderColor: "#2c2f37", color: "#f1f5f9" },
    },
  ];

  return (
    <article className={CARD_SURFACE_CLASS}>
      <SettingsPaneHeader
        title="Appearance"
        description="Choose how Forma looks in this browser. Changes apply immediately across the workspace."
        badges={<SettingsNavBadge tone="allowed">Browser preference</SettingsNavBadge>}
      />

      <div className="p-5">
        <h3 className="text-sm font-medium text-white">Theme</h3>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          Your selection is saved automatically on this device and restored before the interface loads.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Color theme">
          {options.map((option) => {
            const Icon = option.icon;
            const selected = theme === option.id;
            return (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setTheme(option.id)}
                className={`min-w-0 rounded-xl border p-3 text-left transition ${
                  selected
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : "border-zinc-700/40 bg-[#0f1117] hover:border-zinc-600"
                }`}
              >
                <span className="relative flex h-16 items-center justify-center overflow-hidden rounded-lg border border-zinc-700/40" style={option.previewStyle} aria-hidden="true">
                  <Icon className="h-6 w-6" />
                  <span
                    className={`absolute right-2 top-2 flex h-4 w-4 items-center justify-center rounded-full border ${
                      selected ? "border-emerald-400 bg-emerald-500 text-white" : "border-zinc-500 bg-transparent"
                    }`}
                  >
                    {selected ? <Check className="h-3 w-3" /> : null}
                  </span>
                </span>
                <span className="mt-3 block text-sm font-medium text-white">{option.label}</span>
                <span className="mt-1 block text-xs leading-5 text-slate-500">{option.description}</span>
              </button>
            );
          })}
        </div>
      </div>
    </article>
  );
}

function SettingsNavSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1">
      <h2 className="px-2 pb-1 pt-1 text-[11px] font-medium text-slate-500">{title}</h2>
      {children}
    </section>
  );
}

function SettingsNavBadge({ tone, children }: { tone: "ready" | "allowed" | "warn" | "muted"; children: React.ReactNode }) {
  const toneClass =
    tone === "ready"
      ? "bg-emerald-500/10 text-emerald-400"
      : tone === "allowed"
        ? "bg-cyan-300/10 text-cyan-200"
        : tone === "warn"
          ? "bg-amber-500/10 text-amber-300"
          : "bg-white/5 text-slate-500";

  return <span className={`${STATUS_PILL_CLASS} ${toneClass}`}>{children}</span>;
}

function SettingsNavRow({
  label,
  title,
  selected,
  onSelect,
  badge,
  icon: Icon,
  mark,
}: {
  label: string;
  title?: string;
  selected: boolean;
  onSelect: () => void;
  badge?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  mark?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "page" : undefined}
      title={title || label}
      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition ${
        selected
          ? "bg-emerald-500/10 font-medium text-emerald-400"
          : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-200"
      }`}
    >
      {mark}
      {!mark && Icon && <Icon className={`h-3.5 w-3.5 shrink-0 ${selected ? "text-emerald-400" : "text-zinc-500"}`} />}
      <span className="min-w-0 flex-1 truncate text-[13px]">{label}</span>
      {badge}
    </button>
  );
}

function SettingsNavBrandGroup({
  label,
  logo,
  selected,
  badge,
  children,
}: {
  label: string;
  logo: string;
  selected: boolean;
  badge: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-0.5" role="group" aria-label={label}>
      <div
        className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 ${
          selected ? "text-emerald-400" : "text-zinc-400"
        }`}
      >
        <ProviderMarkTile id={logo} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{label}</span>
        {badge}
      </div>
      <div className="ml-3 space-y-0.5 border-l border-[#2c2f37] pl-1.5">{children}</div>
    </div>
  );
}

export default function UserIntegrationsPage() {
  const { authRequired, getToken, hasIdentity, isLoaded, isSignedIn, openSignIn } = useFormaAuth();
  const [payload, setPayload] = useState<IntegrationsPayload | null>(null);
  const [forms, setForms] = useState<Record<string, IntegrationFormState>>({});
  const [selectedNavigationKey, setSelectedNavigationKey] = useState("runtime:all");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [imageTestPrompt, setImageTestPrompt] = useState(
    "A clean studio product render of a compact matte-black electronics enclosure, three-quarter view, neutral background, realistic materials."
  );
  const [imageTestRunning, setImageTestRunning] = useState(false);
  const [imageTestResult, setImageTestResult] = useState<ImageModelTestResult | null>(null);
  const [imageTestError, setImageTestError] = useState<string | null>(null);
  const [imageTestErrorDetails, setImageTestErrorDetails] = useState<unknown>(null);
  const [dataUsagePreference, setDataUsagePreference] = useState<DataUsagePreference | null>(null);
  const [allowModelTraining, setAllowModelTraining] = useState(true);
  const [dataUsageLoading, setDataUsageLoading] = useState(true);
  const [dataUsageSaving, setDataUsageSaving] = useState(false);

  const navigationGroups = useMemo(
    () => integrationNavigationGroups(payload?.integrations || []),
    [payload]
  );

  const selectedNavigationItem = useMemo(
    () => navigationGroups.flatMap(navigationGroupItems).find((item) => item.key === selectedNavigationKey) || null,
    [navigationGroups, selectedNavigationKey]
  );

  const isAppearanceView = selectedNavigationKey === "appearance:theme";
  const isDataPrivacyView = selectedNavigationKey === "privacy:data-usage";
  const isLocalSettingsView = isAppearanceView || isDataPrivacyView;
  const selectedIntegration = isLocalSettingsView
    ? null
    : selectedNavigationItem?.integration || payload?.integrations[0] || null;
  const selectedView = selectedNavigationItem?.view || "all";

  const integrationById = useCallback(
    (integrationId: string) => payload?.integrations.find((integration) => integration.id === integrationId),
    [payload]
  );

  const imageDefaults = useMemo(() => {
    const image = integrationById("image");
    const huggingface = integrationById("huggingface");
    const openai = integrationById("openai");
    const gmi = integrationById("gmi");
    const together = integrationById("together");
    const savedProvider = integrationField(image, "provider")?.value || "";
    const formProvider = image ? forms[image.id]?.fields.provider || "" : "";
    const changedProvider = formProvider && formProvider !== savedProvider ? formProvider : "";
    const inferredProvider = newestConfiguredImageProvider([
      {
        provider: "huggingface",
        integration: huggingface,
        configured: Boolean(formFieldValue(forms, huggingface, "image_model")),
      },
      {
        provider: "gmi",
        integration: gmi,
        configured: Boolean(formFieldValue(forms, gmi, "api_key") || integrationField(gmi, "api_key")?.configured),
      },
      {
        provider: "together",
        integration: together,
        configured: Boolean(formFieldValue(forms, together, "api_key") || integrationField(together, "api_key")?.configured),
      },
      {
        provider: "openai",
        integration: openai,
        configured: Boolean(formFieldValue(forms, openai, "image_model")),
      },
    ]);
    const provider = changedProvider || formProvider || savedProvider || inferredProvider || "none";
    const providerOption = IMAGE_PROVIDER_OPTIONS.find((option) => option.id === provider) || IMAGE_PROVIDER_OPTIONS[0];
    const providerIntegration = providerOption.integrationId ? integrationById(providerOption.integrationId) : undefined;
    const providerModel = providerOption.modelFieldId ? formFieldValue(forms, providerIntegration, providerOption.modelFieldId) : "";
    const model = providerModel || (providerOption.preconfigured ? "" : providerOption.models[0]?.value || "");
    const modelOptions = uniqueModelOptions(providerOption.models);
    return { provider: providerOption.id, model, modelOptions, providerOption, providerIntegration };
  }, [forms, integrationById]);

  const defaultLlmProvider = useMemo(() => {
    const runtime = integrationById("runtime");
    return parsePreferredLlmProvider(
      formFieldValue(forms, runtime, "llm_selector"),
      formFieldValue(forms, runtime, "llm_provider"),
    );
  }, [forms, integrationById]);

  const imageOutputEnabled = useMemo(() => {
    const image = integrationById("image");
    return imageOutputIsEnabled(formFieldValue(forms, image, "enabled"), imageDefaults.provider);
  }, [forms, imageDefaults.provider, integrationById]);

  const selectedFieldGroups = useMemo(() => {
    if (!selectedIntegration || isLocalSettingsView || selectedView === "image") return [];
    return integrationFieldGroups(selectedIntegration, selectedView);
  }, [isLocalSettingsView, selectedIntegration, selectedView]);
  const basicFieldGroups = selectedFieldGroups.filter((group) => group.level === "basic");
  const advancedFieldGroups = selectedFieldGroups.filter((group) => group.level === "advanced");
  const advancedConfiguredCount = selectedIntegration
    ? advancedFieldGroups.reduce(
        (count, group) => count + group.fields.filter((field) => fieldHasValue(forms, selectedIntegration, field)).length,
        0
      )
    : 0;

  const advancedOpenSnapshotRef = useRef({ forms, imageDefaults, selectedIntegration, selectedView });
  advancedOpenSnapshotRef.current = { forms, imageDefaults, selectedIntegration, selectedView };

  useEffect(() => {
    const snapshot = advancedOpenSnapshotRef.current;
    if (snapshot.selectedView === "image") {
      const ids =
        snapshot.imageDefaults.provider === "gmi"
          ? ["image_base_url", ...gmiImageSettingFieldIds(snapshot.imageDefaults.model), "image_timeout_seconds"]
          : snapshot.imageDefaults.providerOption.advancedFieldIds;
      setShowAdvanced(
        ids.some((fieldId) => {
          const field = integrationField(snapshot.imageDefaults.providerIntegration, fieldId);
          return Boolean(field && fieldHasValue(snapshot.forms, snapshot.imageDefaults.providerIntegration, field));
        })
      );
      return;
    }
    const snapshotIntegration = snapshot.selectedIntegration;
    if (!snapshotIntegration) {
      setShowAdvanced(false);
      return;
    }
    const advanced = integrationFieldGroups(snapshotIntegration, snapshot.selectedView).filter((group) => group.level === "advanced");
    setShowAdvanced(
      advanced.some((group) => group.fields.some((field) => fieldHasValue(snapshot.forms, snapshotIntegration, field)))
    );
  }, [imageDefaults.provider, selectedIntegration?.id, selectedNavigationKey, selectedView]);

  function navItemBadge(item: IntegrationNavigationItem) {
    return settingsNavBadge({
      view: item.view,
      integrationId: item.integrationId,
      imageProviderId: item.imageProviderId,
      configured: item.integration.configured,
      enabled: item.integration.enabled,
      defaultLlmProvider,
      imageOutputEnabled,
      activeImageProvider: imageDefaults.provider,
    });
  }

  function renderIntegrationNavRow(item: IntegrationNavigationItem) {
    const badge = navItemBadge(item);
    const markId = item.logo || item.integrationId;
    return (
      <SettingsNavRow
        key={item.key}
        label={item.label}
        title={navigationDescription(item)}
        selected={selectedNavigationKey === item.key}
        icon={item.integrationId === "runtime" ? SlidersHorizontal : undefined}
        mark={item.integrationId === "runtime" ? undefined : <ProviderMarkTile id={markId} />}
        onSelect={() => {
          if (item.imageProviderId) updateImageProvider(item.imageProviderId);
          else setSelectedNavigationKey(item.key);
        }}
        badge={<SettingsNavBadge tone={badge.tone}>{badge.label}</SettingsNavBadge>}
      />
    );
  }

  function renderNavBlock(block: IntegrationNavBlock, keyPrefix: string) {
    if (block.type === "brand") {
      const childSelected = block.brand.items.some((item) => item.key === selectedNavigationKey);
      const badge = aggregateNavBadge(block.brand.items.map(navItemBadge));
      return (
        <SettingsNavBrandGroup
          key={`${keyPrefix}:${block.brand.id}`}
          label={block.brand.label}
          logo={block.brand.logo}
          selected={childSelected}
          badge={<SettingsNavBadge tone={badge.tone}>{badge.label}</SettingsNavBadge>}
        >
          {block.brand.items.map(renderIntegrationNavRow)}
        </SettingsNavBrandGroup>
      );
    }
    return (
      <React.Fragment key={`${keyPrefix}:items:${block.items.map((item) => item.key).join("+")}`}>
        {block.items.map(renderIntegrationNavRow)}
      </React.Fragment>
    );
  }

  useEffect(() => {
    setImageTestResult(null);
    setImageTestError(null);
    setImageTestErrorDetails(null);
  }, [imageDefaults.provider, imageDefaults.model]);

  const optionalAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!authRequired || !isSignedIn) return {};
    try {
      const token = await getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, [authRequired, getToken, isSignedIn]);

  const loadIntegrations = useCallback(async () => {
    if (authRequired && !isLoaded) return;
    if (!hasIdentity) {
      setPayload(null);
      setForms({});
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations`, {
        cache: "no-store",
        headers: await optionalAuthHeaders(),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, "Failed to load integrations."));
      const data = (await response.json()) as IntegrationsPayload;
      setPayload(data);
      setForms(Object.fromEntries(data.integrations.map((integration) => [integration.id, formFromIntegration(integration)])));
      const availableNavigationItems = integrationNavigationGroups(data.integrations).flatMap(navigationGroupItems);
      setSelectedNavigationKey((current) =>
        current === "appearance:theme" || current === "privacy:data-usage" || availableNavigationItems.some((item) => item.key === current)
          ? current
          : availableNavigationItems[0]?.key || "runtime:all"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  }, [authRequired, hasIdentity, isLoaded, optionalAuthHeaders]);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const loadDataUsagePreference = useCallback(async () => {
    if (authRequired && !isLoaded) return;
    if (!hasIdentity) {
      setDataUsagePreference(null);
      setAllowModelTraining(true);
      setDataUsageLoading(false);
      return;
    }
    setDataUsageLoading(true);
    try {
      const response = await fetch(`${API_URL}/user/settings/data-usage`, {
        cache: "no-store",
        headers: await optionalAuthHeaders(),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, "Failed to load data usage preference."));
      const data = (await response.json()) as DataUsagePreference;
      setDataUsagePreference(data);
      setAllowModelTraining(data.allow_model_training);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data usage preference.");
    } finally {
      setDataUsageLoading(false);
    }
  }, [authRequired, hasIdentity, isLoaded, optionalAuthHeaders]);

  useEffect(() => {
    loadDataUsagePreference();
  }, [loadDataUsagePreference]);

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

  function updateImageProvider(provider: string) {
    const providerOption = IMAGE_PROVIDER_OPTIONS.find((option) => option.id === provider);
    updateField("image", "provider", provider);
    setSelectedNavigationKey(imageNavigationKey(provider));
    updateField("image", "enabled", provider === "none" ? "false" : "true");
    updateEnabled("image", provider !== "none");
    if (providerOption?.integrationId) updateEnabled(providerOption.integrationId, provider !== "none");
    if (providerOption?.integrationId && providerOption.modelFieldId && !providerOption.preconfigured) {
      const providerIntegration = integrationById(providerOption.integrationId);
      const existingModel = formFieldValue(forms, providerIntegration, providerOption.modelFieldId);
      if (!existingModel && providerOption.models[0]) updateField(providerOption.integrationId, providerOption.modelFieldId, providerOption.models[0].value);
    }
  }

  function updateImageModel(model: string) {
    const providerOption = IMAGE_PROVIDER_OPTIONS.find((option) => option.id === imageDefaults.provider);
    if (providerOption?.integrationId && providerOption.modelFieldId) {
      updateField(providerOption.integrationId, providerOption.modelFieldId, model);
      return;
    }
    updateField("image", "model", model);
  }

  async function saveIntegrationById(integrationId: string) {
    const integration = integrationById(integrationId);
    if (!integration) return;
    await saveIntegration(integration);
  }

  async function saveImageDefaults() {
    if (!hasIdentity) return;
    const providerOption = IMAGE_PROVIDER_OPTIONS.find((option) => option.id === imageDefaults.provider);
    setSavingId("image-defaults");
    setError(null);
    setNotice(null);
    try {
      await saveIntegrationById("image");
      if (providerOption?.integrationId && providerOption.integrationId !== "image") {
        await saveIntegrationById(providerOption.integrationId);
      }
      setNotice("Image provider saved. New generations will use the selected provider and its configured defaults.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save image defaults.");
    } finally {
      setSavingId(null);
    }
  }

  async function saveIntegration(integration: IntegrationStatus, clearFields: string[] = []) {
    if (!hasIdentity) return;
    const form = forms[integration.id] || formFromIntegration(integration);
    const fields: Record<string, string> = {};
    const clearFieldSet = new Set(clearFields);
    integration.fields.forEach((field) => {
      if (!field.editable) return;
      if (clearFieldSet.has(field.id)) return;
      const value = form.fields[field.id] || "";
      if (field.secret && !value.trim()) return;
      // Environment-backed values are visible defaults, not implicit BYOK
      // values. Persist them only when the user actually changes the field.
      if (field.source === "environment" && value === (field.value || "")) return;
      if (field.source === "unset" && !value.trim()) return;
      fields[field.id] = value;
    });

    setSavingId(integration.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/${encodeURIComponent(integration.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(await optionalAuthHeaders()) },
        body: JSON.stringify({
          enabled: form.enabled,
          fields,
          clear_fields: clearFields,
        }),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, `Failed to save ${integration.label}.`));
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
    if (!hasIdentity) return;
    setSavingId(integration.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/${encodeURIComponent(integration.id)}`, {
        method: "DELETE",
        headers: await optionalAuthHeaders(),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, `Failed to clear ${integration.label}.`));
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
    if (!hasIdentity) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/reload`, {
        method: "POST",
        headers: await optionalAuthHeaders(),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, "Failed to reload integrations."));
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

  async function saveDataUsagePreference() {
    if (!hasIdentity) return;
    setDataUsageSaving(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/user/settings/data-usage`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(await optionalAuthHeaders()) },
        body: JSON.stringify({ allow_model_training: allowModelTraining }),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, "Failed to save data usage preference."));
      const data = (await response.json()) as DataUsagePreference;
      setDataUsagePreference(data);
      setAllowModelTraining(data.allow_model_training);
      setNotice(data.allow_model_training
        ? "Data usage preference saved. This does not grant project contribution consent."
        : "Opt-out saved. Your outputs will be excluded from future model-improvement dataset exports.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save data usage preference.");
    } finally {
      setDataUsageSaving(false);
    }
  }

  async function runImageModelTest() {
    if (!hasIdentity || !imageTestPrompt.trim()) return;
    setImageTestRunning(true);
    setImageTestResult(null);
    setImageTestError(null);
    setImageTestErrorDetails(null);
    try {
      const response = await fetch(`${API_URL}/user/integrations/image-model-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(await optionalAuthHeaders()) },
        body: JSON.stringify({
          provider: imageDefaults.provider,
          model: imageDefaults.model,
          prompt: imageTestPrompt.trim(),
        }),
      });
      const responseText = await response.text();
      let body: ImageModelTestResult & {
        detail?: string | { message?: string; code?: string; [key: string]: unknown };
      };
      try {
        body = JSON.parse(responseText) as typeof body;
      } catch {
        setImageTestError(`Image model test returned HTTP ${response.status} with a non-JSON response.`);
        setImageTestErrorDetails({
          status: response.status,
          status_text: response.statusText,
          response_preview: responseText.slice(0, 2000),
        });
        return;
      }
      if (!response.ok) {
        const detail = body.detail;
        const message = typeof detail === "string"
          ? detail
          : detail?.message || `Image model test failed with HTTP ${response.status}.`;
        const code = typeof detail === "object" && detail?.code ? ` (${detail.code})` : "";
        setImageTestError(`${message}${code}`);
        setImageTestErrorDetails(detail || body);
        return;
      }
      setImageTestResult(body);
    } catch (err) {
      setImageTestError(err instanceof Error ? err.message : "Image model test failed.");
      setImageTestErrorDetails({ error_type: err instanceof Error ? err.name : "UnknownError" });
    } finally {
      setImageTestRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0f1117] font-sans text-slate-100">
      <header className="border-b border-[#2c2f37] bg-[#0f1117]/95 px-4 py-4">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3">
          <Link href="/" className={BUTTON_OUTLINE_CLASS}>
            <ArrowLeft className="h-3.5 w-3.5" />
            Home
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight text-white">Settings</h1>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              Appearance, provider credentials, model defaults, and account data preferences.
            </p>
          </div>
        </div>
      </header>

      {authRequired && !isLoaded ? (
        <section className="mx-auto w-full max-w-7xl px-4 py-5">
          <div className={`${CARD_SURFACE_CLASS} p-6 text-sm text-slate-500`}>Checking session...</div>
        </section>
      ) : !hasIdentity ? (
        <section className="mx-auto grid w-full max-w-7xl gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <ThemeSettingsPanel />
          <div className={`h-fit ${CARD_SURFACE_CLASS} p-6`}>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-white">
              <KeyRound className="h-4 w-4 text-emerald-400" />
              Sign in required
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Settings store API keys and provider defaults for your account. Sign in to manage your models.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/settings" })}
                className={BUTTON_PRIMARY_CLASS}
              >
                <KeyRound className="h-3.5 w-3.5" />
                Sign in
              </button>
              <Link href="/" className={BUTTON_OUTLINE_CLASS}>
                <ArrowLeft className="h-3.5 w-3.5" />
                Home
              </Link>
            </div>
          </div>
        </section>
      ) : (
        <section className="mx-auto grid w-full max-w-7xl gap-5 px-4 py-5 md:grid-cols-[240px_minmax(0,1fr)]">
        <aside className={`h-fit min-h-0 ${CARD_SURFACE_CLASS} md:sticky md:top-4`}>
          <div className="border-b border-[#2c2f37] px-3 py-3">
            <div className="text-sm font-semibold text-white">Settings</div>
            <p className="mt-1 text-[11px] leading-4 text-slate-400">Account, models, and workspace defaults.</p>
          </div>

          <nav aria-label="Settings" className="max-h-[calc(100vh-180px)] space-y-4 overflow-y-auto p-2">
            <SettingsNavSection title="Account">
              <SettingsNavRow
                label="Appearance"
                title="Choose and save your light or dark theme."
                icon={Palette}
                selected={isAppearanceView}
                onSelect={() => setSelectedNavigationKey("appearance:theme")}
              />
              <SettingsNavRow
                label="Data & Privacy"
                title="Control use of your outputs for model improvement."
                icon={ShieldCheck}
                selected={isDataPrivacyView}
                onSelect={() => setSelectedNavigationKey("privacy:data-usage")}
                badge={
                  <SettingsNavBadge tone={dataUsageLoading ? "muted" : allowModelTraining ? "allowed" : "warn"}>
                    {dataUsageLoading ? "Loading" : allowModelTraining ? "Allowed" : "Opted out"}
                  </SettingsNavBadge>
                }
              />
            </SettingsNavSection>

            <SettingsNavSection title="Workspace & Models">
              {loading && !payload ? (
                <div className="px-2 py-2 text-[11px] leading-5 text-slate-500">Loading integrations...</div>
              ) : !navigationGroups.length ? (
                <div className="rounded-lg border border-[#2c2f37] p-3">
                  <p className="text-[11px] leading-5 text-slate-400">
                    {error ? "Could not load integrations." : "No integrations are available for this workspace."}
                  </p>
                  {error && <p className="mt-1 break-words text-[11px] leading-5 text-slate-600">{error}</p>}
                  <button type="button" onClick={loadIntegrations} disabled={loading} className={`mt-3 ${BUTTON_OUTLINE_CLASS}`}>
                    <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                    Retry
                  </button>
                </div>
              ) : (
                navigationGroups.map((group) => (
                  <div key={group.id} className="space-y-0.5">
                    {group.id !== "workspace" && <SettingsNavSubhead>{group.label}</SettingsNavSubhead>}
                    {group.sections.length
                      ? group.sections.map((section) => (
                          <div key={section.id} className="space-y-0.5">
                            <SettingsNavSubhead>{section.label}</SettingsNavSubhead>
                            {section.blocks.map((block, index) => renderNavBlock(block, `${group.id}:${section.id}:${index}`))}
                          </div>
                        ))
                      : navigationGroupItems(group).map(renderIntegrationNavRow)}
                  </div>
                ))
              )}
            </SettingsNavSection>
          </nav>
        </aside>

        <section className="min-w-0">
          {error && (
            <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/30 p-4 text-sm leading-6 text-rose-200">
              <div className="flex items-center gap-2 text-sm font-medium">
                <AlertTriangle className="h-4 w-4" />
                Error
              </div>
              <p className="mt-2 break-words">{error}</p>
            </div>
          )}

          {notice && (
            <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-950/30 p-4 text-sm leading-6 text-emerald-200">
              <div className="flex items-center gap-2 text-sm font-medium">
                <CheckCircle className="h-4 w-4" />
                Applied
              </div>
              <p className="mt-2">{notice}</p>
            </div>
          )}

          {isAppearanceView ? (
            <ThemeSettingsPanel />
          ) : isDataPrivacyView ? (
            <article className={CARD_SURFACE_CLASS}>
              <SettingsPaneHeader
                title="Data & Privacy"
                description="Set an account-wide limit on future dataset use. This setting never grants project contribution consent."
                badges={<SettingsNavBadge tone="allowed">Account preference</SettingsNavBadge>}
                actions={
                  <>
                    <Link href="/legal/privacy-policy" className={BUTTON_OUTLINE_CLASS}>
                      Privacy Policy
                    </Link>
                    <button
                      type="button"
                      onClick={saveDataUsagePreference}
                      disabled={dataUsageLoading || dataUsageSaving}
                      className={BUTTON_PRIMARY_CLASS}
                    >
                      <Save className="h-3.5 w-3.5" />
                      {dataUsageSaving ? "Saving" : "Save"}
                    </button>
                  </>
                }
              />

              <div className="space-y-8 p-5">
                <section>
                  <h3 className="text-sm font-medium text-white">Account-wide contribution limit</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Keep account outputs eligible only when you also make a separate, explicit, purpose-specific project contribution choice.
                  </p>
                  <div className="mt-4">
                    <SettingsFieldCard
                      title="Model training eligibility"
                      help="Turn this off to block account-linked outputs from future training-dataset exports. Eligibility alone does not contribute a project."
                      extraHelp="Deleted projects are contributed only through the optional, unselected choice in the deletion dialog. For access or deletion requests, use the contact in the Privacy Policy."
                      chips={<SettingsNavBadge tone={allowModelTraining ? "allowed" : "warn"}>{allowModelTraining ? "Eligible" : "Opted out"}</SettingsNavBadge>}
                    >
                      <label
                        className={`inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-[#2c2f37] px-3 text-xs font-medium ${
                          dataUsageLoading
                            ? "cursor-wait text-slate-600"
                            : allowModelTraining
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "text-slate-300"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={allowModelTraining}
                          onChange={(event) => setAllowModelTraining(event.target.checked)}
                          disabled={dataUsageLoading || dataUsageSaving}
                          className="h-3.5 w-3.5 accent-emerald-400"
                        />
                        {allowModelTraining ? "Eligible" : "Opted out"}
                      </label>
                    </SettingsFieldCard>
                  </div>
                  <p className="mt-4 text-xs leading-5 text-slate-500">
                    {dataUsagePreference?.source === "user"
                      ? `Saved ${formatTimestamp(dataUsagePreference.updated_at)}`
                      : "Using the default setting; no account preference has been saved yet."}
                  </p>
                </section>

                <section>
                  <h3 className="text-sm font-medium text-white">How opt-outs are tracked</h3>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    Forma stores the account owner ID, an opt-out flag, and created/updated timestamps. Dataset export jobs must exclude every owner ID whose opt-out flag is set, and eligibility never replaces a project-specific consent record.
                  </p>
                </section>
              </div>
            </article>
          ) : payload && selectedIntegration && selectedView === "image" ? (
            <>
              <ImageProviderSetup
                forms={forms}
                provider={imageDefaults.provider}
                providerOption={imageDefaults.providerOption}
                providerIntegration={imageDefaults.providerIntegration}
                imageIntegration={integrationById("image")}
                model={imageDefaults.model}
                modelOptions={imageDefaults.modelOptions}
                saving={savingId !== null}
                showAdvanced={showAdvanced}
                onProviderChange={updateImageProvider}
                onModelChange={updateImageModel}
                onFieldChange={updateField}
                onEnabledChange={updateEnabled}
                onSave={saveImageDefaults}
                onClear={clearIntegration}
                onReload={reloadRuntime}
                reloading={loading}
                onToggleAdvanced={() => setShowAdvanced((current) => !current)}
              />
              {payload.image_model_test_available && (
                <ImageModelTestPanel
                  provider={imageDefaults.provider}
                  model={imageDefaults.model}
                  prompt={imageTestPrompt}
                  running={imageTestRunning}
                  result={imageTestResult}
                  error={imageTestError}
                  errorDetails={imageTestErrorDetails}
                  onPromptChange={setImageTestPrompt}
                  onRun={runImageModelTest}
                />
              )}
            </>
          ) : selectedIntegration ? (
            <article className={CARD_SURFACE_CLASS}>
              <SettingsPaneHeader
                title={selectedNavigationItem?.label || selectedIntegration.label}
                description={navigationDescription(selectedNavigationItem)}
                badges={
                  <>
                    {navigationGroups.some((group) => group.advanced.some((item) => item.key === selectedNavigationKey)) && (
                      <SettingsNavBadge tone="muted">Advanced</SettingsNavBadge>
                    )}
                    {selectedView === "llm" && <SettingsNavBadge tone="allowed">LLM only</SettingsNavBadge>}
                    <SettingsNavBadge tone={selectedIntegration.configured ? "ready" : "muted"}>
                      {selectedIntegration.configured ? "Configured" : "Unset"}
                    </SettingsNavBadge>
                    {selectedIntegration.policy_status && selectedIntegration.policy_status !== "enabled" && (
                      <SettingsNavBadge tone="warn">BYOK {selectedIntegration.policy_status}</SettingsNavBadge>
                    )}
                  </>
                }
                meta={
                  <>
                    {selectedIntegration.policy_notice && (
                      <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-200">{selectedIntegration.policy_notice}</p>
                    )}
                    <p className="mt-2 text-xs text-slate-500">Updated {formatTimestamp(selectedIntegration.updated_at)}</p>
                  </>
                }
                actions={
                  <>
                    <SettingsEnabledControl
                      checked={forms[selectedIntegration.id]?.enabled ?? selectedIntegration.enabled}
                      disabled={savingId === selectedIntegration.id}
                      onChange={(checked) => updateEnabled(selectedIntegration.id, checked)}
                    />
                    <button
                      type="button"
                      onClick={() => saveIntegration(selectedIntegration)}
                      disabled={savingId === selectedIntegration.id}
                      className={BUTTON_PRIMARY_CLASS}
                    >
                      <Save className="h-3.5 w-3.5" />
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => clearIntegration(selectedIntegration)}
                      disabled={savingId === selectedIntegration.id}
                      className={BUTTON_DANGER_CLASS}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Clear
                    </button>
                    <button type="button" onClick={reloadRuntime} disabled={loading} className={BUTTON_OUTLINE_CLASS}>
                      <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                      Reload integrations
                    </button>
                  </>
                }
              />

              <div className="space-y-8 p-5">
                {basicFieldGroups.length > 0 && (
                  <IntegrationFieldGroupList
                    groups={basicFieldGroups}
                    integration={selectedIntegration}
                    forms={forms}
                    saving={savingId === selectedIntegration.id}
                    onChange={(fieldId, value) => updateField(selectedIntegration.id, fieldId, value)}
                    onClearSaved={(fieldId) => saveIntegration(selectedIntegration, [fieldId])}
                  />
                )}
                {advancedFieldGroups.length > 0 && (
                  <SettingsAdvancedDisclosure
                    open={showAdvanced}
                    onToggle={() => setShowAdvanced((current) => !current)}
                    description="Connection, timeouts, rendering extras, and other optional provider settings."
                    configuredCount={advancedConfiguredCount}
                  >
                    <IntegrationFieldGroupList
                      groups={advancedFieldGroups}
                      integration={selectedIntegration}
                      forms={forms}
                      saving={savingId === selectedIntegration.id}
                      onChange={(fieldId, value) => updateField(selectedIntegration.id, fieldId, value)}
                      onClearSaved={(fieldId) => saveIntegration(selectedIntegration, [fieldId])}
                    />
                  </SettingsAdvancedDisclosure>
                )}
              </div>
            </article>
          ) : (
            <div className={`${CARD_SURFACE_CLASS} p-6 text-slate-500`}>No integrations found.</div>
          )}
        </section>
        </section>
      )}
    </main>
  );
}
