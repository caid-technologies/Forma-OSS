const ARTIFICIAL_CHOICES = new Set([
  "custom",
  "other",
  "something else",
  "none of these",
]);

export function normalizeContextSuggestions(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const suggestions: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const suggestion = item.trim().replace(/\s+/g, " ").slice(0, 120);
    const key = suggestion.toLowerCase();
    if (!suggestion || ARTIFICIAL_CHOICES.has(key) || seen.has(key)) continue;
    seen.add(key);
    suggestions.push(suggestion);
    if (suggestions.length === 4) break;
  }
  return suggestions;
}
