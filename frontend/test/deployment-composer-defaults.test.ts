import assert from "node:assert/strict";
import { test } from "node:test";

import { deploymentComposerDefaults } from "../lib/deployment-composer-defaults";

const workflows = [{ id: "default" }, { id: "web_research" }];

test("deployment defaults enable web research and configured image generation", () => {
  assert.deepEqual(
    deploymentComposerDefaults({
      blueprintDevMode: false,
      imageProviderConfigured: true,
      workflows,
    }),
    {
      generateImages: true,
      workflowId: "web_research",
    },
  );
});

test("development mode leaves deployment-only generation defaults off", () => {
  assert.deepEqual(
    deploymentComposerDefaults({
      blueprintDevMode: true,
      imageProviderConfigured: true,
      workflows,
    }),
    {
      generateImages: false,
      workflowId: null,
    },
  );
});

test("deployment defaults require the matching configured capability", () => {
  assert.deepEqual(
    deploymentComposerDefaults({
      blueprintDevMode: false,
      imageProviderConfigured: false,
      workflows: [{ id: "default" }],
    }),
    {
      generateImages: false,
      workflowId: null,
    },
  );
});
