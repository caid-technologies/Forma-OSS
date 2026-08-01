export type GenerationLlmOption = {
  provider: string;
  model: string;
  label: string;
  supports_image_input?: boolean | null;
  selected?: boolean;
  configured?: boolean;
};

export function generationLlmImageSupport(option: Pick<GenerationLlmOption, "provider" | "model">): boolean | null {
  const provider = option.provider.trim().toLowerCase();
  const model = option.model.trim().toLowerCase().replace(/^models\//, "");

  if (provider === "gemini" || provider === "anthropic") return true;
  if (provider === "cloudflare" && model === "@cf/google/gemma-4-26b-a4b-it") return true;
  if (["-vl", "_vl", "/vl", "vision", "llava"].some((marker) => model.includes(marker))) return true;
  if (provider === "openai" && ["gpt-4o", "gpt-4.1", "gpt-5"].some((prefix) => model.startsWith(prefix))) return true;
  if (["nemotron", "gpt-oss", "coder"].some((marker) => model.includes(marker))) return false;
  return null;
}

export function generationLlmKey(option: Pick<GenerationLlmOption, "provider" | "model">) {
  return `${option.provider}/${option.model}`;
}
