import assert from "node:assert/strict";
import { test } from "node:test";

import { connectionStatusPresentation } from "../lib/connection-status";

test("connected status uses a green dot and accessible label", () => {
  const presentation = connectionStatusPresentation("connected");

  assert.equal(presentation.label, "Connected");
  assert.match(presentation.dotClassName, /emerald/);
});

test("disconnected status uses an orange warning dot and accessible label", () => {
  const presentation = connectionStatusPresentation("disconnected");

  assert.equal(presentation.label, "Disconnected");
  assert.match(presentation.dotClassName, /orange/);
});
