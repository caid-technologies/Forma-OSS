import assert from "node:assert/strict";
import { test } from "node:test";

import { normalizeContextSuggestions } from "../lib/context-suggestions";

test("context suggestions are trimmed, deduplicated, and bounded", () => {
  assert.deepEqual(
    normalizeContextSuggestions([" 3-season ", "3-SEASON", "4-season", "Rain", "Wind", "Snow"]),
    ["3-season", "4-season", "Rain", "Wind"],
  );
});

test("artificial free-text choices are not displayed", () => {
  assert.deepEqual(
    normalizeContextSuggestions(["Custom", "Other", "Something else", "None of these", "Battery powered"]),
    ["Battery powered"],
  );
});
