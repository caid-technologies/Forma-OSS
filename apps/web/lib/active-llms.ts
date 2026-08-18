export type GenerationLlmOption = {
  provider: string;
  model: string;
  label: string;
  supports_image_input?: boolean | null;
  selected?: boolean;
  configured?: boolean;
};

export type ImageGenerationCapability = {
  configured?: boolean | null;
  requestCapable?: boolean | null;
  provider?: string | null;
};

export function generationLlmImageSupport(option: Pick<GenerationLlmOption, "provider" | "model">): boolean | null {
  const provider = option.provider.trim().toLowerCase();
  const model = option.model.trim().toLowerCase().replace(/^models\//, "");

  if (provider === "gemini" || provider === "vertex" || provider === "anthropic") return true;
  if (provider === "cloudflare" && model === "@cf/google/gemma-4-26b-a4b-it") return true;
  if (["-vl", "_vl", "/vl", "vision", "llava"].some((marker) => model.includes(marker))) return true;
  if (provider === "openai" && ["gpt-4o", "gpt-4.1", "gpt-5"].some((prefix) => model.startsWith(prefix))) return true;
  if (["nemotron", "gpt-oss", "coder"].some((marker) => model.includes(marker))) return false;
  return null;
}

export function generationLlmKey(option: Pick<GenerationLlmOption, "provider" | "model">) {
  return `${option.provider}/${option.model}`;
}

export function llmHasImageOrMultimodalCapability(
  option: Pick<GenerationLlmOption, "provider" | "model" | "supports_image_input">,
) {
  return (option.supports_image_input ?? generationLlmImageSupport(option)) === true;
}

export function selectedModelsHaveImageOrMultimodalCapability(
  llms: Array<Pick<GenerationLlmOption, "provider" | "model" | "supports_image_input">> = [],
  imageGeneration?: ImageGenerationCapability | null,
) {
  if (imageGeneration?.requestCapable === true) return true;
  if (imageGeneration?.configured === true && Boolean(imageGeneration.provider)) return true;
  return llms.some(llmHasImageOrMultimodalCapability);
}

export function shouldShowProductImageSection({
  imageCandidates = [],
  llms = [],
  imageGeneration = null,
  metadata = {},
}: {
  imageCandidates?: Array<{ src?: string | null }>;
  llms?: Array<Pick<GenerationLlmOption, "provider" | "model" | "supports_image_input">>;
  imageGeneration?: ImageGenerationCapability | null;
  metadata?: Record<string, any>;
}) {
  if (imageCandidates.some((candidate) => Boolean(candidate?.src))) return true;
  const status = String(metadata.image_output_status || "").trim().toLowerCase();
  if (metadata.image_output_requested === true || metadata.image_output_failed === true) return true;
  if (["failed", "succeeded", "pending"].includes(status)) return true;
  return selectedModelsHaveImageOrMultimodalCapability(llms, imageGeneration);
}
