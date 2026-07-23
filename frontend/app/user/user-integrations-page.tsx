"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SignInButton, useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  ChevronDown,
  FlaskConical,
  KeyRound,
  RefreshCw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import {
  gmiImageSettingFieldIds,
  IMAGE_MODEL_OPTIONS,
  modelOptionsForField,
  settingOptionsForField,
  type ProviderModelOption,
} from "../../lib/provider-model-catalog";

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
};

const IMAGE_PROVIDER_OPTIONS: ImageProviderOption[] = [
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
  },
];

type IntegrationView = "all" | "llm" | "image";

type IntegrationNavigationDefinition = {
  integrationId: string;
  view: IntegrationView;
  label?: string;
  imageProviderId?: string;
};

const INTEGRATION_NAV_GROUPS: Array<{ id: string; label: string; items: IntegrationNavigationDefinition[] }> = [
  { id: "workspace", label: "Workspace", items: [{ integrationId: "runtime", view: "all" }] },
  {
    id: "llm",
    label: "Language Model Providers",
    items: [
      { integrationId: "openai", view: "llm", label: "OpenAI LLM" },
      { integrationId: "anthropic", view: "llm" },
      { integrationId: "gemini", view: "llm" },
      { integrationId: "baseten", view: "llm" },
      { integrationId: "gmi", view: "llm", label: "GMI Cloud LLM" },
      { integrationId: "huggingface", view: "llm", label: "Hugging Face LLM" },
      { integrationId: "nvidia", view: "llm" },
      { integrationId: "runpod", view: "llm" },
      { integrationId: "ollama", view: "llm" },
    ],
  },
  {
    id: "image",
    label: "Image Providers",
    items: [
      { integrationId: "openai", view: "image", label: "OpenAI Images", imageProviderId: "openai" },
      { integrationId: "gmi", view: "image", label: "GMI Cloud Images", imageProviderId: "gmi" },
      { integrationId: "huggingface", view: "image", label: "Hugging Face Images", imageProviderId: "huggingface" },
      { integrationId: "together", view: "image", label: "Together AI Images", imageProviderId: "together" },
      { integrationId: "image", view: "image", label: "Image Output & Custom" },
    ],
  },
  { id: "tools", label: "Tools & Search", items: [{ integrationId: "firecrawl", view: "all" }] },
];

type IntegrationNavigationItem = IntegrationNavigationDefinition & {
  key: string;
  label: string;
  integration: IntegrationStatus;
};

type IntegrationNavigationGroup = {
  id: string;
  label: string;
  items: IntegrationNavigationItem[];
};

function integrationNavigationGroups(integrations: IntegrationStatus[]) {
  const includedIds = new Set<string>(INTEGRATION_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.integrationId)));
  const groups: IntegrationNavigationGroup[] = INTEGRATION_NAV_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    items: group.items.flatMap((item) => {
      const integration = integrations.find((candidate) => candidate.id === item.integrationId);
      if (!integration) return [];
      return [{ ...item, key: `${item.integrationId}:${item.view}`, label: item.label || integration.label, integration }];
    }),
  })).filter((group) => group.items.length > 0);
  const other = integrations.filter((integration) => !includedIds.has(integration.id));
  if (other.length) {
    groups.push({
      id: "other",
      label: "Other",
      items: other.map((integration) => ({
        integrationId: integration.id,
        view: "all",
        key: `${integration.id}:all`,
        label: integration.label,
        integration,
      })),
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
    "dedicated-to-blueprint",
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
  fields: IntegrationFieldStatus[];
};

const LANGUAGE_MODEL_FIELD_IDS = new Set([
  "model",
  "fallback_model",
  "max_tokens",
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
        label: "Language Model Defaults",
        description: "Choose the default LLM and optional runtime restrictions.",
        fieldIds: ["llm_selector", "llm_provider", "llm_model", "allowed_providers"],
      },
      {
        id: "image",
        label: "Image Defaults",
        description: "Fallback image provider and model values for generated visuals.",
        fieldIds: ["image_provider", "image_model"],
      },
      {
        id: "research",
        label: "Research Tools",
        description: "Select the external source used for web research.",
        fieldIds: ["external_source_provider"],
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
    { id: "credentials", label: "Credentials", description: "Authentication and required credential-scope confirmations.", fields: [] },
    { id: "language", label: "Language Models", description: "Text model defaults and generation settings.", fields: [] },
    { id: "image", label: "Image Generation", description: "Image model defaults and rendering settings.", fields: [] },
    { id: "video", label: "Video Generation", description: "Video endpoints and model defaults.", fields: [] },
    { id: "connection", label: "Connection & Advanced", description: "Endpoint, timeout, storage, and provider-specific settings.", fields: [] },
  ];
  const byId = new Map(groups.map((group) => [group.id, group]));

  integration.fields.forEach((field) => {
    if (field.secret || isConfirmationField(field)) {
      byId.get("credentials")?.fields.push(field);
    } else if (field.id.startsWith("video_") || field.id === "image_to_video_model") {
      byId.get("video")?.fields.push(field);
    } else if (integration.id === "image" || integration.id === "together" || field.id.startsWith("image_")) {
      byId.get("image")?.fields.push(field);
    } else if (LANGUAGE_MODEL_FIELD_IDS.has(field.id)) {
      byId.get("language")?.fields.push(field);
    } else {
      byId.get("connection")?.fields.push(field);
    }
  });
  const populatedGroups = groups.filter((group) => group.fields.length > 0);
  if (view === "llm") return populatedGroups.filter((group) => ["credentials", "language", "connection"].includes(group.id));
  if (view === "image") return populatedGroups.filter((group) => ["credentials", "image"].includes(group.id));
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
      <div className="flex h-11 border border-[#2c2f37] bg-black focus-within:border-cyan-300">
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
          className="h-full min-w-0 flex-1 bg-transparent px-3 font-mono text-sm text-white outline-none placeholder:text-slate-700 disabled:cursor-not-allowed disabled:text-slate-600"
        />
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          disabled={disabled}
          aria-label={`Show ${suggestionType} suggestions`}
          className="inline-flex w-10 shrink-0 items-center justify-center border-l border-[#2c2f37] text-slate-500 hover:bg-white hover:text-black disabled:cursor-not-allowed"
        >
          <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      {open && !disabled && (
        <div id={listId} role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto border border-[#3a3d46] bg-[#0f1013] shadow-2xl">
          {filteredOptions.length ? (
            filteredOptions.map((option, index) => (
              <React.Fragment key={option.value}>
                {option.group && option.group !== filteredOptions[index - 1]?.group && (
                  <div className="sticky top-0 border-b border-[#3a3d46] bg-[#17181d] px-3 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-cyan-300">
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
                  className={`block w-full border-b border-[#24262c] px-3 py-3 text-left last:border-b-0 hover:bg-cyan-300/10 ${
                    option.value === value ? "bg-cyan-300/10" : ""
                  }`}
                >
                  <span className="block text-sm font-black text-white">{option.label}</span>
                  <span className="mt-1 block break-all font-mono text-[11px] text-slate-500">{option.value}</span>
                  {option.detail && <span className="mt-1 block text-[11px] text-slate-400">{option.detail}</span>}
                </button>
              </React.Fragment>
            ))
          ) : (
            <div className="px-3 py-3 text-xs leading-5 text-slate-400">No matching suggestion. Keep your custom model ID and save it.</div>
          )}
          <div className="sticky bottom-0 border-t border-[#3a3d46] bg-[#17181d] px-3 py-2 text-[10px] font-black uppercase tracking-wider text-slate-500">
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
    <article className="border border-[#2c2f37] bg-[#17181d]">
      <div className="border-b border-[#2c2f37] p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-black uppercase tracking-wide text-white">Image Generation</h2>
              <span className="border border-cyan-300/35 bg-cyan-300/10 px-2 py-1 text-[10px] font-black uppercase text-cyan-200">
                {providerOption.label}
              </span>
              {providerIntegration?.configured && (
                <span className="border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase text-emerald-300">
                  Credentials saved
                </span>
              )}
            </div>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{providerOption.summary}</p>
            {providerIntegration?.policy_notice && <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-200">{providerIntegration.policy_notice}</p>}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <label className="inline-flex h-11 cursor-pointer items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(enabled)}
                onChange={(event) => {
                  onProviderChange(event.target.checked ? provider : "none");
                  if (imageIntegration) onEnabledChange(imageIntegration.id, event.target.checked);
                  if (providerIntegration) onEnabledChange(providerIntegration.id, event.target.checked);
                }}
                className="h-4 w-4 accent-cyan-300"
              />
              Enabled
            </label>
            <button
              type="button"
              onClick={onSave}
              disabled={!canSave}
              className="inline-flex h-11 items-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-widest text-black hover:bg-slate-200 disabled:cursor-wait disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              Save
            </button>
            {providerIntegration?.configured && (
              <button
                type="button"
                onClick={() => onClear(providerIntegration)}
                disabled={saving}
                className="inline-flex h-11 items-center gap-2 border border-rose-400/40 px-4 text-xs font-black uppercase tracking-widest text-rose-200 hover:bg-rose-500 hover:text-white disabled:cursor-wait disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
                Clear
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-5 p-5">
        <section className="border border-[#2c2f37] bg-[#141519] p-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(180px,280px)_minmax(0,1fr)]">
            <label className="min-w-0">
              <span className="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-500">Provider</span>
              <select
                value={provider}
                onChange={(event) => onProviderChange(event.target.value)}
                className="h-11 w-full border border-[#2c2f37] bg-black px-3 text-sm font-black uppercase tracking-wide text-white outline-none focus:border-cyan-300"
              >
                {IMAGE_PROVIDER_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="border border-[#2c2f37] p-3">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Required</div>
                <div className="mt-2 text-sm font-black text-white">
                  {requiredCount ? `${readyCount}/${requiredCount} set` : "None"}
                </div>
              </div>
              <div className="border border-[#2c2f37] p-3">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Model</div>
                <div className="mt-2 truncate text-sm font-black text-white">
                  {providerOption.preconfigured && !model ? "Provider default" : model || "Off"}
                </div>
              </div>
              <div className="border border-[#2c2f37] p-3">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Mode</div>
              <div className="mt-2 text-sm font-black text-white">{providerOption.preconfigured ? "Preconfigured" : "Configurable"}</div>
              </div>
            </div>
          </div>
          {missingRequiredFields.length > 0 && (
            <div className="mt-4 border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
              Missing required setup: {missingRequiredFields.map((field) => field.label).join(", ")}.
            </div>
          )}
        </section>

        {provider === "none" ? (
          <section className="border border-[#2c2f37] bg-[#141519] p-5 text-sm leading-6 text-slate-400">
            Image generation is off. Generated projects will skip product visuals.
          </section>
        ) : (
          <>
            <section className="border border-[#2c2f37] bg-[#141519] p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-black uppercase tracking-wide text-white">Required Setup</h3>
                <span className="border border-[#2c2f37] px-2 py-1 text-[10px] font-black uppercase text-slate-500">
                  API credentials
                </span>
              </div>
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

            <section className="border border-[#2c2f37] bg-[#141519] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h3 className="text-sm font-black uppercase tracking-wide text-white">Model Defaults</h3>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    Use the preconfigured default now. Open advanced settings whenever you want to switch models.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onToggleAdvanced}
                  className="inline-flex h-10 items-center justify-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-300 hover:bg-white hover:text-black"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  {showAdvanced ? "Hide advanced" : "Advanced"}
                </button>
              </div>

              {!providerOption.preconfigured && modelField && (
                <div className="mt-4">
                  <label htmlFor={`image-model-${providerOption.id}`} className="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-500">
                    Image model
                  </label>
                  <ModelCombobox
                    id={`image-model-${providerOption.id}`}
                    value={model}
                    onChange={onModelChange}
                    options={modelOptions}
                    placeholder={providerOption.models[0]?.value || modelField.placeholder || "provider/model-name"}
                  />
                </div>
              )}

              {providerOption.preconfigured && (
                <div className="mt-4 border border-emerald-400/25 bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-100">
                  Ready with provider defaults after credentials are saved.
                  {model ? <span className="font-mono"> Current override: {model}</span> : null}
                </div>
              )}

              {configFields.length > 0 && (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
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
              )}
            </section>

            {showAdvanced && (
              <section className="border border-[#2c2f37] bg-[#141519] p-4">
                <h3 className="text-sm font-black uppercase tracking-wide text-white">Advanced Provider Settings</h3>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  {advancedFields.length ? (
                    advancedFields.map((field) => (
                      <ImageSetupField
                        key={field.id}
                        integration={providerIntegration}
                        field={field}
                        forms={forms}
                        onFieldChange={onFieldChange}
                      />
                    ))
                  ) : (
                    <p className="text-sm text-slate-500">No advanced settings for this provider.</p>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </article>
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
  const isModelField = field.id === "image_model" || field.id === "model";
  const modelOptions = uniqueModelOptions(modelOptionsForField(integration.id, field.id));
  const selectedImageModel = forms[integration.id]?.fields.image_model || integrationField(integration, "image_model")?.value || "";
  const settingOptions = uniqueModelOptions(settingOptionsForField(integration.id, field.id, selectedImageModel));
  const hasSettingOptions = settingOptions.length > 0;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label htmlFor={`image-setup-${integration.id}-${field.id}`} className="text-xs font-black uppercase tracking-wide text-white">
          {field.label}
        </label>
        {field.secret && <span className="border border-cyan-300/30 bg-cyan-300/10 px-2 py-0.5 text-[10px] font-black uppercase text-cyan-200">Secret</span>}
        {field.saved && <span className="border border-[#2c2f37] px-2 py-0.5 text-[10px] font-black uppercase text-slate-500">Saved</span>}
        {field.policy_blocked && (
          <span className="border border-rose-400/40 bg-rose-500/10 px-2 py-0.5 text-[10px] font-black uppercase text-rose-200">
            Not accepted in Cloud
          </span>
        )}
        {!field.policy_blocked && field.policy_conditional && (
          <span className="border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-black uppercase text-amber-200">
            Conditional
          </span>
        )}
      </div>

      {confirmationField ? (
        <label
          htmlFor={`image-setup-${integration.id}-${field.id}`}
          className="flex min-h-11 cursor-pointer items-start gap-3 border border-amber-400/35 bg-amber-500/10 px-3 py-3 text-sm leading-5 text-amber-100"
        >
          <input
            id={`image-setup-${integration.id}-${field.id}`}
            type="checkbox"
            checked={isTruthyFieldValue(fieldValue)}
            onChange={(event) => onFieldChange(integration.id, field.id, event.target.checked ? "confirmed" : "")}
            disabled={!field.editable}
            className="mt-0.5 h-4 w-4 shrink-0 accent-cyan-300"
          />
          <span>{confirmationLabel(integration, field)}</span>
        </label>
      ) : isModelField || hasSettingOptions ? (
        <ModelCombobox
          id={`image-setup-${integration.id}-${field.id}`}
          value={fieldValue}
          options={isModelField ? modelOptions : settingOptions}
          onChange={(value) => onFieldChange(integration.id, field.id, value)}
          placeholder={fieldPlaceholder(field)}
          disabled={!field.editable}
          suggestionType={isModelField ? "model" : "setting"}
        />
      ) : (
        <input
          id={`image-setup-${integration.id}-${field.id}`}
          type={field.secret ? "password" : "text"}
          value={fieldValue}
          onChange={(event) => onFieldChange(integration.id, field.id, event.target.value)}
          placeholder={fieldPlaceholder(field)}
          disabled={!field.editable}
          autoComplete="off"
          className="h-11 w-full border border-[#2c2f37] bg-black px-3 font-mono text-sm text-white outline-none placeholder:text-slate-700 focus:border-cyan-300 disabled:cursor-not-allowed disabled:border-rose-400/25 disabled:text-slate-600 disabled:placeholder:text-rose-200/50"
        />
      )}
      {field.help && <p className="mt-2 text-xs leading-5 text-slate-500">{field.help}</p>}
      {field.policy_notice && <p className="mt-2 text-xs leading-5 text-amber-200">{field.policy_notice}</p>}
    </div>
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
  const isModelField = ["model", "fallback_model", "llm_selector", "llm_model", "image_model"].includes(field.id);
  const modelOptions = uniqueModelOptions(modelOptionsForField(integration.id, field.id));
  const inputId = `${integration.id}-${field.id}`;

  return (
    <div className="border border-[#2c2f37] bg-[#141519] p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <label htmlFor={inputId} className="text-sm font-black uppercase tracking-wide text-white">
            {field.label}
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="border border-[#2c2f37] px-2 py-1 text-[10px] font-black uppercase text-slate-500">{sourceLabel(field)}</span>
            {isModelField && (
              <span className="border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[10px] font-black uppercase text-cyan-200">
                Type or choose
              </span>
            )}
            {field.secret && (
              <span className="border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[10px] font-black uppercase text-cyan-200">Secret</span>
            )}
            {field.policy_blocked && (
              <span className="border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase text-rose-200">
                Not accepted in Cloud
              </span>
            )}
            {!field.policy_blocked && field.policy_conditional && (
              <span className="border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase text-amber-200">Conditional</span>
            )}
          </div>
        </div>
        <p className="min-w-0 break-all font-mono text-[11px] leading-5 text-slate-500 md:text-right">{field.env_names.join(", ")}</p>
      </div>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        {confirmationField ? (
          <label
            htmlFor={inputId}
            className="flex min-h-11 flex-1 cursor-pointer items-start gap-3 border border-amber-400/35 bg-amber-500/10 px-3 py-3 text-sm leading-5 text-amber-100"
          >
            <input
              id={inputId}
              type="checkbox"
              checked={isTruthyFieldValue(value)}
              onChange={(event) => onChange(event.target.checked ? "confirmed" : "")}
              disabled={!field.editable}
              className="mt-0.5 h-4 w-4 shrink-0 accent-cyan-300"
            />
            <span>{confirmationLabel(integration, field)}</span>
          </label>
        ) : isModelField ? (
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
            className="h-11 min-w-0 flex-1 border border-[#2c2f37] bg-black px-3 font-mono text-sm text-white outline-none placeholder:text-slate-700 focus:border-cyan-300 disabled:cursor-not-allowed disabled:border-rose-400/25 disabled:text-slate-600 disabled:placeholder:text-rose-200/50"
          />
        )}
        {field.saved && (
          <button
            type="button"
            onClick={onClearSaved}
            disabled={saving}
            className="inline-flex h-11 items-center justify-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Clear saved
          </button>
        )}
      </div>
      {field.help && <p className="mt-2 text-xs leading-5 text-slate-500">{field.help}</p>}
      {isModelField && <p className="mt-2 text-xs leading-5 text-slate-500">Search the suggestions or enter any model ID supported by this provider.</p>}
      {field.policy_notice && <p className="mt-2 text-xs leading-5 text-amber-200">{field.policy_notice}</p>}
    </div>
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
    <section className="mt-4 border border-fuchsia-400/40 bg-[#17181d] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FlaskConical className="h-4 w-4 text-fuchsia-300" />
            <h2 className="text-sm font-black uppercase tracking-wide text-white">Test Image Model</h2>
            <span className="border border-fuchsia-400/35 bg-fuchsia-400/10 px-2 py-1 text-[10px] font-black uppercase text-fuchsia-200">
              Local / Preview only
            </span>
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            Makes one direct provider request. It does not run the main agent, create a project, or execute the image sequence.
          </p>
          <p className="mt-2 break-all font-mono text-[11px] text-cyan-200">
            {provider || "none"}/{model || "no model"}
          </p>
        </div>
        <div className="border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[11px] leading-5 text-amber-100">
          Uses saved settings and may incur one provider image-generation charge.
        </div>
      </div>

      <div className="mt-5 grid gap-3">
        <label htmlFor="image-model-test-prompt" className="text-xs font-black uppercase tracking-wide text-white">
          Test prompt
        </label>
        <textarea
          id="image-model-test-prompt"
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="A clean studio product render of a compact electronics enclosure..."
          className="w-full resize-y border border-[#2c2f37] bg-black px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-slate-700 focus:border-fuchsia-300"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[11px] text-slate-500">Save provider/model changes above before testing.</span>
          <button
            type="button"
            onClick={onRun}
            disabled={running || !prompt.trim() || provider === "none" || !model}
            className="inline-flex h-11 items-center gap-2 bg-fuchsia-300 px-4 text-xs font-black uppercase tracking-widest text-black hover:bg-fuchsia-200 disabled:cursor-wait disabled:opacity-50"
          >
            <FlaskConical className={`h-4 w-4 ${running ? "animate-pulse" : ""}`} />
            {running ? "Testing model..." : "Generate one test image"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-5 border border-rose-500/40 bg-rose-950/30 p-4 text-sm leading-6 text-rose-200">
          <div className="flex items-center gap-2 font-black uppercase tracking-wide">
            <AlertTriangle className="h-4 w-4" />
            Test failed
          </div>
          <p className="mt-2 break-words">{error}</p>
        </div>
      )}

      {result && (
        <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="flex min-h-72 items-center justify-center border border-[#2c2f37] bg-black p-3">
            {/* Provider results can be data URLs or short-lived remote URLs, so Next image optimization is not appropriate here. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={result.image_data_url} alt="Direct image model test result" className="max-h-[640px] w-full object-contain" />
          </div>
          <div className="grid content-start gap-3">
            <div className="border border-emerald-400/35 bg-emerald-400/10 p-3 text-emerald-100">
              <div className="text-[10px] font-black uppercase tracking-widest">Request succeeded</div>
              <div className="mt-2 font-mono text-sm">{result.elapsed_ms.toLocaleString()} ms</div>
            </div>
            <div className="border border-[#2c2f37] p-3 text-xs leading-5 text-slate-400">
              <div><span className="text-slate-600">Provider:</span> {result.provider}</div>
              <div><span className="text-slate-600">Model:</span> {result.model}</div>
              <div><span className="text-slate-600">Size:</span> {result.size || "Provider default"}</div>
              <div><span className="text-slate-600">Format:</span> {result.output_format}</div>
            </div>
          </div>
        </div>
      )}

      {diagnostics != null && (
        <details className="mt-4 border border-[#2c2f37] bg-black">
          <summary className="cursor-pointer px-3 py-3 text-xs font-black uppercase tracking-widest text-slate-400">
            Raw diagnostics
          </summary>
          <pre className="max-h-96 overflow-auto border-t border-[#2c2f37] p-3 text-[11px] leading-5 text-slate-400">
            {JSON.stringify(diagnostics, null, 2)}
          </pre>
        </details>
      )}
    </section>
  );
}

export default function UserIntegrationsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [payload, setPayload] = useState<IntegrationsPayload | null>(null);
  const [forms, setForms] = useState<Record<string, IntegrationFormState>>({});
  const [selectedNavigationKey, setSelectedNavigationKey] = useState("runtime:all");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showImageAdvanced, setShowImageAdvanced] = useState(false);
  const [imageTestPrompt, setImageTestPrompt] = useState(
    "A clean studio product render of a compact matte-black electronics enclosure, three-quarter view, neutral background, realistic materials."
  );
  const [imageTestRunning, setImageTestRunning] = useState(false);
  const [imageTestResult, setImageTestResult] = useState<ImageModelTestResult | null>(null);
  const [imageTestError, setImageTestError] = useState<string | null>(null);
  const [imageTestErrorDetails, setImageTestErrorDetails] = useState<unknown>(null);

  const navigationGroups = useMemo(
    () => integrationNavigationGroups(payload?.integrations || []),
    [payload]
  );

  const selectedNavigationItem = useMemo(
    () => navigationGroups.flatMap((group) => group.items).find((item) => item.key === selectedNavigationKey) || null,
    [navigationGroups, selectedNavigationKey]
  );

  const selectedIntegration = selectedNavigationItem?.integration || payload?.integrations[0] || null;
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

  useEffect(() => {
    setImageTestResult(null);
    setImageTestError(null);
    setImageTestErrorDetails(null);
  }, [imageDefaults.provider, imageDefaults.model]);

  const optionalAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!isSignedIn) return {};
    try {
      const token = await getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, [getToken, isSignedIn]);

  const loadIntegrations = useCallback(async () => {
    if (!isLoaded) return;
    if (!isSignedIn) {
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
      const availableNavigationItems = integrationNavigationGroups(data.integrations).flatMap((group) => group.items);
      setSelectedNavigationKey((current) =>
        availableNavigationItems.some((item) => item.key === current) ? current : availableNavigationItems[0]?.key || "runtime:all"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  }, [isLoaded, isSignedIn, optionalAuthHeaders]);

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
    if (!isSignedIn) return;
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
    if (!isSignedIn) return;
    const form = forms[integration.id] || formFromIntegration(integration);
    const fields: Record<string, string> = {};
    const clearFieldSet = new Set(clearFields);
    integration.fields.forEach((field) => {
      if (!field.editable) return;
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
    if (!isSignedIn) return;
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
    if (!isSignedIn) return;
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

  async function runImageModelTest() {
    if (!isSignedIn || !imageTestPrompt.trim()) return;
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
                <h1 className="truncate text-lg font-black uppercase tracking-wide text-white">Settings</h1>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                API keys, preferred models, and provider defaults for your Forma workspace.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={reloadRuntime}
            disabled={loading || !isLoaded || !isSignedIn}
            className="inline-flex h-11 shrink-0 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-wait disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Reload
          </button>
        </div>
      </header>

      {!isLoaded ? (
        <section className="mx-auto w-full max-w-7xl px-4 py-5">
          <div className="border border-[#2c2f37] bg-[#17181d] p-6 text-sm text-slate-500">Checking session...</div>
        </section>
      ) : !isSignedIn ? (
        <section className="mx-auto w-full max-w-7xl px-4 py-5">
          <div className="max-w-xl border border-[#2c2f37] bg-[#17181d] p-6">
            <div className="inline-flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
              <KeyRound className="h-4 w-4 text-cyan-300" />
              Sign in required
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Settings store API keys and provider defaults for your account. Sign in to manage your models.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <SignInButton mode="modal">
                <button
                  type="button"
                  className="inline-flex h-11 items-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-widest text-black hover:bg-slate-200"
                >
                  <KeyRound className="h-4 w-4" />
                  Sign in
                </button>
              </SignInButton>
              <Link
                href="/"
                className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-4 text-xs font-black uppercase tracking-widest text-slate-300 hover:bg-white hover:text-black"
              >
                <ArrowLeft className="h-4 w-4" />
                Home
              </Link>
            </div>
          </div>
        </section>
      ) : (
        <section className="mx-auto grid w-full max-w-7xl gap-5 px-4 py-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="min-h-0 border border-[#2c2f37] bg-[#17181d]">
          <div className="border-b border-[#2c2f37] p-4">
            <div className="inline-flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
              <KeyRound className="h-4 w-4 text-cyan-300" />
              Provider & Model Settings
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-500">Language models, image generation, and tools are separated by purpose.</p>
          </div>

          <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-3">
            {loading && !payload ? (
              <div className="border border-[#2c2f37] p-4 text-sm text-slate-500">Loading integrations...</div>
            ) : (
              navigationGroups.map((group) => (
                <section key={group.id} className="mb-5 last:mb-0">
                  <div className="mb-2 flex items-center gap-2 px-1">
                    <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">{group.label}</span>
                    <span className="h-px flex-1 bg-[#2c2f37]" />
                  </div>
                  {group.items.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => {
                        if (item.imageProviderId) updateImageProvider(item.imageProviderId);
                        else setSelectedNavigationKey(item.key);
                      }}
                      className={`mb-2 block w-full border p-3 text-left transition ${
                        selectedNavigationKey === item.key
                          ? "border-cyan-300 bg-cyan-300/10"
                          : "border-[#2c2f37] bg-[#141519] hover:border-slate-500"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-black uppercase tracking-wide text-white">{item.label}</span>
                        <span
                          className={`shrink-0 border px-2 py-1 text-[10px] font-black uppercase ${
                            item.integration.configured
                              ? item.integration.enabled
                                ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                                : "border-amber-400/40 bg-amber-500/10 text-amber-300"
                              : "border-[#2c2f37] text-slate-500"
                          }`}
                        >
                          {item.integration.configured ? (item.integration.enabled ? "Ready" : "Off") : "Unset"}
                        </span>
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <p className="line-clamp-1 min-w-0 text-xs text-slate-500">{navigationDescription(item)}</p>
                        <span className="shrink-0 text-[9px] font-black uppercase tracking-wider text-cyan-300/70">
                          {item.view === "llm" ? "LLM" : item.view === "image" ? "Image" : item.integration.id === "firecrawl" ? "Search" : "Defaults"}
                        </span>
                      </div>
                    </button>
                  ))}
                </section>
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

          {payload && selectedView === "image" && (
            <section className="mb-4 border border-cyan-300/40 bg-[#17181d] p-5">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                <div className="min-w-0">
                  <div className="inline-flex items-center gap-2 text-sm font-black uppercase tracking-wide text-white">
                    <KeyRound className="h-4 w-4 text-cyan-300" />
                    Image Provider
                  </div>
                  <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500">
                    Pick the provider used for generated product images. Required setup appears below.
                  </p>
                </div>

                <div className="grid w-full gap-3 md:grid-cols-[minmax(180px,280px)] xl:max-w-xs">
                  <label className="min-w-0">
                    <span className="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-500">Provider</span>
                    <select
                      value={imageDefaults.provider}
                      onChange={(event) => updateImageProvider(event.target.value)}
                      className="h-11 w-full border border-[#2c2f37] bg-black px-3 text-sm font-black uppercase tracking-wide text-white outline-none focus:border-cyan-300"
                    >
                      {IMAGE_PROVIDER_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            </section>
          )}

          {payload && selectedIntegration && selectedView === "image" ? (
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
                showAdvanced={showImageAdvanced}
                onProviderChange={updateImageProvider}
                onModelChange={updateImageModel}
                onFieldChange={updateField}
                onEnabledChange={updateEnabled}
                onSave={saveImageDefaults}
                onClear={clearIntegration}
                onToggleAdvanced={() => setShowImageAdvanced((current) => !current)}
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
            <article className="border border-[#2c2f37] bg-[#17181d]">
              <div className="flex flex-col gap-4 border-b border-[#2c2f37] p-5 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-black uppercase tracking-wide text-white">{selectedNavigationItem?.label || selectedIntegration.label}</h2>
                    {selectedView === "llm" && (
                      <span className="border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[10px] font-black uppercase text-cyan-200">LLM only</span>
                    )}
                    <span
                      className={`border px-2 py-1 text-[10px] font-black uppercase ${
                        selectedIntegration.configured
                          ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                          : "border-[#2c2f37] text-slate-500"
                      }`}
                    >
                      {selectedIntegration.configured ? "Configured" : "Not configured"}
                    </span>
                    {selectedIntegration.policy_status && selectedIntegration.policy_status !== "enabled" && (
                      <span className="border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase text-amber-300">
                        BYOK {selectedIntegration.policy_status}
                      </span>
                    )}
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{navigationDescription(selectedNavigationItem)}</p>
                  {selectedIntegration.policy_notice && (
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-200">{selectedIntegration.policy_notice}</p>
                  )}
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

              <div className="grid gap-5 p-5">
                {integrationFieldGroups(selectedIntegration, selectedView).map((group) => (
                  <section key={group.id} className="border border-[#2c2f37] bg-[#101115] p-4">
                    <div className="mb-4 border-b border-[#2c2f37] pb-4">
                      <h3 className="text-sm font-black uppercase tracking-wide text-white">{group.label}</h3>
                      <p className="mt-2 text-xs leading-5 text-slate-500">{group.description}</p>
                    </div>
                    <div className="grid gap-4">
                      {group.fields.map((field) => (
                        <IntegrationFieldEditor
                          key={field.id}
                          integration={selectedIntegration}
                          field={field}
                          value={forms[selectedIntegration.id]?.fields[field.id] || ""}
                          saving={savingId === selectedIntegration.id}
                          onChange={(value) => updateField(selectedIntegration.id, field.id, value)}
                          onClearSaved={() => saveIntegration(selectedIntegration, [field.id])}
                        />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </article>
          ) : (
            <div className="border border-[#2c2f37] bg-[#17181d] p-6 text-slate-500">No integrations found.</div>
          )}
        </section>
        </section>
      )}
    </main>
  );
}
