import assert from "node:assert/strict";
import { test } from "node:test";

import { generationLlmImageSupport } from "../lib/active-llms";
import { usableRuntimeLlmOptions, type RuntimeConfigContract } from "../lib/config";

function contract(): RuntimeConfigContract {
  return {
    contract_version: 1,
    authority: "backend",
    blueprint_dev_mode: true,
    generation: {
      ready: true,
      available: true,
      reason: null,
      selected_llm: {
        provider: "cloudflare",
        model: "@cf/google/gemma-4-26b-a4b-it",
        label: "Cloudflare Gemma 4 26B A4B",
        selected: true,
        configured: true,
        supports_image_input: true,
      },
      llm_options: [
        {
          provider: "cloudflare",
          model: "@cf/google/gemma-4-26b-a4b-it",
          label: "Cloudflare Gemma 4 26B A4B",
          selected: true,
          configured: true,
          supports_image_input: true,
        },
        {
          provider: "openai",
          model: "gpt-disabled",
          label: "OpenAI disabled",
          configured: false,
        },
      ],
    },
    images: {
      enabled: true,
      configured: true,
      request_capable: true,
      provider: "gmi",
      model: "gpt-image-2",
      generate_by_default: true,
      reason: null,
    },
    workflow: { default_id: "default", options: [] },
    provider_setup: { required: false, llm_required: false, image_required: false },
  };
}

test("workspace consumes only configured LLM options from the backend contract", () => {
  assert.deepEqual(usableRuntimeLlmOptions(contract()), [contract().generation.llm_options[0]]);
});

test("fallback image support classification remains available for legacy records", () => {
  assert.equal(generationLlmImageSupport({ provider: "cloudflare", model: "@cf/google/gemma-4-26b-a4b-it" }), true);
  assert.equal(generationLlmImageSupport({ provider: "cloudflare", model: "nvidia/nemotron-3-super-120b-a12b" }), false);
  assert.equal(generationLlmImageSupport({ provider: "cloudflare", model: "some-new-model" }), null);
});
