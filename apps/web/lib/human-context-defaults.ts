export type HumanContextQuestionForDefaults = {
  id: string;
  label: string;
  question?: string;
};

export function humanContextSkipPromptSection(
  basePrompt: string,
  questions: HumanContextQuestionForDefaults[],
  finalNotes = "",
) {
  const skippedQuestions = questions.map((item) => `- ${item.label}: ${item.question || "Unanswered"}`);
  if (finalNotes.trim()) {
    skippedQuestions.push(`- Additional human notes: ${finalNotes.trim()}`);
  }
  return [
    basePrompt,
    "",
    "HUMAN-IN-THE-LOOP CONTEXT:",
    "- The user explicitly skipped the optional clarification questions.",
    ...skippedQuestions,
    "",
    "Infer missing details from the full project context during generation. Record every inferred choice as an assumption, and keep safety-critical uncertainty explicit instead of inventing a hidden value.",
  ].join("\n");
}

export function humanContextSkipChatSummary(
  questions: HumanContextQuestionForDefaults[],
  finalNotes = "",
) {
  const lines = [
    "Skipped optional clarification questions. Forma will infer missing details from the project context and record them as assumptions.",
    ...questions.map((question) => `- ${question.label}: skipped`),
  ];
  if (finalNotes.trim()) {
    lines.push(`- Additional notes: ${finalNotes.trim()}`);
  }
  return lines.join("\n");
}
