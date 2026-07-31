import assert from "node:assert/strict";
import { test } from "node:test";

import {
  humanContextDefaultAnswer,
  humanContextDefaultsChatSummary,
  humanContextDefaultsPromptSection,
} from "../lib/human-context-defaults";

const electronicsQuestions = [
  { id: "controller_modules", label: "Controller / Modules" },
  { id: "power", label: "Power" },
  { id: "outputs", label: "Outputs" },
];

test("skipped electronics questions get deterministic safe defaults", () => {
  const prompt = humanContextDefaultsPromptSection("Build an Arduino button panel", electronicsQuestions);

  assert.match(prompt, /common, compatible, readily available modules/);
  assert.match(prompt, /USB-C 5 V/);
  assert.match(prompt, /simple status indicator/);
  assert.match(prompt, /original request takes precedence/i);
  assert.doesNotMatch(prompt, /not specified/);
});

test("unknown clarifier questions receive a documented conservative default", () => {
  assert.equal(
    humanContextDefaultAnswer({ id: "custom", label: "Mounting" }),
    "Use Forma's conservative prototype default for mounting and document the choice.",
  );
});

test("the reused outputs id still gets an artifact default when labeled Artifacts", () => {
  assert.match(
    humanContextDefaultAnswer({ id: "outputs", label: "Artifacts" }),
    /buildability, clear wiring or materials/,
  );
});

test("the chat summary makes applied defaults visible to the user", () => {
  const summary = humanContextDefaultsChatSummary(electronicsQuestions, "Use an Arduino Uno.");

  assert.match(summary, /^Skipped questions and used Forma defaults:/);
  assert.match(summary, /- Power: Use a safe low-voltage USB-C 5 V supply/);
  assert.match(summary, /- Additional notes: Use an Arduino Uno\./);
});
