import assert from "node:assert/strict";
import { test } from "node:test";

import {
  imageOutputIsEnabled,
  parsePreferredLlmProvider,
  settingsNavBadge,
} from "../lib/settings-nav-status.ts";

test("parsePreferredLlmProvider reads anthropic from a Claude selector", () => {
  assert.equal(parsePreferredLlmProvider("anthropic/claude-opus-5"), "anthropic");
  assert.equal(parsePreferredLlmProvider("claude-opus-5"), "anthropic");
  assert.equal(parsePreferredLlmProvider("", "anthropic"), "anthropic");
});

test("image output stays off when IMAGE_OUTPUT_ENABLED is false", () => {
  assert.equal(imageOutputIsEnabled("false", "openai"), false);
  assert.equal(imageOutputIsEnabled("", "none"), false);
  assert.equal(imageOutputIsEnabled("true", "openai"), true);
});

test("only the default LLM provider is Ready", () => {
  assert.deepEqual(settingsNavBadge({
    view: "llm",
    integrationId: "anthropic",
    configured: true,
    enabled: true,
    defaultLlmProvider: "anthropic",
  }), { tone: "ready", label: "Ready" });
  assert.deepEqual(settingsNavBadge({
    view: "llm",
    integrationId: "openai",
    configured: true,
    enabled: true,
    defaultLlmProvider: "anthropic",
  }), { tone: "warn", label: "Off" });
  assert.deepEqual(settingsNavBadge({
    view: "llm",
    integrationId: "openai",
    configured: false,
    enabled: true,
    defaultLlmProvider: "anthropic",
  }), { tone: "muted", label: "Unset" });
});

test("custom image output is Unset unless it is the active image provider", () => {
  assert.deepEqual(settingsNavBadge({
    view: "image",
    integrationId: "image",
    configured: false,
    enabled: true,
    imageOutputEnabled: false,
    activeImageProvider: "openai",
  }), { tone: "muted", label: "Unset" });
  assert.deepEqual(settingsNavBadge({
    view: "image",
    integrationId: "openai",
    imageProviderId: "openai",
    configured: false,
    enabled: true,
    imageOutputEnabled: false,
    activeImageProvider: "openai",
  }), { tone: "muted", label: "Unset" });
});
