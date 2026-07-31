export type HumanContextQuestionForDefaults = {
  id: string;
  label: string;
};

const DEFAULT_ANSWERS: Record<string, string> = {
  sample_assay: "Use a non-hazardous, research-only demonstration sample; keep the exact assay as an explicit open choice.",
  instrumentation: "Use the simplest non-hazardous detection method compatible with the requested function.",
  validation: "Start with bench safety, core-function, and repeatability checks, plus leak testing when fluids are involved.",
  environment: "Assume an indoor bench prototype unless the request explicitly names another environment.",
  motion_power: "Use low-voltage, low-force actuation with a manual release and no mains voltage.",
  success: "Safely demonstrate the requested core function and document any missing quantitative targets as open choices.",
  controller_modules: "Choose common, compatible, readily available modules that minimize wiring and integration risk.",
  power: "Use a safe low-voltage USB-C 5 V supply and no mains voltage unless the request requires another source.",
  outputs: "Implement only requested outputs; otherwise include a simple status indicator for the core function.",
  use_case: "Treat version one as an indoor bench prototype for technical evaluation.",
  constraints: "Prefer safe low-voltage operation, readily available components, and a cost-conscious build.",
  artifacts: "Prioritize buildability, clear wiring or materials, a BOM, assembly steps, and basic validation.",
};

export function humanContextDefaultAnswer(question: HumanContextQuestionForDefaults) {
  if (question.label.trim().toLowerCase() === "artifacts") {
    return DEFAULT_ANSWERS.artifacts;
  }
  return (
    DEFAULT_ANSWERS[question.id] ||
    `Use Forma's conservative prototype default for ${question.label.toLowerCase()} and document the choice.`
  );
}

export function humanContextDefaultsPromptSection(
  basePrompt: string,
  questions: HumanContextQuestionForDefaults[],
  finalNotes = "",
) {
  const contextLines = questions.map(
    (question) => `- ${question.label}: ${humanContextDefaultAnswer(question)}`,
  );
  if (finalNotes.trim()) {
    contextLines.push(`- Additional human notes: ${finalNotes.trim()}`);
  }
  return [
    basePrompt,
    "",
    "HUMAN-IN-THE-LOOP CONTEXT:",
    "- The user skipped optional clarification and asked Forma to apply these defaults:",
    ...contextLines,
    "",
    "The original request takes precedence over these defaults. Keep any safety-critical uncertainty explicit in the project docs instead of inventing hidden constraints.",
  ].join("\n");
}

export function humanContextDefaultsChatSummary(
  questions: HumanContextQuestionForDefaults[],
  finalNotes = "",
) {
  const lines = [
    "Skipped questions and used Forma defaults:",
    ...questions.map((question) => `- ${question.label}: ${humanContextDefaultAnswer(question)}`),
  ];
  if (finalNotes.trim()) {
    lines.push(`- Additional notes: ${finalNotes.trim()}`);
  }
  return lines.join("\n");
}
