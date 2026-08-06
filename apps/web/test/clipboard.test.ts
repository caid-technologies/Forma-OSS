import assert from "node:assert/strict";
import { test } from "node:test";

import { copyTextToClipboard, type CopyEnvironment } from "../lib/clipboard";

function recordingEnvironment(overrides: Partial<CopyEnvironment> = {}) {
  const writes: string[] = [];
  const legacyWrites: string[] = [];

  const environment: CopyEnvironment = {
    clipboard: {
      async writeText(text: string) {
        writes.push(text);
      },
    },
    isSecureContext: true,
    legacyCopy: (text: string) => {
      legacyWrites.push(text);
      return true;
    },
    ...overrides,
  };

  return { environment, writes, legacyWrites };
}

test("the async clipboard API is used when it is available in a secure context", async () => {
  const { environment, writes, legacyWrites } = recordingEnvironment();

  assert.equal(await copyTextToClipboard("Forma build steps", environment), true);
  assert.deepEqual(writes, ["Forma build steps"]);
  assert.deepEqual(legacyWrites, []);
});

test("a rejected clipboard write falls back to the legacy copy command", async () => {
  const { environment, legacyWrites } = recordingEnvironment({
    clipboard: {
      writeText: async () => {
        throw new Error("NotAllowedError");
      },
    },
  });

  assert.equal(await copyTextToClipboard("Wiring notes", environment), true);
  assert.deepEqual(legacyWrites, ["Wiring notes"]);
});

test("a non-secure context skips the async clipboard API entirely", async () => {
  const { environment, writes, legacyWrites } = recordingEnvironment({ isSecureContext: false });

  assert.equal(await copyTextToClipboard("Bill of materials", environment), true);
  assert.deepEqual(writes, []);
  assert.deepEqual(legacyWrites, ["Bill of materials"]);
});

test("a failing legacy copy is reported as a failure instead of a silent success", async () => {
  const { environment } = recordingEnvironment({
    clipboard: null,
    legacyCopy: () => false,
  });

  assert.equal(await copyTextToClipboard("Bill of materials", environment), false);
});

test("a throwing legacy copy is reported as a failure", async () => {
  const { environment } = recordingEnvironment({
    clipboard: null,
    legacyCopy: () => {
      throw new Error("execCommand is not supported");
    },
  });

  assert.equal(await copyTextToClipboard("Bill of materials", environment), false);
});

test("an environment with no copy capability reports failure", async () => {
  assert.equal(await copyTextToClipboard("Bill of materials", {}), false);
});

test("empty text is never written to the clipboard", async () => {
  const { environment, writes, legacyWrites } = recordingEnvironment();

  assert.equal(await copyTextToClipboard("", environment), false);
  assert.deepEqual(writes, []);
  assert.deepEqual(legacyWrites, []);
});
