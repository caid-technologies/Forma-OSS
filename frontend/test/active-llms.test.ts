import assert from "node:assert/strict";
import { test } from "node:test";

import { activeLlmsFromIntegrations, type GenerationLlmOption, type IntegrationsPayload } from "../lib/active-llms";

const defaults: GenerationLlmOption[] = [
  { provider: "openai", model: "gpt-5.5", label: "OpenAI GPT-5.5" },
  { provider: "anthropic", model: "claude-sonnet-5", label: "Claude Sonnet 5" },
  { provider: "huggingface", model: "Qwen/Qwen2.5-Coder-3B-Instruct:nscale", label: "Hugging Face Qwen2.5 Coder" },
  { provider: "baseten", model: "zai-org/GLM-5.2", label: "GLM 5.2" },
  { provider: "nvidia", model: "nvidia/z-ai/glm-5.2", label: "NVIDIA GLM 5.2" },
];

function label(provider: string, model: string) {
  const known = defaults.find((option) => option.provider === provider && option.model === model);
  return known?.label || `${provider} ${model}`;
}

test("only enabled and configured providers appear in the generation LLM list", () => {
  const payload: IntegrationsPayload = {
    integrations: [
      {
        id: "runtime",
        enabled: false,
        configured: true,
        fields: [{ id: "llm_selector", value: "openai/gpt-5.5", configured: true }],
      },
      {
        id: "openai",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "gpt-5.5", configured: true }],
      },
      {
        id: "anthropic",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "claude-sonnet-5", configured: true }],
      },
      {
        id: "huggingface",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "Qwen/Qwen2.5-Coder-3B-Instruct:nscale", configured: true }],
      },
      {
        id: "baseten",
        enabled: true,
        configured: true,
        fields: [{ id: "model", value: "deepseek-ai/DeepSeek-V4-Pro", configured: true }],
      },
      {
        id: "nvidia",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "nvidia/z-ai/glm-5.2", configured: true }],
      },
    ],
  };

  assert.deepEqual(activeLlmsFromIntegrations(payload, defaults, label), [
    {
      provider: "baseten",
      model: "deepseek-ai/DeepSeek-V4-Pro",
      label: "baseten deepseek-ai/DeepSeek-V4-Pro",
    },
  ]);
});

test("no static fallback models appear when every provider is off", () => {
  const payload: IntegrationsPayload = {
    integrations: [
      {
        id: "openai",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "gpt-5.5", configured: true }],
      },
      {
        id: "baseten",
        enabled: false,
        configured: true,
        fields: [{ id: "model", value: "deepseek-ai/DeepSeek-V4-Pro", configured: true }],
      },
    ],
  };

  assert.deepEqual(activeLlmsFromIntegrations(payload, defaults, label), []);
});
