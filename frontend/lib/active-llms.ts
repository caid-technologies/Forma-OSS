export type GenerationLlmOption = {
  provider: string;
  model: string;
  label: string;
};

export type IntegrationFieldStatus = {
  id: string;
  value: string | null;
  configured: boolean;
};

export type IntegrationStatus = {
  id: string;
  enabled: boolean;
  configured: boolean;
  environment_configured?: boolean;
  available?: boolean;
  fields: IntegrationFieldStatus[];
};

export type IntegrationsPayload = {
  integrations?: IntegrationStatus[];
};

const LLM_PROVIDER_IDS = new Set([
  "anthropic",
  "baseten",
  "gemini",
  "gmi",
  "huggingface",
  "nebius",
  "nvidia",
  "openai",
  "openai-compatible",
  "runpod",
  "runpod-serverless",
]);

export function generationLlmKey(option: Pick<GenerationLlmOption, "provider" | "model">) {
  return `${option.provider}/${option.model}`;
}

function integrationFieldValue(integration: IntegrationStatus | undefined, fieldId: string) {
  const field = integration?.fields.find((item) => item.id === fieldId);
  return typeof field?.value === "string" && field.value.trim() ? field.value.trim() : null;
}

function parseLlmSelector(value: string | null) {
  if (!value) return null;
  const separator = value.indexOf("/");
  if (separator <= 0 || separator >= value.length - 1) return null;
  return {
    provider: value.slice(0, separator).trim(),
    model: value.slice(separator + 1).trim(),
  };
}

function parseProviderAllowlist(value: string | null) {
  if (!value) return null;
  const providers = value
    .split(",")
    .map((provider) => provider.trim().toLowerCase())
    .filter(Boolean);
  return providers.length ? new Set(providers) : null;
}

function firstDefaultModelForProvider(defaultLlms: GenerationLlmOption[], provider: string) {
  return defaultLlms.find((option) => option.provider === provider)?.model || "";
}

function uniqueGenerationLlms(options: GenerationLlmOption[]) {
  const seen = new Set<string>();
  return options.filter((option) => {
    const key = generationLlmKey(option);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function integrationIsAvailable(integration: IntegrationStatus | undefined) {
  if (!integration) return false;
  if (typeof integration.available === "boolean") return integration.available;
  return Boolean(integration.environment_configured || (integration.enabled && integration.configured));
}

export function activeLlmsFromIntegrations(
  payload: IntegrationsPayload | null | undefined,
  defaultLlms: GenerationLlmOption[],
  labelFor: (provider: string, model: string) => string,
) {
  const integrations = Array.isArray(payload?.integrations) ? payload.integrations : [];
  const byId = new Map(integrations.map((integration) => [integration.id, integration]));
  const options: GenerationLlmOption[] = [];
  const runtime = byId.get("runtime");
  const allowedProviders = parseProviderAllowlist(integrationFieldValue(runtime, "allowed_providers"));
  const providerIsAllowed = (provider: string) => !allowedProviders || allowedProviders.has(provider.toLowerCase());
  const preferred = parseLlmSelector(integrationFieldValue(runtime, "llm_selector"));
  if (preferred && providerIsAllowed(preferred.provider)) {
    const providerIntegration = byId.get(preferred.provider);
    if (integrationIsAvailable(providerIntegration)) {
      options.push({
        provider: preferred.provider,
        model: preferred.model,
        label: labelFor(preferred.provider, preferred.model),
      });
    }
  }

  integrations.forEach((integration) => {
    if (!LLM_PROVIDER_IDS.has(integration.id) || !providerIsAllowed(integration.id) || !integrationIsAvailable(integration)) return;
    const model = integrationFieldValue(integration, "model") || firstDefaultModelForProvider(defaultLlms, integration.id);
    if (!model) return;
    options.push({
      provider: integration.id,
      model,
      label: labelFor(integration.id, model),
    });
  });

  return uniqueGenerationLlms(options);
}
