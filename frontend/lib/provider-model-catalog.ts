export type ProviderModelOption = {
  value: string;
  label: string;
  detail?: string;
  group?: string;
};

function model(value: string, label: string, detail?: string, group?: string): ProviderModelOption {
  return { value, label, detail, group };
}

// These are discovery suggestions, not an allowlist. Provider catalogs change often,
// so every model picker also accepts an arbitrary provider model ID.
export const LLM_MODEL_OPTIONS: Record<string, ProviderModelOption[]> = {
  openai: [
    model("gpt-5.6-sol", "GPT-5.6 Sol", "Frontier coding and agentic work"),
    model("gpt-5.6-terra", "GPT-5.6 Terra", "Balanced general-purpose model"),
    model("gpt-5.6-luna", "GPT-5.6 Luna", "Fast, efficient model"),
    model("gpt-5.5", "GPT-5.5", "Forma legacy default"),
  ],
  anthropic: [
    model("claude-fable-5", "Claude Fable 5", "Most capable widely available Claude model"),
    model("claude-opus-4-8", "Claude Opus 4.8", "Complex agentic and coding work"),
    model("claude-sonnet-5", "Claude Sonnet 5", "Balanced intelligence and speed"),
    model("claude-haiku-4-5", "Claude Haiku 4.5", "Fast, cost-efficient Claude model"),
  ],
  gemini: [
    model("gemini-3.6-flash", "Gemini 3.6 Flash", "Agentic and multimodal workloads"),
    model("gemini-3.5-flash", "Gemini 3.5 Flash", "Coding and sustained agentic tasks"),
    model("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "High-throughput, cost-efficient tasks"),
    model("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Fast general-purpose model"),
    model("gemini-2.5-pro", "Gemini 2.5 Pro", "Stable previous-generation pro model"),
    model("gemini-2.5-flash", "Gemini 2.5 Flash", "Stable previous-generation flash model"),
  ],
  baseten: [
    model("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro"),
    model("zai-org/GLM-5.2", "GLM 5.2"),
    model("moonshotai/Kimi-K2.7-Code", "Kimi K2.7 Code"),
    model("moonshotai/Kimi-K2.6", "Kimi K2.6"),
    model("nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B", "Nemotron 3 Ultra"),
    model("openai/gpt-oss-120b", "GPT-OSS 120B"),
  ],
  gmi: [
    model("anthropic/claude-fable-5", "Claude Fable 5", "Forma default; availability depends on your GMI organization"),
    model("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "GMI API reference example; check your organization's live model list"),
  ],
  huggingface: [
    model("zai-org/GLM-5.2", "GLM 5.2", "Inference Providers"),
    model("moonshotai/Kimi-K2.7-Code", "Kimi K2.7 Code", "Inference Providers"),
    model("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", "Inference Providers"),
    model("moonshotai/Kimi-K2.6", "Kimi K2.6", "Inference Providers"),
    model("Qwen/Qwen3.5-9B", "Qwen 3.5 9B", "Inference Providers"),
    model("openai/gpt-oss-120b", "GPT-OSS 120B", "Inference Providers"),
    model("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B Instruct", "Inference Providers"),
    model("Qwen/Qwen2.5-Coder-3B-Instruct:nscale", "Qwen 2.5 Coder 3B", "Forma legacy default via Nscale"),
  ],
  nvidia: [
    model("nvidia/z-ai/glm-5.2", "GLM 5.2"),
    model("qwen/qwen2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B"),
    model("meta/llama-3.1-8b-instruct", "Llama 3.1 8B Instruct"),
    model("meta/llama-3.1-70b-instruct", "Llama 3.1 70B Instruct"),
    model("meta/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct"),
  ],
  runpod: [
    model("caid-technologies/parti-base", "Parti Base", "Forma Runpod deployment"),
  ],
  ollama: [
    model("qwen3:0.6b", "Qwen 3 0.6B"),
    model("qwen3:8b", "Qwen 3 8B"),
    model("llama3.2:3b", "Llama 3.2 3B"),
  ],
};

export const IMAGE_MODEL_OPTIONS: Record<string, ProviderModelOption[]> = {
  huggingface: [
    model("black-forest-labs/FLUX.1-schnell", "FLUX.1 Schnell", "Fast text-to-image generation"),
    model("black-forest-labs/FLUX.1-Krea-dev", "FLUX.1 Krea Dev", "High-quality image generation"),
    model("Qwen/Qwen-Image", "Qwen Image"),
    model("stabilityai/stable-diffusion-xl-base-1.0", "Stable Diffusion XL"),
  ],
  openai: [
    model("gpt-image-2", "GPT Image 2"),
    model("gpt-image-1", "GPT Image 1"),
  ],
  gmi: [
    model("gpt-image-2", "GPT Image 2", "Native OpenAI-compatible GMI endpoint", "Direct generation"),
    model("gpt-image-2-generate", "GPT Image 2 Generate", "GMI request queue", "Direct generation"),
    model("gpt-image-1.5", "GPT Image 1.5", "GMI request queue", "Direct generation"),
    model("gemini-3.1-flash-image-preview", "Gemini 3.1 Flash Image Preview", "Generation and reference-guided editing", "Direct generation"),
    model("gemini-3-pro-image-preview", "Gemini 3 Pro Image Preview", "GMI request queue", "Direct generation"),
    model("gemini-2.5-flash-image", "Gemini 2.5 Flash Image", "Fast generation and editing", "Direct generation"),
    model("flux-kontext-pro", "FLUX Kontext Pro", "Aspect ratio, seed, and safety controls", "Direct generation"),
    model("Flux2-Dev", "FLUX 2 Dev", "Text-to-image generation", "Direct generation"),
    model("Flux2-Klein", "FLUX 2 Klein", "Lightweight image generation", "Direct generation"),
    model("GLM-Image", "GLM Image", "GMI request queue", "Direct generation"),
    model("Qwen-Image-2512", "Qwen Image 2512", "High-resolution text-to-image generation", "Direct generation"),
    model("bria-fibo", "Bria FIBO", "Image generation", "Direct generation"),
    model("reve-create-20250915", "Reve Create", "Text-to-image generation", "Direct generation"),
    model("seedream-3-0-t2i-250415", "Seedream 3.0", "Text-to-image generation", "Direct generation"),
    model("seedream-4-0-250828", "Seedream 4.0", "Image generation", "Direct generation"),
    model("seedream-5.0-lite", "Seedream 5.0 Lite", "2K/3K generation and reference input", "Direct generation"),
    model("seedream-5.0-pro", "Seedream 5.0 Pro", "2K/3K generation; documented by GMI but absent from its catalog index", "Direct generation"),
    model("wan2.7-image", "Wan 2.7 Image", "1K/2K generation", "Direct generation"),
    model("wan2.7-image-pro", "Wan 2.7 Image Pro", "1K/2K/4K generation", "Direct generation"),
    model("Z-Image", "Z-Image", "Image generation", "Direct generation"),
    model("Z-Image-Turbo", "Z-Image Turbo", "Fast image generation", "Direct generation"),

    model("bria-eraser", "Bria Eraser", "Requires an input image", "Reference / edit"),
    model("bria-fibo-edit", "Bria FIBO Edit", "Requires an input image", "Reference / edit"),
    model("bria-fibo-image-blend", "Bria FIBO Image Blend", "Blends reference images", "Reference / edit"),
    model("bria-fibo-recolor", "Bria FIBO Recolor", "Recolors an input image", "Reference / edit"),
    model("bria-fibo-relight", "Bria FIBO Relight", "Relights an input image", "Reference / edit"),
    model("bria-fibo-reseason", "Bria FIBO Reseason", "Transforms an input image", "Reference / edit"),
    model("bria-fibo-restore", "Bria FIBO Restore", "Restores an input image", "Reference / edit"),
    model("bria-fibo-restyle", "Bria FIBO Restyle", "Restyles an input image", "Reference / edit"),
    model("bria-fibo-sketch-to-image", "Bria FIBO Sketch to Image", "Requires a sketch input", "Reference / edit"),
    model("bria-genfill", "Bria Generative Fill", "Requires image and mask inputs", "Reference / edit"),
    model("gpt-image-2-edit", "GPT Image 2 Edit", "Requires an input image", "Reference / edit"),
    model("hunyuan-image-to-image", "Hunyuan Image to Image", "Requires an input image", "Reference / edit"),
    model("reve-edit-20250915", "Reve Edit", "Requires an input image", "Reference / edit"),
    model("reve-edit-fast-20251030", "Reve Edit Fast", "Fast reference-image editing", "Reference / edit"),
    model("reve-remix-20250915", "Reve Remix", "Reference-image remixing", "Reference / edit"),
    model("reve-remix-fast-20251030", "Reve Remix Fast", "Fast reference-image remixing", "Reference / edit"),
    model("seededit-3-0-i2i-250628", "SeedEdit 3.0", "Image-to-image editing", "Reference / edit"),

    model("Gemini-batch-inference", "Gemini Batch Inference", "Batch workflow rather than a direct text-to-image model", "Utility / batch"),
    model("Z-Image-Turbo-Fun-Controlnet-Union-2.1", "Z-Image Turbo ControlNet Union 2.1", "ControlNet workflow requiring control input", "Utility / batch"),
  ],
  together: [
    model("openai/gpt-image-2", "GPT Image 2"),
    model("black-forest-labs/FLUX.1-schnell-Free", "FLUX.1 Schnell Free"),
    model("black-forest-labs/FLUX.1-schnell", "FLUX.1 Schnell"),
    model("black-forest-labs/FLUX.1.1-pro", "FLUX 1.1 Pro"),
    model("black-forest-labs/FLUX.2-dev", "FLUX 2 Dev"),
    model("google/imagen-4.0-fast", "Imagen 4 Fast"),
    model("Qwen/Qwen-Image", "Qwen Image"),
  ],
  "openai-compatible": [
    model("gpt-image-2", "GPT Image 2"),
    model("black-forest-labs/FLUX.1-schnell", "FLUX.1 Schnell"),
    model("vendor/image-model", "Custom provider model", "Replace with your endpoint's model ID"),
  ],
};

const GMI_GEMINI_IMAGE_MODELS = new Set([
  "gemini-2.5-flash-image",
  "gemini-3-pro-image-preview",
  "gemini-3.1-flash-image-preview",
]);

const GMI_WAN_IMAGE_MODELS = new Set(["wan2.7-image", "wan2.7-image-pro"]);
const GMI_SEEDREAM_5_IMAGE_MODELS = new Set(["seedream-5.0-lite", "seedream-5.0-pro"]);

export function gmiImageSettingFieldIds(modelId: string): string[] {
  const normalized = modelId.trim();
  if (normalized === "gpt-image-2") {
    return [
      "image_size",
      "image_quality",
      "image_output_format",
      "image_output_compression",
      "image_background",
      "image_moderation",
    ];
  }
  if (normalized === "gpt-image-2-generate") {
    return ["image_size", "image_quality", "image_output_format"];
  }
  if (normalized === "gpt-image-1.5") {
    return ["image_size", "image_quality", "image_output_format", "image_output_compression", "image_background"];
  }
  if (GMI_GEMINI_IMAGE_MODELS.has(normalized)) {
    return ["image_resolution", "image_aspect_ratio", "image_output_format"];
  }
  if (normalized === "flux-kontext-pro") {
    return [
      "image_aspect_ratio",
      "image_seed",
      "image_prompt_upsampling",
      "image_safety_tolerance",
      "image_output_format",
    ];
  }
  if (GMI_SEEDREAM_5_IMAGE_MODELS.has(normalized)) {
    return ["image_size", "image_output_format", "image_sequential_generation", "image_watermark"];
  }
  if (GMI_WAN_IMAGE_MODELS.has(normalized)) {
    return ["image_resolution"];
  }
  return [];
}

export function settingOptionsForField(integrationId: string, fieldId: string, modelId = ""): ProviderModelOption[] {
  if (integrationId !== "gmi") return [];
  if (!gmiImageSettingFieldIds(modelId).includes(fieldId)) return [];
  if (fieldId === "image_size") {
    if (GMI_SEEDREAM_5_IMAGE_MODELS.has(modelId)) {
      return [model("2K", "2K"), model("3K", "3K"), model("2048x2048", "Square · 2048×2048")];
    }
    if (modelId === "gpt-image-1.5" || modelId === "gpt-image-2-generate") {
      return [
        model("1024x1024", "Square · 1024×1024"),
        model("1024x1536", "Portrait · 1024×1536"),
        model("1536x1024", "Landscape · 1536×1024"),
      ];
    }
    return [
      model("1024x1024", "Square · 1024×1024"),
      model("1024x1536", "Portrait · 1024×1536"),
      model("1536x1024", "Landscape · 1536×1024"),
      model("1920x1080", "Widescreen · 1920×1080"),
    ];
  }
  if (fieldId === "image_quality") return [model("auto", "Auto"), model("low", "Low"), model("medium", "Medium"), model("high", "High")];
  if (fieldId === "image_output_format") {
    const options = [model("png", "PNG"), model("jpeg", "JPEG")];
    return modelId === "gpt-image-1.5" ? [...options, model("webp", "WebP")] : options;
  }
  if (fieldId === "image_background") {
    const options = [model("auto", "Auto"), model("opaque", "Opaque")];
    return modelId === "gpt-image-1.5" ? [...options, model("transparent", "Transparent")] : options;
  }
  if (fieldId === "image_moderation") return [model("auto", "Auto"), model("low", "Low")];
  if (fieldId === "image_resolution") {
    if (modelId === "wan2.7-image") return [model("1K", "1K"), model("2K", "2K")];
    if (modelId === "wan2.7-image-pro") return [model("1K", "1K"), model("2K", "2K"), model("4K", "4K")];
    return [model("512", "512"), model("1K", "1K"), model("2K", "2K"), model("4K", "4K")];
  }
  if (fieldId === "image_aspect_ratio") {
    if (modelId === "flux-kontext-pro") return ["1:1", "16:9", "9:16", "4:3", "3:7", "7:3"].map((value) => model(value, value));
    return ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"].map((value) => model(value, value));
  }
  if (fieldId === "image_prompt_upsampling" || fieldId === "image_watermark") {
    return [model("false", "Disabled"), model("true", "Enabled")];
  }
  if (fieldId === "image_safety_tolerance") {
    return ["0", "1", "2", "3", "4", "5", "6"].map((value) => model(value, value, value === "0" ? "Most strict" : value === "6" ? "Most permissive" : undefined));
  }
  if (fieldId === "image_sequential_generation") return [model("disabled", "Disabled"), model("auto", "Auto")];
  return [];
}

export function modelOptionsForField(integrationId: string, fieldId: string): ProviderModelOption[] {
  if (fieldId === "llm_selector") {
    return Object.entries(LLM_MODEL_OPTIONS).flatMap(([provider, options]) =>
      options.map((option) => ({
        ...option,
        value: `${provider}/${option.value}`,
        label: `${providerLabel(provider)} · ${option.label}`,
      })),
    );
  }
  if (fieldId === "llm_model") {
    return Object.values(LLM_MODEL_OPTIONS).flat();
  }
  if (fieldId === "image_model") {
    return IMAGE_MODEL_OPTIONS[integrationId] || Object.values(IMAGE_MODEL_OPTIONS).flat();
  }
  if (fieldId === "model" || fieldId === "fallback_model") {
    if (integrationId === "image") return IMAGE_MODEL_OPTIONS["openai-compatible"];
    return LLM_MODEL_OPTIONS[integrationId] || [];
  }
  return [];
}

function providerLabel(provider: string) {
  return ({
    anthropic: "Anthropic",
    baseten: "Baseten",
    gemini: "Google Gemini",
    gmi: "GMI Cloud",
    huggingface: "Hugging Face",
    nvidia: "NVIDIA",
    ollama: "Ollama",
    openai: "OpenAI",
    runpod: "Runpod",
  } as Record<string, string>)[provider] || provider;
}
