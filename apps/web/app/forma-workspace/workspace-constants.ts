import { WORKSPACE_STATUS_STALE_AFTER_MS } from "../../lib/connection-status";
import type { AgentPipelineStep, GenerationWorkflowOption } from "./types";

export const DEFAULT_WORKFLOW_ID = "default";
export const WEB_RESEARCH_WORKFLOW_ID = "web_research";
export const JOB_POLL_INTERVAL_MS = 5000;
export const ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS = 1200;
export const PIPELINE_UI_HEARTBEAT_MS = 5000;
export const PIPELINE_STALE_AFTER_MS = WORKSPACE_STATUS_STALE_AFTER_MS;
export const RECOVERY_JOB_BATCH_SIZE = 3;
export const RECOVERY_JOB_MAX_BACKOFF_MS = 60000;
export const LOG_POLL_INTERVAL_MS = 5000;
export const CHAT_THREAD_STORAGE_PREFIX = "forma.chat.";
export const CHAT_INDEX_STORAGE_KEY = "forma.chatIndex";
export const PINNED_CHATS_STORAGE_KEY = "forma.pinnedChats";
export const LEGACY_PROJECT_CHAT_STORAGE_PREFIX = "forma.projectChat.";
export const MAX_PROJECT_CHAT_MESSAGES = 80;
export const MAX_CHAT_INDEX_ITEMS = 200;
export const INITIAL_CHAT_TIMESTAMP = "2000-01-01T00:00:00.000Z";
export const NEW_PROJECT_TITLE = "New project";
export const CHAT_DIAGNOSTIC_CHARACTER_LIMIT = 420;

export const defaultGenerationWorkflows: GenerationWorkflowOption[] = [
  { id: DEFAULT_WORKFLOW_ID, label: "Catalog", description: "Catalog workflow", uses_catalog: true },
  { id: WEB_RESEARCH_WORKFLOW_ID, label: "Web Research", description: "Live web research workflow", uses_web_research: true, uses_firecrawl_mcp: true, uses_external_sources: true },
];

export const RUNPOD_PARTI_BASE_MODEL = "caid-technologies/parti-base";
export const BASETEN_GLM_MODEL = "zai-org/GLM-5.2";
export const BASETEN_DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-V4-Pro";
export const ANTHROPIC_OPUS_MODEL = "claude-opus-5";
export const ANTHROPIC_SONNET_MODEL = "claude-sonnet-5";
export const GEMINI_FLASH_MODEL = "gemini-3.7-flash";
export const CLOUDFLARE_GEMMA_MODEL = "@cf/google/gemma-4-26b-a4b-it";
export const NVIDIA_GLM_MODEL = "nvidia/z-ai/glm-5.2";
export const NVIDIA_QWEN_CODER_32B_MODEL = "qwen/qwen2.5-coder-32b-instruct";
export const NVIDIA_LLAMA_8B_MODEL = "meta/llama-3.1-8b-instruct";

export const defaultAgentPipelineSteps: AgentPipelineStep[] = [
  {
    id: "safety_guardrail",
    agent: "Safety Guardrail",
    label: "Checking safe build scope",
    description: "Screening the request for low-voltage maker hardware constraints.",
    duration_ms: 3500,
  },
  {
    id: "context_clarifier",
    agent: "Context Clarifier Agent",
    label: "Clarifying build context",
    description: "Checking whether user-provided answers should be folded into generation.",
    duration_ms: 2500,
  },
  {
    id: "intent_parser",
    agent: "Intent Parser Agent",
    label: "Parsing the hardware idea",
    description: "Converting the prompt into project intent and category.",
    duration_ms: 5500,
  },
  {
    id: "requirements",
    agent: "Requirements Agent",
    label: "Extracting requirements",
    description: "Capturing functions, voltage, constraints, and safety notes.",
    duration_ms: 5500,
  },
  {
    id: "system_architecture",
    agent: "System Architecture Agent",
    label: "Decomposing the complete system",
    description: "Building a purpose-driven tree of electrical, mechanical, firmware, and nested subsystems.",
    duration_ms: 5500,
  },
  {
    id: "component_selection",
    agent: "Component Selection Agent",
    label: "Selecting compatible parts",
    description: "Choosing parts by system role before exact catalog pins are hydrated.",
    duration_ms: 6500,
  },
  {
    id: "wiring_netlist",
    agent: "Wiring/Netlist Agent",
    label: "Drafting nets and pin mappings",
    description: "Connecting power, ground, buses, controller pins, and peripherals.",
    duration_ms: 6500,
  },
  {
    id: "validation_repair",
    agent: "Validation + Auto-Correction Agent",
    label: "Validating and repairing wiring",
    description: "Checking shorts, voltage mismatches, unpowered parts, and pin conflicts.",
    duration_ms: 5500,
  },
  {
    id: "bom",
    agent: "BOM Agent",
    label: "Calculating BOM and cost",
    description: "Summing selected components and updating the project estimate.",
    duration_ms: 3000,
  },
  {
    id: "mechanical_fabrication",
    agent: "Mechanical/Fabrication Agent",
    label: "Designing enclosure and placement",
    description: "Generating mounting, fabrication, CAD, and 3D placement details.",
    duration_ms: 6500,
  },
  {
    id: "assembly",
    agent: "Assembly Instruction Agent",
    label: "Writing build steps",
    description: "Producing sequential assembly instructions and safety flags.",
    duration_ms: 5500,
  },
  {
    id: "package_project",
    agent: "Project Packager",
    label: "Packaging project artifacts",
    description: "Building the HardwareIR, diagrams, validation summary, and saved record.",
    duration_ms: 3500,
  },
];

export const optionalImagePipelineStep: AgentPipelineStep = {
  id: "image_generation",
  agent: "Product Image Agent",
  label: "Generating product visuals",
  description: "Creating optional concept images from the completed HardwareIR visual spec.",
  duration_ms: 8000,
  optional: true,
};

export const samplePrompts = [
  "Compact handheld device with display, controls, USB-C power, and enclosure",
  "Environmental monitor with sensor feedback, display, and battery power",
  "Small controller for a low-voltage actuator or relay",
];

export function generationLlmLabel(provider: string, model: string) {
  if (provider === "runpod-serverless" && model === RUNPOD_PARTI_BASE_MODEL) return RUNPOD_PARTI_BASE_MODEL;
  if (provider === "runpod" && model === RUNPOD_PARTI_BASE_MODEL) return "Runpod Parti Base";
  if (provider === "baseten" && model === BASETEN_GLM_MODEL) return "GLM 5.2";
  if (provider === "baseten" && model === BASETEN_DEEPSEEK_MODEL) return "Baseten DeepSeek V4 Pro";
  if (provider === "anthropic" && model === ANTHROPIC_OPUS_MODEL) return "Claude Opus 5";
  if (provider === "anthropic" && model === ANTHROPIC_SONNET_MODEL) return "Claude Sonnet 5";
  if (provider === "gemini" && model === GEMINI_FLASH_MODEL) return "Gemini 3.7 Flash";
  if (provider === "vertex" && model === GEMINI_FLASH_MODEL) return "Vertex Gemini 3.7 Flash";
  if (provider === "huggingface") return `Hugging Face ${model}`;
  if (provider === "gmi" && model === "anthropic/claude-fable-5") return "GMI Claude Fable 5";
  if (provider === "cloudflare" && model === CLOUDFLARE_GEMMA_MODEL) return "Cloudflare Gemma 4 26B A4B";
  if (provider === "nvidia" && model === NVIDIA_GLM_MODEL) return "NVIDIA GLM 5.2";
  if (provider === "nvidia" && model === NVIDIA_QWEN_CODER_32B_MODEL) return "NVIDIA Qwen2.5 Coder 32B";
  if (provider === "nvidia" && model === NVIDIA_LLAMA_8B_MODEL) return "NVIDIA Llama 3.1 8B";
  if (provider === "simulation") return "Local Simulation";
  return `${provider} ${model}`.trim();
}
