export type SettingsNavView = "all" | "llm" | "image";
export type SettingsNavTone = "ready" | "warn" | "muted";
export type SettingsNavBadge = {
  tone: SettingsNavTone;
  label: "Ready" | "Off" | "Unset";
};

const LLM_PROVIDER_ALIASES: Record<string, string> = {
  claude: "anthropic",
  "anthropic-claude": "anthropic",
  hf: "huggingface",
  "hugging-face": "huggingface",
  google: "gemini",
  "google-vertex": "vertex",
  "google-vertex-ai": "vertex",
  "vertex-ai": "vertex",
  vertexai: "vertex",
};

function normalizeProviderId(value: string) {
  const normalized = value.trim().toLowerCase().replaceAll("_", "-");
  return LLM_PROVIDER_ALIASES[normalized] || normalized;
}

export function parsePreferredLlmProvider(selector: string, providerOverride = "") {
  const override = normalizeProviderId(providerOverride);
  if (override) return override;

  const raw = selector.trim();
  if (!raw) return "";
  if (raw.includes("/")) {
    return normalizeProviderId(raw.slice(0, raw.indexOf("/")));
  }
  if (raw.toLowerCase().startsWith("claude-")) return "anthropic";
  if (/^(gpt-|o1|o3|o4|text-)/i.test(raw)) return "openai";
  return normalizeProviderId(raw);
}

export function imageOutputIsEnabled(enabledValue: string, provider = "") {
  const normalized = enabledValue.trim().toLowerCase();
  if (["0", "false", "no", "n", "off"].includes(normalized)) return false;
  if (["1", "true", "yes", "y", "on"].includes(normalized)) return true;
  return Boolean(provider) && provider !== "none";
}

export function settingsNavBadge(input: {
  view: SettingsNavView;
  integrationId: string;
  imageProviderId?: string;
  configured: boolean;
  enabled: boolean;
  defaultLlmProvider?: string;
  imageOutputEnabled?: boolean;
  activeImageProvider?: string;
}): SettingsNavBadge {
  if (input.view === "llm") {
    const isDefault = Boolean(input.defaultLlmProvider) && input.integrationId === input.defaultLlmProvider;
    if (isDefault && input.configured && input.enabled) return { tone: "ready", label: "Ready" };
    if (input.configured) return { tone: "warn", label: "Off" };
    return { tone: "muted", label: "Unset" };
  }

  if (input.view === "image") {
    const activeProvider = input.activeImageProvider || "none";
    const matchesCustomImage = !input.imageProviderId && input.integrationId === "image" && (
      activeProvider === "openai-compatible" || activeProvider === "image"
    );
    const matchesNamedImage = Boolean(input.imageProviderId) && input.imageProviderId === activeProvider;
    const isActive = Boolean(input.imageOutputEnabled) && activeProvider !== "none" && (matchesNamedImage || matchesCustomImage);
    if (isActive && input.configured && input.enabled) return { tone: "ready", label: "Ready" };
    if (input.configured) return { tone: "warn", label: "Off" };
    return { tone: "muted", label: "Unset" };
  }

  if (input.configured && input.enabled) return { tone: "ready", label: "Ready" };
  if (input.configured) return { tone: "warn", label: "Off" };
  return { tone: "muted", label: "Unset" };
}
