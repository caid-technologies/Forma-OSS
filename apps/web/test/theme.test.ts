import assert from "node:assert/strict";
import { test } from "node:test";

import { normalizeTheme, THEME_STORAGE_KEY } from "../lib/theme";

test("theme preferences use a stable local storage key", () => {
  assert.equal(THEME_STORAGE_KEY, "forma-theme");
});

test("theme preferences accept light and default every other value to dark", () => {
  assert.equal(normalizeTheme("light"), "light");
  assert.equal(normalizeTheme("dark"), "dark");
  assert.equal(normalizeTheme(null), "dark");
  assert.equal(normalizeTheme("system"), "dark");
});
