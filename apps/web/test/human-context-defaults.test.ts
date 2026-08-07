import assert from "node:assert/strict";
import { test } from "node:test";

import {
  humanContextSkipChatSummary,
  humanContextSkipPromptSection,
} from "../lib/human-context-defaults";

const electronicsQuestions = [
  { id: "controller_modules", label: "Controller / Modules", question: "Which controller should coordinate the system?" },
  { id: "power", label: "Power", question: "How should the product be powered?" },
  { id: "outputs", label: "Outputs", question: "Which outputs are required?" },
];

test("skipped questions remain dynamic instead of receiving fixed design values", () => {
  const prompt = humanContextSkipPromptSection("Build an Arduino button panel", electronicsQuestions);

  assert.match(prompt, /explicitly skipped/i);
  assert.match(prompt, /How should the product be powered\?/);
  assert.match(prompt, /infer missing details from the full project context/i);
  assert.match(prompt, /record every inferred choice as an assumption/i);
  assert.doesNotMatch(prompt, /USB-C 5 V|indoor bench|Arduino Uno/);
});

test("the chat summary reports the skip without claiming fixed defaults", () => {
  const summary = humanContextSkipChatSummary(electronicsQuestions, "Use the uploaded reference.");

  assert.match(summary, /^Skipped optional clarification questions/);
  assert.match(summary, /- Power: skipped/);
  assert.match(summary, /- Additional notes: Use the uploaded reference\./);
  assert.doesNotMatch(summary, /defaults|USB-C 5 V/);
});
