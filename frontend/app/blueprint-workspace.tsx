"use client";

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import {
  activeLlmsFromIntegrations,
  generationLlmKey,
  type GenerationLlmOption,
  type IntegrationsPayload,
} from "../lib/active-llms";
import { buildProjectDocsMarkdown, docsExportFilename } from "../lib/docs-export";
import { useFormaAuth } from "../lib/forma-auth";
import {
  useAdminSession,
  useBackendLogs,
  useJobs,
  type A2AJob,
} from "./blueprint-workspace/use-admin-data";
import { useDeferredTask } from "./blueprint-workspace/use-deferred-task";
import {
  useVideoModels,
  type VideoGenerationMode,
  type VideoModelOption,
} from "./blueprint-workspace/use-video-models";
import {
  VIDEO_PROMPT_MAX_CHARS,
  useProjectVideo,
  videoIdentity,
  videoLabel,
  videoPromptText,
  videoSourceUrl,
  type StoredVideoInfo,
} from "./blueprint-workspace/use-project-video";
import {
  JobsPanel,
  LogsPanel,
  formatBytes,
  isFinalVideoStatus,
  statusTone,
} from "./blueprint-workspace/admin-panels";
import HomeChatView from "./blueprint-workspace/home-chat-view";
import {
  ProjectGallery,
  buildProjectGalleryItems,
  previewableImageSrc,
  resolveProjectImageCandidates,
  type ProjectImageCandidate,
} from "./blueprint-workspace/project-gallery";
import {
  AssemblyPanel,
  BomPanel,
  ChatNamespaceSummaryPanel,
  MechanicalPanel,
  OverviewPanel,
} from "./blueprint-workspace/project-detail-panels";
import {
  ChatSidebar,
  MobileSidebarButton,
  MobileSidebarDrawer,
  MobileWorkspaceBar,
  type ChatListItem,
} from "./blueprint-workspace/sidebar";
import WorkspaceFrame from "./blueprint-workspace/workspace-frame";
import {
  Sparkles,
  Cpu,
  ShieldCheck,
  AlertTriangle,
  CheckCircle,
  ShoppingBag,
  History,
  Box,
  RefreshCw,
  Eye,
  Film,
  Database,
  ArrowRight,
  ArrowLeft,
  Info,
  Layers,
  Paperclip,
  ExternalLink,
  KeyRound,
  Terminal,
  MessageSquare,
  Square,
} from "lucide-react";

const SchematicCanvas = dynamic(() => import("../components/schematic-canvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[620px] items-center justify-center bg-[#0f1014] text-xs font-black uppercase tracking-[0.16em] text-slate-600">
      Loading wiring diagram...
    </div>
  ),
});

const DEFAULT_API_URL = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_API_URL);
const DEFAULT_SHOW_DEVELOPER_TOOLS =
  process.env.NODE_ENV === "development" ||
  isTruthyEnv(process.env.NEXT_PUBLIC_BLUEPRINT_DEBUG) ||
  isTruthyEnv(process.env.NEXT_PUBLIC_BLUEPRINT_DEV_MODE);
const DEFAULT_WORKFLOW_ID = "default";
const WEB_RESEARCH_WORKFLOW_ID = "web_research";
const FIRECRAWL_EXTERNAL_SOURCE_PROVIDER = "firecrawl";
const JOB_POLL_INTERVAL_MS = 5000;
const ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS = 1200;
const PIPELINE_UI_HEARTBEAT_MS = 5000;
const PIPELINE_STALE_AFTER_MS = 30000;
const RECOVERY_JOB_BATCH_SIZE = 3;
const RECOVERY_JOB_MAX_BACKOFF_MS = 60000;
const LOG_POLL_INTERVAL_MS = 5000;
const CHAT_THREAD_STORAGE_PREFIX = "blueprint.chat.";
const CHAT_INDEX_STORAGE_KEY = "blueprint.chatIndex";
const LEGACY_PROJECT_CHAT_STORAGE_PREFIX = "blueprint.projectChat.";
const MAX_PROJECT_CHAT_MESSAGES = 80;
const MAX_CHAT_INDEX_ITEMS = 200;
const INITIAL_CHAT_TIMESTAMP = "2000-01-01T00:00:00.000Z";
const NEW_PROJECT_TITLE = "New project";

let lastKnownServerStatus: "connected" | "disconnected" | null = null;

type GenerationWorkflowOption = {
  id: string;
  label: string;
  description?: string;
  uses_catalog?: boolean;
  uses_web_research?: boolean;
  uses_firecrawl_mcp?: boolean;
  uses_external_sources?: boolean;
};

type AgentPipelineStep = {
  id: string;
  agent: string;
  label: string;
  description: string;
  duration_ms?: number;
  optional?: boolean;
};

type AgentPipelineEvent = {
  workflow?: string;
  step_id: string;
  status: "started" | "completed" | "failed" | "skipped" | string;
  agent?: string;
  label?: string;
  description?: string;
  observed_at?: string;
  details?: Record<string, any>;
};

type AgentPipelineProgress = {
  startedAt: string;
  steps: AgentPipelineStep[];
  currentStepIndex: number;
  estimated: boolean;
  synced?: boolean;
  jobId?: string | null;
  events?: AgentPipelineEvent[];
  uiUpdatedAt?: string;
};

type ChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  status?: "idle" | "loading" | "success" | "error" | "cancelled";
  timestamp: string;
  projectId?: string | null;
  pipelineProgress?: AgentPipelineProgress | null;
};

type ActiveGenerationRun = {
  kind: "chat" | "project-chat";
  controller: AbortController;
  jobId: string | null;
  chatId: string;
  assistantMessageId: string | null;
  cancelled: boolean;
};

type ActiveGenerationState = Pick<ActiveGenerationRun, "kind" | "jobId">;

type HumanContextQuestion = {
  id: string;
  label: string;
  question: string;
  placeholder: string;
  suggestions: string[];
};

type PendingHumanContext = {
  basePrompt: string;
  questions: HumanContextQuestion[];
  answers: Record<string, string>;
};

const defaultGenerationWorkflows: GenerationWorkflowOption[] = [
  { id: DEFAULT_WORKFLOW_ID, label: "Catalog", description: "Catalog workflow", uses_catalog: true },
  { id: WEB_RESEARCH_WORKFLOW_ID, label: "Web Research", description: "Firecrawl research workflow", uses_web_research: true, uses_firecrawl_mcp: true, uses_external_sources: true },
];

const RUNPOD_PARTI_BASE_MODEL = "caid-technologies/parti-base";
const BASETEN_GLM_MODEL = "zai-org/GLM-5.2";
const BASETEN_DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-V4-Pro";
const ANTHROPIC_SONNET_MODEL = "claude-sonnet-5";
const NVIDIA_GLM_MODEL = "nvidia/z-ai/glm-5.2";
const NVIDIA_QWEN_CODER_32B_MODEL = "qwen/qwen2.5-coder-32b-instruct";
const NVIDIA_LLAMA_8B_MODEL = "meta/llama-3.1-8b-instruct";

const localOnlyGenerationLlms: GenerationLlmOption[] =
  process.env.NODE_ENV === "development"
    ? [{ provider: "baseten", model: BASETEN_DEEPSEEK_MODEL, label: "Baseten DeepSeek V4 Pro" }]
    : [];

const defaultGenerationLlms: GenerationLlmOption[] = [
  { provider: "openai", model: "gpt-5.5", label: "OpenAI GPT-5.5" },
  { provider: "anthropic", model: ANTHROPIC_SONNET_MODEL, label: "Claude Sonnet 5" },
  { provider: "huggingface", model: "Qwen/Qwen2.5-Coder-3B-Instruct:nscale", label: "Hugging Face Qwen2.5 Coder" },
  { provider: "runpod", model: RUNPOD_PARTI_BASE_MODEL, label: "Runpod Parti Base" },
  { provider: "runpod-serverless", model: RUNPOD_PARTI_BASE_MODEL, label: RUNPOD_PARTI_BASE_MODEL },
  { provider: "baseten", model: BASETEN_GLM_MODEL, label: "GLM 5.2" },
  ...localOnlyGenerationLlms,
  { provider: "gmi", model: "anthropic/claude-fable-5", label: "GMI Claude Fable 5" },
  { provider: "nvidia", model: NVIDIA_GLM_MODEL, label: "NVIDIA GLM 5.2" },
  { provider: "nvidia", model: NVIDIA_QWEN_CODER_32B_MODEL, label: "NVIDIA Qwen2.5 Coder 32B" },
  { provider: "nvidia", model: NVIDIA_LLAMA_8B_MODEL, label: "NVIDIA Llama 3.1 8B" },
];

const defaultAgentPipelineSteps: AgentPipelineStep[] = [
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
    id: "component_selection",
    agent: "Component Selection Agent",
    label: "Selecting compatible parts",
    description: "Choosing parts and pin definitions for the build.",
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

const optionalImagePipelineStep: AgentPipelineStep = {
  id: "image_generation",
  agent: "Product Image Agent",
  label: "Generating product visuals",
  description: "Creating optional concept images from the completed HardwareIR visual spec.",
  duration_ms: 8000,
  optional: true,
};

const CHAT_DIAGNOSTIC_CHARACTER_LIMIT = 420;

function generationLlmLabel(provider: string, model: string) {
  if (provider === "runpod-serverless" && model === RUNPOD_PARTI_BASE_MODEL) return RUNPOD_PARTI_BASE_MODEL;
  if (provider === "runpod" && model === RUNPOD_PARTI_BASE_MODEL) return "Runpod Parti Base";
  if (provider === "baseten" && model === BASETEN_GLM_MODEL) return "GLM 5.2";
  if (provider === "baseten" && model === BASETEN_DEEPSEEK_MODEL) return "Baseten DeepSeek V4 Pro";
  if (provider === "anthropic" && model === ANTHROPIC_SONNET_MODEL) return "Claude Sonnet 5";
  if (provider === "huggingface") return `Hugging Face ${model}`;
  if (provider === "gmi" && model === "anthropic/claude-fable-5") return "GMI Claude Fable 5";
  if (provider === "nvidia" && model === NVIDIA_GLM_MODEL) return "NVIDIA GLM 5.2";
  if (provider === "nvidia" && model === NVIDIA_QWEN_CODER_32B_MODEL) return "NVIDIA Qwen2.5 Coder 32B";
  if (provider === "nvidia" && model === NVIDIA_LLAMA_8B_MODEL) return "NVIDIA Llama 3.1 8B";
  if (provider === "simulation") return "Local Simulation";
  return `${provider} ${model}`.trim();
}

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function isTruthyEnv(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value || "").trim().toLowerCase());
}

function downloadBrowserFile(contents: string, filename: string, mimeType: string) {
  const blob = new Blob([contents], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const samplePrompts = [
  "Compact handheld device with display, controls, USB-C power, and enclosure",
  "Environmental monitor with sensor feedback, display, and battery power",
  "Small controller for a low-voltage actuator or relay",
];

function newChatMessageId() {
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function newBuildChatId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function newFrontendJobId() {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `job_frontend_${suffix.replace(/[^A-Za-z0-9_.:-]/g, "_")}`;
}

function chatTimestamp() {
  return new Date().toISOString();
}

function formatChatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function initialChatMessages(timestamp: string = INITIAL_CHAT_TIMESTAMP): ChatMessage[] {
  return [
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "Tell me what you want to build. I can turn it into a project with parts, wiring, mechanical notes, validation, jobs, and optional product images.",
      status: "idle",
      timestamp,
    },
  ];
}

function validChatStatus(value: any): ChatMessage["status"] {
  return ["idle", "loading", "success", "error", "cancelled"].includes(value) ? value : "idle";
}

function validChatRole(value: any): ChatMessage["role"] {
  return ["assistant", "user", "system"].includes(value) ? value : "assistant";
}

function normalizeChatMessage(value: any): ChatMessage | null {
  if (!value || typeof value !== "object" || typeof value.content !== "string") return null;
  return {
    id: typeof value.id === "string" && value.id ? value.id : newChatMessageId(),
    role: validChatRole(value.role),
    content: value.content,
    status: validChatStatus(value.status),
    timestamp: typeof value.timestamp === "string" && value.timestamp ? value.timestamp : chatTimestamp(),
    projectId: typeof value.projectId === "string" ? value.projectId : null,
    pipelineProgress: normalizeAgentPipelineProgress(value.pipelineProgress),
  };
}

function chatHasStarted(messages: ChatMessage[]) {
  return messages.some((message) => message.role === "user" || Boolean(message.projectId));
}

function chatTitleFromMessages(messages: ChatMessage[], fallback = NEW_PROJECT_TITLE) {
  const firstUserMessage = messages.find((message) => message.role === "user" && message.content.trim());
  const title = firstUserMessage?.content.trim().replace(/\s+/g, " ");
  if (!title) return fallback;
  return title.length > 80 ? `${title.slice(0, 77)}...` : title;
}

function persistableChatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .map(normalizeChatMessage)
    .filter((message: ChatMessage | null): message is ChatMessage => Boolean(message))
    .slice(-MAX_PROJECT_CHAT_MESSAGES);
}

function chatIsWaiting(messages: ChatMessage[]) {
  return messages.some((message) => message.status === "loading");
}

function chatMessageIdentityKey(messages: ChatMessage[]) {
  return messages.map((message) => message.id).join("|");
}

function normalizeProjectHistoryRecord(value: any): any | null {
  if (!value || typeof value !== "object") return null;
  const projectId = typeof value.project_id === "string" ? value.project_id.trim() : "";
  if (!projectId) return null;
  const creatorDisplay =
    typeof value.creator_username === "string" && value.creator_username.trim()
      ? value.creator_username.trim()
      : typeof value.creator_display === "string" && value.creator_display.trim()
        ? value.creator_display.trim()
        : "unknown";
  const creatorImageUrl =
    typeof value.creator_image_url === "string" && value.creator_image_url.trim()
      ? value.creator_image_url.trim()
      : typeof value.creatorImageUrl === "string" && value.creatorImageUrl.trim()
        ? value.creatorImageUrl.trim()
        : null;
  return {
    ...value,
    project_id: projectId,
    chat_id: typeof value.chat_id === "string" ? value.chat_id.trim() : "",
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : "Untitled project",
    prompt: typeof value.prompt === "string" ? value.prompt : "",
    created_at: typeof value.created_at === "string" && value.created_at ? value.created_at : chatTimestamp(),
    visibility: value.visibility === "private" ? "private" : "public",
    can_chat: Boolean(value.can_chat ?? value.canChat),
    creator_display: creatorDisplay,
    creator_username: creatorDisplay,
    creator_image_url: creatorImageUrl,
    parts_count: Math.max(0, Number(value.parts_count || value.partsCount || 0)),
    star_count: Math.max(0, Number(value.star_count || value.starCount || 0)),
  };
}

function normalizeAgentPipelineStep(value: any): AgentPipelineStep | null {
  if (!value || typeof value !== "object") return null;
  const id = typeof value.id === "string" && value.id.trim() ? value.id.trim() : "";
  const label = typeof value.label === "string" && value.label.trim() ? value.label.trim() : "";
  if (!id || !label) return null;
  return {
    id,
    label,
    agent: typeof value.agent === "string" && value.agent.trim() ? value.agent.trim() : label,
    description: typeof value.description === "string" ? value.description : "",
    duration_ms: Number.isFinite(Number(value.duration_ms)) ? Math.max(1000, Number(value.duration_ms)) : undefined,
    optional: Boolean(value.optional),
  };
}

function normalizeAgentPipelineSteps(value: any): AgentPipelineStep[] {
  const rawSteps = Array.isArray(value?.steps) ? value.steps : Array.isArray(value) ? value : [];
  const steps = rawSteps.map(normalizeAgentPipelineStep).filter(Boolean) as AgentPipelineStep[];
  return steps.length ? steps : defaultAgentPipelineSteps;
}

function normalizeAgentPipelineProgress(value: any): AgentPipelineProgress | null {
  if (!value || typeof value !== "object") return null;
  const steps = normalizeAgentPipelineSteps(value.steps);
  const events = normalizeAgentPipelineEvents(value.events);
  return {
    startedAt: typeof value.startedAt === "string" && value.startedAt ? value.startedAt : chatTimestamp(),
    steps,
    currentStepIndex: Math.min(Math.max(Number(value.currentStepIndex || 0), 0), Math.max(steps.length - 1, 0)),
    estimated: value.estimated !== false,
    synced: Boolean(value.synced),
    jobId: typeof value.jobId === "string" ? value.jobId : null,
    events,
    uiUpdatedAt: typeof value.uiUpdatedAt === "string" && value.uiUpdatedAt ? value.uiUpdatedAt : chatTimestamp(),
  };
}

function normalizeAgentPipelineEvents(value: any): AgentPipelineEvent[] {
  const rawEvents = Array.isArray(value) ? value : [];
  return rawEvents
    .map((event) => {
      if (!event || typeof event !== "object" || typeof event.step_id !== "string") return null;
      return {
        workflow: typeof event.workflow === "string" ? event.workflow : undefined,
        step_id: event.step_id,
        status: typeof event.status === "string" ? event.status : "started",
        agent: typeof event.agent === "string" ? event.agent : undefined,
        label: typeof event.label === "string" ? event.label : undefined,
        description: typeof event.description === "string" ? event.description : undefined,
        observed_at: typeof event.observed_at === "string" ? event.observed_at : undefined,
        details: event.details && typeof event.details === "object" ? event.details : undefined,
      };
    })
    .filter(Boolean) as AgentPipelineEvent[];
}

function stepsForPipelineRun(steps: AgentPipelineStep[], includeImage: boolean) {
  const normalized = steps.length ? steps : defaultAgentPipelineSteps;
  const baseSteps = normalized.filter((step) => !step.optional || includeImage);
  if (includeImage && !baseSteps.some((step) => step.id === optionalImagePipelineStep.id)) {
    return [...baseSteps, optionalImagePipelineStep];
  }
  return baseSteps;
}

function createAgentPipelineProgress(
  steps: AgentPipelineStep[],
  includeImage: boolean,
  startedAt: string = chatTimestamp(),
  jobId: string | null = null
): AgentPipelineProgress {
  return {
    startedAt,
    steps: stepsForPipelineRun(steps, includeImage),
    currentStepIndex: 0,
    estimated: true,
    synced: false,
    jobId,
    events: [],
    uiUpdatedAt: startedAt,
  };
}

function shouldPulsePipelineUi(progress: AgentPipelineProgress, nowMs: number) {
  const lastUiMs = timestampMs(progress.uiUpdatedAt);
  return lastUiMs === null || nowMs - lastUiMs >= PIPELINE_UI_HEARTBEAT_MS;
}

function agentPipelineStepIndex(progress: AgentPipelineProgress, nowMs: number) {
  const startedMs = Date.parse(progress.startedAt);
  const elapsedMs = Math.max(0, nowMs - (Number.isNaN(startedMs) ? nowMs : startedMs));
  let accumulatedMs = 0;
  for (let index = 0; index < progress.steps.length; index += 1) {
    accumulatedMs += progress.steps[index].duration_ms || 5500;
    if (elapsedMs < accumulatedMs) return index;
  }
  return Math.max(0, progress.steps.length - 1);
}

function advanceAgentPipelineProgress(progress: AgentPipelineProgress, nowMs: number): AgentPipelineProgress {
  if (progress.synced || progress.estimated === false) {
    return shouldPulsePipelineUi(progress, nowMs)
      ? { ...progress, uiUpdatedAt: new Date(nowMs).toISOString() }
      : progress;
  }
  const currentStepIndex = agentPipelineStepIndex(progress, nowMs);
  if (currentStepIndex !== progress.currentStepIndex) {
    return { ...progress, currentStepIndex, uiUpdatedAt: new Date(nowMs).toISOString() };
  }
  return shouldPulsePipelineUi(progress, nowMs)
    ? { ...progress, uiUpdatedAt: new Date(nowMs).toISOString() }
    : progress;
}

function pipelineEventCursor(events: AgentPipelineEvent[] | undefined) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  const lastEvent = normalizedEvents[normalizedEvents.length - 1];
  return [
    normalizedEvents.length,
    lastEvent?.observed_at || "",
    lastEvent?.step_id || "",
    lastEvent?.status || "",
  ].join(":");
}

function isFailedPipelineStatus(status: any) {
  return String(status || "").toLowerCase().includes("failed");
}

function isCompletedPipelineStatus(status: any) {
  const normalized = String(status || "").toLowerCase();
  return normalized === "completed" || normalized === "provider_response_received";
}

function failedPipelineEvent(events: AgentPipelineEvent[] | undefined) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  return [...normalizedEvents].reverse().find((event) => isFailedPipelineStatus(event.status)) || null;
}

function compactDiagnosticText(value: any, limit: number = CHAT_DIAGNOSTIC_CHARACTER_LIMIT) {
  const original = String(value || "").trim();
  if (!original) return "";

  const normalized = original
    .replace(/\r\n/g, "\n")
    .replace(/https:\/\/errors\.pydantic\.dev\/\S+/g, "")
    .replace(/,\s*input_value=(?:'[^']*'|"[^"]*"|[^\]\n]*)/g, "")
    .replace(/,\s*input_type=[^\]\n]+/g, "")
    .replace(/\[type=([^,\]\s]+)[^\]]*\]/g, "[type=$1]");

  const lines = normalized
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .filter((line) => !/^for further information visit/i.test(line))
    .filter((line) => !/^input_(value|type)=/i.test(line));
  const text = lines.join("\n") || original;

  if (text.length <= limit) return text;
  const clipped = text.slice(0, limit).replace(/\s+\S*$/, "").trimEnd();
  return `${clipped || text.slice(0, limit).trimEnd()}...`;
}

function generationFailureChatMessage(message: string, includeJobsHint = false) {
  const compact = compactDiagnosticText(message);
  const content = compact
    ? /^generation failed\b/i.test(compact)
      ? compact
      : `Generation failed: ${compact}`
    : "Generation failed.";
  return includeJobsHint ? `${content}\nFull diagnostics are available in Jobs.` : content;
}

function jobFailureMessage(job: A2AJob) {
  const event = failedPipelineEvent(job.progress_events);
  const eventDetails = event?.details || {};
  const reason = job.error || eventDetails.error || eventDetails.reason || eventDetails.message;
  if (reason) return String(reason);
  if (event?.label) return `${event.label} failed.`;
  return "Generation failed.";
}

function terminalJobMessagePatch(job: A2AJob, message: ChatMessage): Partial<Omit<ChatMessage, "id">> | null {
  if (message.status !== "loading") return null;
  if (["cancelled", "canceled"].includes(String(job.status || "").toLowerCase())) {
    return {
      content: "Generation stopped by you.",
      status: "cancelled",
    };
  }
  if (job.status === "failed") {
    return {
      content: generationFailureChatMessage(jobFailureMessage(job), true),
      status: "error",
    };
  }
  if (job.status === "succeeded") {
    const title = job.result_summary?.title || "Project";
    const projectId = typeof job.result_summary?.project_id === "string" ? job.result_summary.project_id : null;
    return {
      content: `${title} is ready. Loading project output...`,
      status: "success",
      projectId,
    };
  }
  return null;
}

function patchChangesMessage(message: ChatMessage, patch: Partial<Omit<ChatMessage, "id">> | null) {
  if (!patch) return false;
  return Object.entries(patch).some(([key, value]) => (message as any)[key] !== value);
}

function sameAgentPipelineProgress(left: AgentPipelineProgress | null | undefined, right: AgentPipelineProgress | null | undefined) {
  if (left === right) return true;
  if (!left || !right) return false;
  return (
    left.currentStepIndex === right.currentStepIndex &&
    left.estimated === right.estimated &&
    Boolean(left.synced) === Boolean(right.synced) &&
    (left.jobId || null) === (right.jobId || null) &&
    pipelineEventCursor(left.events) === pipelineEventCursor(right.events)
  );
}

function progressFromJobEvents(
  job: A2AJob | null,
  fallback: AgentPipelineProgress,
  includeImage: boolean
): AgentPipelineProgress | null {
  const events = normalizeAgentPipelineEvents(job?.progress_events);
  if (!events.length) return null;
  const previousEvents = normalizeAgentPipelineEvents(fallback.events);
  if (fallback.synced && previousEvents.length > events.length) return fallback;
  const steps = stepsForPipelineRun(fallback.steps, includeImage);
  const indexByStep = new Map(steps.map((step, index) => [step.id, index]));
  let currentStepIndex = fallback.currentStepIndex;
  for (const event of events) {
    const eventIndex = indexByStep.get(event.step_id);
    if (eventIndex === undefined) continue;
    if (isCompletedPipelineStatus(event.status) || event.status === "skipped") {
      currentStepIndex = Math.min(eventIndex + 1, Math.max(steps.length - 1, 0));
    } else {
      currentStepIndex = eventIndex;
    }
  }
  if (fallback.synced && previousEvents.length >= events.length && currentStepIndex < fallback.currentStepIndex) {
    return fallback;
  }
  return {
    ...fallback,
    startedAt: job?.started_at || fallback.startedAt,
    steps,
    currentStepIndex,
    estimated: false,
    synced: true,
    jobId: job?.job_id || fallback.jobId || null,
    events,
    uiUpdatedAt: chatTimestamp(),
  };
}

function mergeMessagePipelineProgressFromJob(
  message: ChatMessage,
  job: A2AJob,
  seedProgress: AgentPipelineProgress,
  includeImage: boolean
) {
  const nextProgress = progressFromJobEvents(job, message.pipelineProgress || seedProgress, includeImage);
  const terminalPatch = terminalJobMessagePatch(job, message);
  const progressChanged = Boolean(nextProgress && !sameAgentPipelineProgress(message.pipelineProgress, nextProgress));
  const patchChanged = patchChangesMessage(message, terminalPatch);
  if (!progressChanged && !patchChanged) return message;
  return {
    ...message,
    ...(terminalPatch || {}),
    pipelineProgress: nextProgress || message.pipelineProgress || null,
    timestamp: chatTimestamp(),
  };
}

function progressIncludesImageStep(progress: AgentPipelineProgress | null | undefined) {
  return Boolean(progress?.steps?.some((step) => step.id === optionalImagePipelineStep.id || step.optional));
}

function mergeMessagesWithJobs(
  messages: ChatMessage[],
  jobsById: Map<string, A2AJob>,
  includeImageDefault: boolean
) {
  let changed = false;
  const nextMessages = messages.map((message) => {
    const jobId = message.pipelineProgress?.jobId;
    if (!jobId) return message;
    const job = jobsById.get(jobId);
    if (!job || !message.pipelineProgress) return message;
    const includeImage = includeImageDefault || progressIncludesImageStep(message.pipelineProgress);
    const nextMessage = mergeMessagePipelineProgressFromJob(message, job, message.pipelineProgress, includeImage);
    if (nextMessage !== message) changed = true;
    return nextMessage;
  });
  return changed ? nextMessages : messages;
}

function advancePipelineMessages(messages: ChatMessage[], nowMs: number) {
  let changed = false;
  const nextMessages = messages.map((message) => {
    if (message.status !== "loading" || !message.pipelineProgress) return message;
    const nextProgress = advanceAgentPipelineProgress(message.pipelineProgress, nowMs);
    if (nextProgress === message.pipelineProgress) return message;
    changed = true;
    return { ...message, pipelineProgress: nextProgress };
  });
  return changed ? nextMessages : messages;
}

function pipelineEventTimestampMs(event: AgentPipelineEvent | null | undefined): number | null {
  return timestampMs(event?.observed_at);
}

function latestPipelineEvent(events: AgentPipelineEvent[]) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  return normalizedEvents[normalizedEvents.length - 1] || null;
}

function pipelineStepForEvent(progress: AgentPipelineProgress, event: AgentPipelineEvent | null | undefined) {
  if (!event) return null;
  return progress.steps.find((step) => step.id === event.step_id) || null;
}

function activePipelineStep(progress: AgentPipelineProgress) {
  const events = normalizeAgentPipelineEvents(progress.events);
  const lastEvent = latestPipelineEvent(events);
  const stepFromEvent = pipelineStepForEvent(progress, lastEvent);
  if (lastEvent && !isCompletedPipelineStatus(lastEvent.status) && lastEvent.status !== "skipped") {
    return stepFromEvent || progress.steps[progress.currentStepIndex] || progress.steps[0] || null;
  }
  return progress.steps[progress.currentStepIndex] || stepFromEvent || progress.steps[0] || null;
}

function completedPipelineStepCount(progress: AgentPipelineProgress) {
  const completed = new Set<string>();
  normalizeAgentPipelineEvents(progress.events).forEach((event) => {
    if (isCompletedPipelineStatus(event.status) || event.status === "skipped") completed.add(event.step_id);
    if (isFailedPipelineStatus(event.status)) completed.delete(event.step_id);
  });
  if (completed.size) return completed.size;
  return progress.estimated ? Math.max(0, progress.currentStepIndex) : 0;
}

function pipelineStepStatus(progress: AgentPipelineProgress, step: AgentPipelineStep, activeStepId: string | null) {
  const events = normalizeAgentPipelineEvents(progress.events);
  const stepEvents = events.filter((event) => event.step_id === step.id);
  const lastStepEvent = stepEvents[stepEvents.length - 1];
  if (isFailedPipelineStatus(lastStepEvent?.status)) return "failed";
  if (lastStepEvent?.status === "skipped") return "skipped";
  if (isCompletedPipelineStatus(lastStepEvent?.status)) return "completed";
  if (activeStepId === step.id) return "active";
  return "pending";
}

function formatPipelineAge(value?: string | null, nowMs: number = Date.now()) {
  const ms = timestampMs(value);
  if (ms === null) return "-";
  return formatDurationSeconds(Math.max(1, Math.round((nowMs - ms) / 1000)));
}

function formatPipelineDetails(details: Record<string, any> | undefined) {
  if (!details || typeof details !== "object") return "";
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 3)
    .map(([key, value]) => {
      const rawText = typeof value === "string" ? value : JSON.stringify(value);
      const text = typeof rawText === "string" ? rawText : String(value);
      return `${key.replace(/_/g, " ")}: ${text.length > 80 ? `${text.slice(0, 77)}...` : text}`;
    })
    .join(" / ");
}

function PipelineStepDot({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "border-emerald-400 bg-emerald-400"
      : status === "failed"
        ? "border-rose-400 bg-rose-400"
        : status === "skipped"
          ? "border-slate-600 bg-slate-800"
          : status === "active"
            ? "border-cyan-300 bg-cyan-300"
            : "border-slate-700 bg-black";
  return <span className={`h-2.5 w-2.5 shrink-0 border ${tone}`} />;
}

function chatThreadStorageKey(chatId: string, scope = "local") {
  return scope === "local"
    ? `${CHAT_THREAD_STORAGE_PREFIX}${chatId}`
    : `${CHAT_THREAD_STORAGE_PREFIX}${encodeURIComponent(scope)}.${chatId}`;
}

function legacyProjectChatStorageKey(projectId: string) {
  return `${LEGACY_PROJECT_CHAT_STORAGE_PREFIX}${projectId}`;
}

function readStoredChatThread(chatId: string, legacyProjectId?: string | null, scope = "local"): ChatMessage[] {
  if (typeof window === "undefined" || !chatId) return [];
  try {
    const raw = window.localStorage.getItem(chatThreadStorageKey(chatId, scope))
      || (scope === "local" && legacyProjectId ? window.localStorage.getItem(legacyProjectChatStorageKey(legacyProjectId)) : null);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatMessage).filter(Boolean) as ChatMessage[] : [];
  } catch {
    return [];
  }
}

function writeStoredChatThread(chatId: string, messages: ChatMessage[], scope = "local") {
  if (typeof window === "undefined" || !chatId) return;
  try {
    window.localStorage.setItem(chatThreadStorageKey(chatId, scope), JSON.stringify(messages.slice(-MAX_PROJECT_CHAT_MESSAGES)));
  } catch {
    // Local chat history is best-effort.
  }
}

function normalizeChatListItem(value: any): ChatListItem | null {
  if (!value || typeof value !== "object") return null;
  const chatId = typeof value.chatId === "string" ? value.chatId.trim() : "";
  if (!chatId) return null;
  return {
    chatId,
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : NEW_PROJECT_TITLE,
    projectId: typeof value.projectId === "string" ? value.projectId : "",
    createdAt: typeof value.createdAt === "string" && value.createdAt ? value.createdAt : chatTimestamp(),
    projectCount: Math.max(0, Number(value.projectCount || 0)),
  };
}

function chatIndexStorageKey(scope = "local") {
  return scope === "local"
    ? CHAT_INDEX_STORAGE_KEY
    : `${CHAT_INDEX_STORAGE_KEY}.${encodeURIComponent(scope)}`;
}

function readStoredChatIndex(scope = "local"): ChatListItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(chatIndexStorageKey(scope));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatListItem).filter(Boolean) as ChatListItem[] : [];
  } catch {
    return [];
  }
}

function writeStoredChatIndex(items: ChatListItem[], scope = "local") {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(chatIndexStorageKey(scope), JSON.stringify(items.slice(0, MAX_CHAT_INDEX_ITEMS)));
  } catch {
    // Local chat index is best-effort.
  }
}

function chatListItemTime(value: string | null | undefined): number {
  const normalizedValue = value?.trim() || "";
  // Project creation timestamps have historically been emitted as UTC without a
  // timezone suffix. Treat them as UTC so they compare correctly with chat
  // updated_at values, which include "Z".
  const timestamp = Date.parse(
    normalizedValue && !/(?:z|[+-]\d{2}:?\d{2})$/i.test(normalizedValue)
      ? `${normalizedValue}Z`
      : normalizedValue
  );
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function latestChatListItemDate(
  left: string | null | undefined,
  right: string | null | undefined
): string | null {
  return chatListItemTime(right) > chatListItemTime(left) ? right || null : left || right || null;
}

function sortChatListItems(items: ChatListItem[]): ChatListItem[] {
  return [...items].sort(
    (left, right) => chatListItemTime(right.createdAt) - chatListItemTime(left.createdAt)
  );
}

function upsertChatListItem(items: ChatListItem[], item: Partial<ChatListItem> & { chatId: string }): ChatListItem[] {
  const existing = items.find((current) => current.chatId === item.chatId);
  const incomingTitle = item.title?.trim() || "";
  const existingTitle = existing?.title?.trim() || "";
  const keepExistingTitle =
    incomingTitle === NEW_PROJECT_TITLE && Boolean(existingTitle) && existingTitle !== NEW_PROJECT_TITLE;
  const incomingProjectId = typeof item.projectId === "string" ? item.projectId : undefined;
  const nextItem: ChatListItem = {
    chatId: item.chatId,
    title: keepExistingTitle ? existingTitle : incomingTitle || existingTitle || NEW_PROJECT_TITLE,
    projectId: incomingProjectId === undefined ? existing?.projectId || "" : incomingProjectId || existing?.projectId || "",
    createdAt: item.createdAt || existing?.createdAt || chatTimestamp(),
    projectCount: Math.max(item.projectCount ?? existing?.projectCount ?? 0, 0),
  };
  return sortChatListItems([nextItem, ...items.filter((current) => current.chatId !== item.chatId)])
    .slice(0, MAX_CHAT_INDEX_ITEMS);
}

function initialProjectChatMessages(projectId: string, title: string, sourcePrompt?: string | null): ChatMessage[] {
  const messages: ChatMessage[] = [];
  if (sourcePrompt?.trim()) {
    messages.push({
      id: newChatMessageId(),
      role: "user",
      content: sourcePrompt.trim(),
      status: "idle",
      timestamp: chatTimestamp(),
      projectId,
    });
  }
  messages.push({
    id: newChatMessageId(),
    role: "assistant",
    content: `${title || "Project"} is the active project for this chat.`,
    status: "success",
    timestamp: chatTimestamp(),
    projectId,
  });
  return messages;
}

function missingProjectNotice(projectId: string) {
  return `This chat pointed at project ${projectId}, but that project is no longer available in the project database. The chat history is still here; generate again to create a new project.`;
}

function messagesWithoutMissingProject(messages: ChatMessage[], projectId: string): ChatMessage[] {
  const notice = missingProjectNotice(projectId);
  const normalizedMessages = messages.map((message) =>
    message.projectId === projectId ? { ...message, projectId: null } : message
  );
  if (normalizedMessages.some((message) => message.role === "assistant" && message.content === notice)) {
    return normalizedMessages;
  }
  const noticeMessage: ChatMessage = {
    id: newChatMessageId(),
    role: "assistant",
    content: notice,
    status: "error",
    timestamp: chatTimestamp(),
    projectId: null,
  };
  return [...normalizedMessages, noticeMessage].slice(-MAX_PROJECT_CHAT_MESSAGES);
}

function automaticHumanContextPromptSection(basePrompt: string) {
  const inferredQuestions = humanContextQuestionsForPrompt(basePrompt);
  return [
    basePrompt,
    "",
    "HUMAN-IN-THE-LOOP CONTEXT:",
    "- User submitted this from the chat interface; generate the project immediately.",
    "- Missing human context should be recorded as unspecified in project docs, not invented.",
    ...inferredQuestions.map((question) => `- ${question.label}: not specified at creation time; preserve as an explicit open question if it affects safety, wiring, materials, or validation.`),
  ].join("\n");
}

function projectChatGenerationPrompt(projectIR: any, userMessage: string, activeNamespaceTab = "chat") {
  const title = projectIR?.overview?.title || "current project";
  const description = projectIR?.overview?.description || "";
  const projectId = projectIR?.assembly_metadata?.project_id || "unknown";
  const namespaceTab = workspaceTabMeta(activeNamespaceTab);
  const namespace = workspaceNamespaceForTab(activeNamespaceTab);
  const components = Array.isArray(projectIR?.components)
    ? projectIR.components.slice(0, 10).map((component: any) => `${component.ref_des || ""} ${component.name || component.part_number || ""}`.trim()).filter(Boolean)
    : [];
  return [
    "Create a new Forma hardware project from this project chat message.",
    `Source project id: ${projectId}`,
    `Source project title: ${title}`,
    description ? `Source project description: ${description}` : "",
    components.length ? `Source components: ${components.join("; ")}` : "",
    `Active chat namespace: ${namespace} (${namespaceTab.label})`,
    "Interpret the user message relative to that namespace unless the message clearly asks for another part of the project.",
    "",
    "User chat message:",
    userMessage,
    "",
    "Return a complete new project. If the user asks for a revision, preserve relevant source-project continuity while creating a new project object.",
  ].filter(Boolean).join("\n");
}

function humanContextQuestionsForPrompt(promptText: string): HumanContextQuestion[] {
  const lower = promptText.toLowerCase();
  if (/(lab[-\s]?on[-\s]?a[-\s]?chip|microfluid|assay|cartridge|diagnostic|reagent|sample)/.test(lower)) {
    return [
      {
        id: "sample_assay",
        label: "Sample / Assay",
        question: "What sample, analyte, or assay workflow should this support?",
        placeholder: "Example: water sample, colorimetric nitrate assay, 3 reagent chambers...",
        suggestions: ["Water quality", "Colorimetric assay", "Fluorescence readout"],
      },
      {
        id: "instrumentation",
        label: "Reader / Detection",
        question: "What detection and control method should the reader use?",
        placeholder: "Example: LED + photodiode absorbance, heater, pressure sensor, peristaltic pump...",
        suggestions: ["Optical absorbance", "Fluorescence", "Pressure-driven flow"],
      },
      {
        id: "validation",
        label: "Validation",
        question: "What needs to be validated first?",
        placeholder: "Example: leak test, limit of detection, repeatability, contamination control...",
        suggestions: ["Leak testing", "Repeatability", "Research-only prototype"],
      },
    ];
  }

  if (/(tent|deploy|self[-\s]?assembl|fold|frame|shelter|weatherproof|structure)/.test(lower)) {
    return [
      {
        id: "environment",
        label: "Environment",
        question: "Where will this operate, and what weather or load should it survive?",
        placeholder: "Example: camping rain/wind, sandy soil, one-person field setup, 35 mph gust target...",
        suggestions: ["Rain and wind", "Field work", "Portable camping"],
      },
      {
        id: "motion_power",
        label: "Motion / Power",
        question: "How should deployment be powered and limited for safety?",
        placeholder: "Example: 12V battery, low-force servos, clutch release, manual crank fallback...",
        suggestions: ["12V battery", "Low-force actuators", "Manual release"],
      },
      {
        id: "success",
        label: "Success Criteria",
        question: "What makes version one successful?",
        placeholder: "Example: deploys in under 2 minutes, self-tensions guy lines, never pinches fabric or fingers...",
        suggestions: ["Fast deployment", "Self-tensioning", "Emergency release"],
      },
    ];
  }

  if (/(wire|wiring|schematic|pcb|sensor|relay|motor|driver|esp32|arduino|pin|gpio)/.test(lower)) {
    return [
      {
        id: "controller_modules",
        label: "Controller / Modules",
        question: "Which controller and major modules should be treated as fixed?",
        placeholder: "Example: ESP32-S3, SSD1306 OLED, SHT41, 5V relay module...",
        suggestions: ["ESP32", "Arduino", "Use generated choice"],
      },
      {
        id: "power",
        label: "Power",
        question: "What power rails, battery, or adapter constraints matter?",
        placeholder: "Example: USB-C 5V only, 3S LiPo, no mains, separate motor rail...",
        suggestions: ["USB-C 5V", "Battery powered", "No mains"],
      },
      {
        id: "outputs",
        label: "Outputs",
        question: "What should the system control or display?",
        placeholder: "Example: fan PWM, warning LED, buzzer, OLED status, pump relay...",
        suggestions: ["Display status", "Drive actuator", "Log sensor data"],
      },
    ];
  }

  return [
    {
      id: "use_case",
      label: "Use Case",
      question: "Who uses it, and where does it operate?",
      placeholder: "Example: bench prototype, outdoor field tool, wearable, classroom demo...",
      suggestions: ["Bench prototype", "Field tool", "Consumer device"],
    },
    {
      id: "constraints",
      label: "Constraints",
      question: "What hard constraints should the design preserve?",
      placeholder: "Example: USB-C only, under $100, waterproof, no enclosure, safe low voltage...",
      suggestions: ["Low voltage", "Low cost", "Weatherproof"],
    },
    {
      id: "outputs",
      label: "Artifacts",
      question: "What should Forma optimize in the first version?",
      placeholder: "Example: wiring accuracy, mechanical concept, product images, validation, BOM...",
      suggestions: ["Wiring accuracy", "Mechanical design", "Product images"],
    },
  ];
}

function normalizeHumanContextQuestions(value: any): HumanContextQuestion[] {
  const rawQuestions = Array.isArray(value?.questions) ? value.questions : Array.isArray(value) ? value : [];
  return rawQuestions
    .map((question: any): HumanContextQuestion | null => {
      if (!question || typeof question !== "object") return null;
      const id = typeof question.id === "string" && question.id.trim() ? question.id.trim() : "";
      const label = typeof question.label === "string" && question.label.trim() ? question.label.trim() : id;
      const text = typeof question.question === "string" && question.question.trim() ? question.question.trim() : "";
      if (!id || !label || !text) return null;
      return {
        id,
        label,
        question: text,
        placeholder: typeof question.placeholder === "string" ? question.placeholder : "",
        suggestions: Array.isArray(question.suggestions)
          ? question.suggestions.filter((suggestion: any) => typeof suggestion === "string" && suggestion.trim()).slice(0, 4)
          : [],
      };
    })
    .filter((question: HumanContextQuestion | null): question is HumanContextQuestion => Boolean(question));
}

async function requestHumanContextQuestions(promptText: string, workflow: string, hasImage: boolean, signal?: AbortSignal) {
  try {
    const res = await fetch(`${API_URL}/clarifying-questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
      body: JSON.stringify({
        prompt: promptText,
        workflow,
        has_image: hasImage,
        max_questions: 3,
        force: true,
      }),
    });
    if (!res.ok) throw new Error(await readApiErrorMessage(res));
    const data = await res.json();
    const questions = normalizeHumanContextQuestions(data);
    return {
      shouldAsk: Boolean(data?.should_ask) && questions.length > 0,
      reason: typeof data?.reason === "string" ? data.reason : "",
      questions,
    };
  } catch (error) {
    if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw error;
    console.warn("Context Clarifier Agent unavailable; using local fallback questions.", error);
    const questions = humanContextQuestionsForPrompt(promptText);
    return {
      shouldAsk: questions.length > 0,
      reason: "Context Clarifier Agent is using local fallback questions.",
      questions,
    };
  }
}

function humanContextPromptSection(context: PendingHumanContext, finalNotes: string) {
  const lines = context.questions.map((question) => {
    const answer = (context.answers[question.id] || "").trim() || "not specified";
    return `- ${question.label}: ${answer}`;
  });
  if (finalNotes.trim()) {
    lines.push(`- Additional human notes: ${finalNotes.trim()}`);
  }
  return [
    context.basePrompt,
    "",
    "HUMAN-IN-THE-LOOP CONTEXT:",
    ...lines,
    "",
    "Treat this human context as explicit project requirements. If something is still unspecified, say so in project docs instead of inventing hidden constraints.",
  ].join("\n");
}

function humanContextChatSummary(context: PendingHumanContext, finalNotes: string) {
  const answered = context.questions
    .map((question) => {
      const answer = (context.answers[question.id] || "").trim();
      return answer ? `${question.label}: ${answer}` : null;
    })
    .filter(Boolean);
  if (finalNotes.trim()) answered.push(`Additional notes: ${finalNotes.trim()}`);
  return answered.length ? `Context added:\n${answered.map((item) => `- ${item}`).join("\n")}` : "Build with no extra human context.";
}

function validateGenerationInput(value: string, hasImage: boolean) {
  const promptText = value.trim();
  if (!promptText) {
    return {
      isValid: hasImage,
      message: hasImage ? null : "Provide a prompt or reference image.",
    };
  }

  return {
    isValid: true,
    message: null,
  };
}

type ApiErrorDetails = {
  message: string;
  code?: string;
  reason?: string;
  provider?: string;
  model?: string;
  job_id?: string;
  debug?: Record<string, any>;
};

function normalizeApiErrorDetails(value: any, fallback: string): ApiErrorDetails {
  if (typeof value === "string" && value.trim()) {
    return { message: value.trim() };
  }

  if (Array.isArray(value)) {
    const messages = value
      .map((item: any) => item?.msg || item?.message || item?.detail)
      .filter(Boolean);
    if (messages.length) return { message: messages.join("; ") };
  }

  if (value && typeof value === "object") {
    const message =
      typeof value.message === "string"
        ? value.message
        : typeof value.detail === "string"
          ? value.detail
          : fallback;
    const reason = typeof value.reason === "string" ? value.reason : undefined;
    const provider = typeof value.provider === "string" ? value.provider : undefined;
    const model = typeof value.model === "string" ? value.model : undefined;
    return {
      message,
      code: typeof value.code === "string" ? value.code : undefined,
      reason,
      provider,
      model,
      job_id: typeof value.job_id === "string" ? value.job_id : undefined,
      debug: value.debug && typeof value.debug === "object" ? value.debug : undefined,
    };
  }

  return { message: fallback };
}

async function readApiError(response: Response): Promise<ApiErrorDetails> {
  const fallback = `Server returned ${response.status}`;
  try {
    const body = await response.json();
    if (body?.detail !== undefined) return normalizeApiErrorDetails(body.detail, fallback);
    if (body?.message !== undefined) return normalizeApiErrorDetails(body.message, fallback);
    if (body?.error !== undefined) return normalizeApiErrorDetails(body.error, fallback);
  } catch {
    // Fall through to a generic message.
  }

  return { message: fallback };
}

async function readApiErrorMessage(response: Response) {
  return (await readApiError(response)).message;
}

const communityProjects = [
  {
    title: "Portable device",
    description: "Reference design for a compact handheld product with display, controls, and enclosure notes.",
    file: "pocket_mp3_player.json",
  },
  {
    title: "Monitoring kit",
    description: "General-purpose sensing and control example with power, wiring, and enclosure guidance.",
    file: "plant_watering.json",
  },
  {
    title: "Control module",
    description: "Compact controller example with display, sensor, and validated power rails.",
    file: "smart_thermostat.json",
  },
];

type ChatRouteTransition = {
  chatId: string;
  title: string;
  projectId: string;
  error?: string | null;
};

type VideoGenerationConfig = {
  configured: boolean | null;
  reason: string | null;
};

type ImageGenerationConfig = {
  configured: boolean | null;
  provider: string | null;
  reason: string | null;
};

const workspaceTabs = [
  { id: "chat", label: "INFO", icon: Info },
  { id: "overview", label: "IMAGE", icon: Eye },
  { id: "bom", label: "BOM", icon: ShoppingBag },
  { id: "mechanical", label: "MECH", icon: Box },
  { id: "schematic", label: "WIRE", icon: Cpu },
  { id: "assembly", label: "DOCS", icon: Info },
  { id: "video", label: "VIDEO", icon: Film },
];

const workspaceTabNamespaces: Record<string, string> = {
  overview: "product.visuals",
  chat: "project.chat",
  bom: "product.bom",
  mechanical: "product.mech",
  schematic: "product.electrical",
  assembly: "project.docs",
  video: "product.visuals.video",
  jobs: "project.history.jobs",
  logs: "project.runtime.logs",
};

function normalizeTab(tab: string | null) {
  if (!tab) return null;
  const aliases: Record<string, string> = {
    image: "overview",
    mech: "mechanical",
    wire: "schematic",
    docs: "assembly",
  };
  const normalized = aliases[tab] || tab;
  return workspaceTabs.some((item) => item.id === normalized) ? normalized : null;
}

function workspaceTabMeta(tab: string | null) {
  const normalized = normalizeTab(tab);
  return workspaceTabs.find((item) => item.id === normalized) || workspaceTabs.find((item) => item.id === "chat") || workspaceTabs[0];
}

function workspaceNamespaceForTab(tab: string | null) {
  const meta = workspaceTabMeta(tab);
  return workspaceTabNamespaces[meta.id] || meta.id;
}

function withProjectResponseMetadata(ir: any, response: any) {
  if (!ir) return ir;
  const timingMetadata = generationTimingMetadataFromJob(response?.job);
  return {
    ...ir,
    assembly_metadata: {
      ...(ir.assembly_metadata || {}),
      project_id: ir.assembly_metadata?.project_id || response?.project_id,
      chat_id: ir.assembly_metadata?.chat_id || response?.chat_id,
      can_chat: Boolean(ir.assembly_metadata?.can_chat ?? ir.assembly_metadata?.canChat ?? response?.can_chat ?? response?.canChat),
      frontend_job_id: ir.assembly_metadata?.frontend_job_id || response?.job_id,
      source_prompt: ir.assembly_metadata?.source_prompt || response?.prompt,
      ...timingMetadata,
    },
  };
}

function timestampMs(value: any): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

function durationSecondsBetween(startValue: any, endValue: any): number | null {
  const start = timestampMs(startValue);
  const end = timestampMs(endValue);
  if (start === null || end === null || end < start) return null;
  return Math.max(1, Math.round((end - start) / 1000));
}

function generationTimingMetadataFromJob(job: A2AJob | null | undefined): Record<string, any> {
  const seconds = durationSecondsBetween(job?.started_at, job?.completed_at);
  if (seconds === null) return {};
  return {
    total_generation_time_seconds: seconds,
    total_generation_started_at: job?.started_at || null,
    total_generation_completed_at: job?.completed_at || null,
  };
}

function formatDurationSeconds(value: any) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  const totalSeconds = Math.max(1, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  if (hours) return `${hours}h ${minutes}m ${remainingSeconds}s`;
  if (minutes) return `${minutes}m ${remainingSeconds}s`;
  return `${remainingSeconds}s`;
}

function formatTotalGenerationTime(metadata: Record<string, any> = {}) {
  const explicitSeconds =
    metadata.total_generation_time_seconds ??
    metadata.total_generation_duration_seconds ??
    metadata.generation_duration_seconds ??
    metadata.duration_seconds;
  const formatted = formatDurationSeconds(explicitSeconds);
  if (formatted !== "-") return formatted;
  const derivedSeconds = durationSecondsBetween(
    metadata.total_generation_started_at || metadata.generation_started_at || metadata.started_at,
    metadata.total_generation_completed_at || metadata.generation_completed_at || metadata.completed_at
  );
  return formatDurationSeconds(derivedSeconds);
}

function projectIdFromIR(ir: any) {
  return ir?.assembly_metadata?.project_id || null;
}

function chatIdFromIR(ir: any) {
  return ir?.assembly_metadata?.chat_id || null;
}

function canChatWithProjectIR(ir: any) {
  return Boolean(ir?.assembly_metadata?.can_chat ?? ir?.assembly_metadata?.canChat);
}

function chatIdFromJob(job: A2AJob) {
  const rawChatId = job.payload?.chat_id || job.result_summary?.chat_id;
  return typeof rawChatId === "string" ? rawChatId.trim() : "";
}

function projectRoute(projectId: string) {
  return `/project/${encodeURIComponent(projectId)}`;
}

function chatRoute(chatId: string) {
  return `/chat/${encodeURIComponent(chatId)}`;
}

function safeDecodeProjectId(projectId: string) {
  try {
    return decodeURIComponent(projectId);
  } catch {
    return projectId;
  }
}

function safeDecodeChatId(chatId: string) {
  try {
    return decodeURIComponent(chatId);
  } catch {
    return chatId;
  }
}

type HomeProps = {
  routeProjectId?: string | null;
  routeChatId?: string | null;
  showDeveloperTools?: boolean;
  homeView?: "chat" | "projects" | "my-projects" | "jobs" | "logs";
};

export function FormaWorkspace({
  routeProjectId = null,
  routeChatId = null,
  showDeveloperTools = DEFAULT_SHOW_DEVELOPER_TOOLS,
  homeView = "chat",
}: HomeProps = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const pathnameChatId = pathname.match(/^\/chat\/([^/]+)\/?$/)?.[1] || null;
  const pathnameProjectId = pathname.match(/^\/project\/([^/]+)\/?$/)?.[1] || null;
  const currentRouteChatId = pathnameChatId || (pathname === null ? routeChatId : null);
  const currentRouteProjectId = pathnameProjectId || (pathname === null ? routeProjectId : null);
  const {
    authRequired,
    getToken,
    identityKey: authIdentityKey,
    isLoaded: authLoaded,
    isSignedIn,
    openSignIn,
    userImageUrl,
  } = useFormaAuth();
  const chatStorageScope = authRequired ? `identity:${authIdentityKey}` : "local";
  const [prompt, setPrompt] = useState("");
  const [activeChatId, setActiveChatId] = useState(() => currentRouteChatId ? safeDecodeChatId(currentRouteChatId) : newBuildChatId());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => initialChatMessages());
  const [pendingHumanContext, setPendingHumanContext] = useState<PendingHumanContext | null>(null);
  const [chatThreads, setChatThreads] = useState<Record<string, ChatMessage[]>>({});
  const [projectChatInput, setProjectChatInput] = useState("");
  const [projectChatVisible, setProjectChatVisible] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [activeGeneration, setActiveGeneration] = useState<ActiveGenerationState | null>(null);
  const [activeTab, setActiveTab] = useState("chat");
  const [projectIR, setProjectIR] = useState<any>(null);
  const [projectHistory, setProjectHistory] = useState<any[]>([]);
  const [myProjectHistory, setMyProjectHistory] = useState<any[]>([]);
  const [projectHistoryLoaded, setProjectHistoryLoaded] = useState(false);
  const [myProjectHistoryLoaded, setMyProjectHistoryLoaded] = useState(false);
  const [localChatItems, setLocalChatItems] = useState<ChatListItem[]>([]);
  const [privateChatItems, setPrivateChatItems] = useState<ChatListItem[]>([]);
  const [privateChatsLoaded, setPrivateChatsLoaded] = useState(false);
  const [chatIndexLoaded, setChatIndexLoaded] = useState(false);
  const [sessionChatItems, setSessionChatItems] = useState<ChatListItem[]>([]);
  const [projectGalleryImages, setProjectGalleryImages] = useState<Record<string, ProjectImageCandidate | null>>({});
  const [visibleProjectGalleryIds, setVisibleProjectGalleryIds] = useState<string[]>([]);
  const [routeProjectError, setRouteProjectError] = useState<string | null>(null);
  const [chatRouteTransition, setChatRouteTransition] = useState<ChatRouteTransition | null>(() => (
    currentRouteChatId && !currentRouteProjectId
      ? {
          chatId: safeDecodeChatId(currentRouteChatId),
          title: "Opening chat",
          projectId: "",
          error: null,
        }
      : null
  ));
  const [serverStatus, setServerStatus] = useState<"connected" | "disconnected">(
    () => lastKnownServerStatus || "disconnected"
  );
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [generationInputNotice, setGenerationInputNotice] = useState<string | null>(null);
  const [videoGenerationConfig, setVideoGenerationConfig] = useState<VideoGenerationConfig>({
    configured: null,
    reason: null,
  });
  const [videoSelfCorrectionConfig, setVideoSelfCorrectionConfig] = useState<VideoGenerationConfig>({
    configured: null,
    reason: null,
  });
  const [imageGenerationConfig, setImageGenerationConfig] = useState<ImageGenerationConfig>({
    configured: null,
    provider: null,
    reason: null,
  });
  const [imageGenerationConfigLoaded, setImageGenerationConfigLoaded] = useState(false);
  const [generateProductImage, setGenerateProductImage] = useState(false);
  const [generationWorkflow, setGenerationWorkflow] = useState(DEFAULT_WORKFLOW_ID);
  const [generationWorkflows, setGenerationWorkflows] = useState<GenerationWorkflowOption[]>(defaultGenerationWorkflows);
  const [agentPipelineSteps, setAgentPipelineSteps] = useState<AgentPipelineStep[]>(defaultAgentPipelineSteps);
  const [generationLlms, setGenerationLlms] = useState<GenerationLlmOption[]>(() => authRequired ? [] : defaultGenerationLlms);
  const [generationLlmKeyValue, setGenerationLlmKeyValue] = useState(() => authRequired ? "" : generationLlmKey(defaultGenerationLlms[0]));
  const [generationLlmsLoaded, setGenerationLlmsLoaded] = useState(!authRequired);
  const [mechElectricalActive, setMechElectricalActive] = useState(true);
  const [mechToggles, setMechToggles] = useState({
    structural: true,
    enclosure: true,
    mechanism: true,
    misc: false,
    print: true,
    bodyRotation: false,
  });

  const fileInputRefSidebar = useRef<HTMLInputElement>(null);
  const fileInputRefCenter = useRef<HTMLInputElement>(null);
  const projectsSectionRef = useRef<HTMLElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const projectChatEndRef = useRef<HTMLDivElement>(null);
  const chatPersistenceTimersRef = useRef<Record<string, number>>({});
  const generationLlmRequestIdRef = useRef(0);
  const pipelineStepsRequestIdRef = useRef(0);
  const pipelineStepsAbortRef = useRef<AbortController | null>(null);
  const pipelineStepsRequestStartedRef = useRef(false);
  const pipelineStepsLastRequestedWorkflowRef = useRef<string | null>(null);
  const recoveryJobMissesRef = useRef(new Map<string, { misses: number; retryAfter: number }>());
  const activeGenerationRef = useRef<ActiveGenerationRun | null>(null);
  const visibleChatSourceProjects = myProjectHistory;
  const visibleChatSourceItems = useMemo(
    () => authRequired
      ? mergeChatListItems(sessionChatItems, privateChatItems)
      : mergeChatListItems(privateChatItems, localChatItems),
    [authRequired, localChatItems, privateChatItems, sessionChatItems]
  );
  const chatListItems = useMemo(
    () => buildChatListItems(visibleChatSourceProjects, visibleChatSourceItems),
    [visibleChatSourceProjects, visibleChatSourceItems]
  );
  const projectGalleryItems = useMemo(
    () => buildProjectGalleryItems(
      projectHistory,
      projectGalleryImages
    ).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, isSignedIn, projectHistory, projectGalleryImages]
  );
  const myProjectGalleryItems = useMemo(
    () => buildProjectGalleryItems(
      mergeProjectRecords(myProjectHistory, projectRecordsFromChatItems(chatListItems)),
      projectGalleryImages
    ).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, chatListItems, isSignedIn, myProjectHistory, projectGalleryImages]
  );
  const chatHistoryLoaded = myProjectHistoryLoaded && privateChatsLoaded;
  const projectsPageLoading = !projectHistoryLoaded;
  const myProjectsPageLoading = (authRequired && !authLoaded)
    || !myProjectHistoryLoaded
    || !privateChatsLoaded
    || !chatIndexLoaded;
  const handleVisibleProjectGalleryIdsChange = useCallback((projectIds: string[]) => {
    setVisibleProjectGalleryIds((current) => (
      sameStringList(current, projectIds) ? current : projectIds
    ));
  }, []);
  const chatMessageScrollKey = useMemo(
    () => `${activeChatId || ""}:${chatMessageIdentityKey(chatMessages)}`,
    [activeChatId, chatMessages]
  );
  const projectChatMessageScrollKey = useMemo(() => {
    const chatId = projectIR ? (chatIdFromIR(projectIR) || projectIdFromIR(projectIR) || activeChatId) : activeChatId;
    const messages = chatId ? chatThreads[chatId] || [] : [];
    return `${chatId || ""}:${chatMessageIdentityKey(messages)}`;
  }, [activeChatId, chatThreads, projectIR]);
  const generationInputValidation = useMemo(
    () => validateGenerationInput(pendingHumanContext?.basePrompt || prompt, Boolean(selectedImage)),
    [pendingHumanContext, prompt, selectedImage]
  );
  const hasGenerationInput = Boolean(prompt.trim() || selectedImage || pendingHumanContext);
  const selectedGenerationWorkflow = useMemo(
    () => generationWorkflows.find((workflow) => workflow.id === generationWorkflow) || generationWorkflows[0] || defaultGenerationWorkflows[0],
    [generationWorkflow, generationWorkflows]
  );
  const webResearchEnabled = generationWorkflow === WEB_RESEARCH_WORKFLOW_ID;
  const selectedWorkflowUsesExternalSources = Boolean(
    webResearchEnabled &&
    (
      selectedGenerationWorkflow?.uses_external_sources ||
      selectedGenerationWorkflow?.uses_web_research ||
      selectedGenerationWorkflow?.uses_firecrawl_mcp
    )
  );
  const selectedGenerationLlm = useMemo(
    () => generationLlms.find((option) => generationLlmKey(option) === generationLlmKeyValue) || generationLlms[0] || null,
    [generationLlmKeyValue, generationLlms]
  );
  const generationLlmsReady = Boolean(selectedGenerationLlm);
  const needsGenerationProvider = generationLlmsLoaded && !generationLlmsReady && (!authRequired || authLoaded);
  const needsImageProvider = imageGenerationConfigLoaded && imageGenerationConfig.configured !== true && (!authRequired || authLoaded);
  const visibleGenerationInputNotice =
    generationInputNotice ||
    (needsGenerationProvider
      ? "No model provider is active. Add and enable one in Settings before building."
      : (prompt.trim() || pendingHumanContext) && !generationInputValidation.isValid
        ? generationInputValidation.message
        : null);
  const appendChatMessage = (message: Omit<ChatMessage, "id" | "timestamp"> & { id?: string }) => {
    const nextMessage: ChatMessage = {
      id: message.id || newChatMessageId(),
      role: message.role,
      content: message.content,
      status: message.status || "idle",
      projectId: message.projectId,
      pipelineProgress: message.pipelineProgress || null,
      timestamp: chatTimestamp(),
    };
    setChatMessages((current) => [...current, nextMessage]);
    return nextMessage.id;
  };
  const updateChatMessage = (id: string, patch: Partial<Omit<ChatMessage, "id">>) => {
    setChatMessages((current) =>
      current.map((message) =>
        message.id === id
          ? {
              ...message,
              ...patch,
              timestamp: patch.timestamp || chatTimestamp(),
            }
          : message
      )
    );
  };

  const ensureChatThread = (projectId: string | null, ir: any, sourcePrompt?: string | null) => {
    if (!projectId) return;
    const chatId = chatIdFromIR(ir) || projectId;
    setActiveChatId(chatId);
    setChatThreads((current) => {
      if (current[chatId]?.length) return current;
      const storedMessages = readStoredChatThread(chatId, projectId, chatStorageScope);
      const nextMessages = storedMessages.length
        ? storedMessages
        : initialProjectChatMessages(projectId, ir?.overview?.title || "Project", sourcePrompt);
      writeStoredChatThread(chatId, nextMessages, chatStorageScope);
      persistChatThread(chatId, nextMessages, ir?.overview?.title || null);
      return {
        ...current,
        [chatId]: nextMessages,
      };
    });
  };

  const appendThreadMessage = (chatId: string | null, message: Omit<ChatMessage, "id" | "timestamp"> & { id?: string }) => {
    if (!chatId) return "";
    const nextMessage: ChatMessage = {
      id: message.id || newChatMessageId(),
      role: message.role,
      content: message.content,
      status: message.status || "idle",
      projectId: message.projectId,
      pipelineProgress: message.pipelineProgress || null,
      timestamp: chatTimestamp(),
    };
    setChatThreads((current) => {
      const nextMessages = [...(current[chatId] || []), nextMessage].slice(-MAX_PROJECT_CHAT_MESSAGES);
      writeStoredChatThread(chatId, nextMessages, chatStorageScope);
      persistChatThread(chatId, nextMessages);
      return {
        ...current,
        [chatId]: nextMessages,
      };
    });
    return nextMessage.id;
  };

  const updateThreadMessage = (chatId: string | null, messageId: string, patch: Partial<Omit<ChatMessage, "id">>) => {
    if (!chatId || !messageId) return;
    setChatThreads((current) => {
      const currentMessages = current[chatId] || [];
      const nextMessages = currentMessages.map((message) =>
        message.id === messageId
          ? {
              ...message,
              ...patch,
              timestamp: patch.timestamp || chatTimestamp(),
            }
          : message
      );
      writeStoredChatThread(chatId, nextMessages, chatStorageScope);
      persistChatThread(chatId, nextMessages);
      return {
        ...current,
        [chatId]: nextMessages,
      };
    });
  };

  const applyChatPipelineProgressFromJob = (
    messageId: string,
    job: A2AJob | null,
    seedProgress: AgentPipelineProgress,
    includeImage: boolean
  ) => {
    if (!messageId || !job) return;
    setChatMessages((current) => {
      let changed = false;
      const nextMessages = current.map((message) => {
        if (message.id !== messageId) return message;
        const nextMessage = mergeMessagePipelineProgressFromJob(message, job, seedProgress, includeImage);
        if (nextMessage !== message) changed = true;
        return nextMessage;
      });
      return changed ? nextMessages : current;
    });
  };

  const applyThreadPipelineProgressFromJob = (
    chatId: string | null,
    messageId: string,
    job: A2AJob | null,
    seedProgress: AgentPipelineProgress,
    includeImage: boolean
  ) => {
    if (!chatId || !messageId || !job) return;
    setChatThreads((current) => {
      const currentMessages = current[chatId] || [];
      let changed = false;
      const nextMessages = currentMessages.map((message) => {
        if (message.id !== messageId) return message;
        const nextMessage = mergeMessagePipelineProgressFromJob(message, job, seedProgress, includeImage);
        if (nextMessage !== message) changed = true;
        return nextMessage;
      });
      if (!changed) return current;
      writeStoredChatThread(chatId, nextMessages, chatStorageScope);
      persistChatThread(chatId, nextMessages);
      return {
        ...current,
        [chatId]: nextMessages,
      };
    });
  };

  const rememberChatItem = (item: Partial<ChatListItem> & { chatId: string }) => {
    const normalizedItem = normalizeChatListItem(item);
    if (authRequired) {
      if (normalizedItem) {
        setSessionChatItems((current) => mergeChatListItems([normalizedItem], current));
      }
    }
    setLocalChatItems((current) => {
      const nextItems = upsertChatListItem(current, item);
      writeStoredChatIndex(nextItems, chatStorageScope);
      return nextItems;
    });
    if (normalizedItem && (!authRequired || isSignedIn)) {
      const messages = chatThreads[item.chatId]
        || (activeChatId === item.chatId ? chatMessages : readStoredChatThread(item.chatId, null, chatStorageScope));
      persistChatThread(item.chatId, messages, normalizedItem.title);
    }
  };

  const rememberProjectRecord = (record: any) => {
    const normalizedRecord = normalizeProjectHistoryRecord(record);
    if (!normalizedRecord) return;
    const mergeProject = (projects: any[]) => (
      [normalizedRecord, ...projects.filter((project: any) => project?.project_id !== normalizedRecord.project_id)]
        .sort((left: any, right: any) => {
          const leftTime = Date.parse(left.created_at || "");
          const rightTime = Date.parse(right.created_at || "");
          return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
        })
    );
    setProjectHistory((projects) => (
      normalizedRecord.visibility === "public"
        ? mergeProject(projects)
        : projects.filter((project: any) => project?.project_id !== normalizedRecord.project_id)
    ));
    setMyProjectHistory(mergeProject);
    setMyProjectHistoryLoaded(true);
  };

  const detachMissingProjectFromChat = (chatId: string, projectId: string, title?: string | null) => {
    if (!chatId || !projectId) return;
    setLocalChatItems((current) => {
      const existing = current.find((item) => item.chatId === chatId);
      const nextItem: ChatListItem = {
        chatId,
        title: existing?.title?.trim() || title?.trim() || NEW_PROJECT_TITLE,
        projectId: "",
        createdAt: existing?.createdAt || chatTimestamp(),
        projectCount: 0,
      };
      const nextItems = [nextItem, ...current.filter((item) => item.chatId !== chatId)]
        .sort((left, right) => {
          const leftTime = Date.parse(left.createdAt || "");
          const rightTime = Date.parse(right.createdAt || "");
          return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
        })
        .slice(0, MAX_CHAT_INDEX_ITEMS);
      writeStoredChatIndex(nextItems, chatStorageScope);
      return nextItems;
    });
  };

  const updateHumanContextAnswer = (questionId: string, value: string) => {
    setPendingHumanContext((current) =>
      current
        ? {
            ...current,
            answers: {
              ...current.answers,
              [questionId]: value,
            },
          }
        : current
    );
  };
  const clearHumanContextCheckpoint = () => {
    if (pendingHumanContext) setPrompt(pendingHumanContext.basePrompt);
    setPendingHumanContext(null);
  };

  const requireSignedInForGeneration = async () => {
    if (!authRequired || isSignedIn) return true;
    setGenerationInputNotice("Sign in to talk in chat and make projects.");
    openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" });
    return false;
  };

  const generationRequestHeaders = useCallback(async () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (!authRequired) return headers;
    const token = await getToken();
    if (!token) {
      openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" });
      throw new Error("Sign in to talk in chat and make projects.");
    }
    headers.Authorization = `Bearer ${token}`;
    return headers;
  }, [authRequired, getToken, openSignIn]);

  const optionalAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!isSignedIn) return {};
    try {
      const token = await getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, [getToken, isSignedIn]);

  const { isAdmin, loaded: adminSessionLoaded } = useAdminSession({
    apiUrl: API_URL,
    getHeaders: optionalAuthHeaders,
    readError: readApiErrorMessage,
    enabled: authRequired,
    authRequired,
    authReady: !authRequired || authLoaded,
    signedIn: isSignedIn,
    requestScopeKey: authIdentityKey,
  });
  const canViewJobs = !authRequired || isAdmin;
  const canViewAdminTools = !authRequired || showDeveloperTools || isAdmin;
  const sidebarChatsLoading = !chatIndexLoaded || !chatHistoryLoaded;
  const sidebarJobsPending = authRequired && !adminSessionLoaded;
  const jobsViewActive = canViewJobs && (homeView === "jobs" || Boolean(projectIR && activeTab === "jobs"));
  const logsViewActive = canViewAdminTools && (homeView === "logs" || Boolean(projectIR && activeTab === "logs"));
  const {
    jobs: a2aJobs,
    loading: jobsLoading,
    error: jobsError,
    statusFilter: jobStatusFilter,
    setStatusFilter: setJobStatusFilter,
    lastUpdatedAt: jobsLastUpdatedAt,
    refresh: fetchA2aJobs,
    fetchJob: fetchA2aJob,
  } = useJobs({
    apiUrl: API_URL,
    getHeaders: generationRequestHeaders,
    readError: readApiErrorMessage,
    enabled: jobsViewActive,
    requestScopeKey: authIdentityKey,
    pollIntervalMs: JOB_POLL_INTERVAL_MS,
  });
  const {
    logs: backendLogs,
    loading: logsLoading,
    error: logsError,
    lastUpdatedAt: logsLastUpdatedAt,
    refresh: fetchBackendLogs,
  } = useBackendLogs({
    apiUrl: API_URL,
    getHeaders: generationRequestHeaders,
    readError: readApiErrorMessage,
    enabled: logsViewActive,
    pollIntervalMs: LOG_POLL_INTERVAL_MS,
  });
  const {
    models: videoModels,
    loading: videoModelsLoading,
    error: videoModelsError,
    selectedModel: selectedVideoModel,
    setSelectedModel: setSelectedVideoModel,
    aspectRatios: videoAspectRatios,
    aspectRatio: videoAspectRatio,
    setAspectRatio: setVideoAspectRatio,
  } = useVideoModels({
    apiUrl: API_URL,
    enabled: Boolean(projectIR && activeTab === "video"),
    onAvailabilityChange: setVideoGenerationConfig,
  });
  const waitingGenerationJobKey = useMemo(() => {
    const jobIds = new Set<string>();
    const collect = (messages: ChatMessage[]) => {
      messages.forEach((message) => {
        const jobId = message.status === "loading" ? message.pipelineProgress?.jobId : null;
        if (jobId && jobId !== activeGeneration?.jobId) jobIds.add(jobId);
      });
    };
    collect(chatMessages);
    Object.values(chatThreads).forEach(collect);
    return Array.from(jobIds).join("\n");
  }, [activeGeneration?.jobId, chatMessages, chatThreads]);


  const persistChatThread = (chatId: string | null, messages: ChatMessage[], explicitTitle?: string | null) => {
    if ((authRequired && !isSignedIn) || !chatId || typeof window === "undefined") return;
    const nextMessages = persistableChatMessages(messages);
    if (!chatHasStarted(nextMessages)) return;
    const title = explicitTitle?.trim() || chatTitleFromMessages(nextMessages);
    const existingTimer = chatPersistenceTimersRef.current[chatId];
    if (existingTimer) window.clearTimeout(existingTimer);
    chatPersistenceTimersRef.current[chatId] = window.setTimeout(async () => {
      delete chatPersistenceTimersRef.current[chatId];
      try {
        const res = await fetch(`${API_URL}/chats/${encodeURIComponent(chatId)}`, {
          method: "PUT",
          headers: await generationRequestHeaders(),
          body: JSON.stringify({
            chat_id: chatId,
            title,
            messages: nextMessages,
          }),
        });
        if (!res.ok) throw new Error(await readApiErrorMessage(res));
        const savedChat = await res.json();
        setPrivateChatItems((current) => mergeChatListItems(normalizePrivateChatItems([savedChat]), current));
      } catch (error) {
        console.error("Error saving private chat", error);
      }
    }, 300);
  };

  const goHome = () => {
    setChatRouteTransition(null);
    setProjectIR(null);
    setActiveTab("chat");
    router.push("/");
  };

  const startNewProjectChat = () => {
    const guardChatId = projectIR ? (chatIdFromIR(projectIR) || projectIdFromIR(projectIR) || activeChatId) : activeChatId;
    const guardMessages = projectIR && guardChatId ? chatThreads[guardChatId] || [] : chatMessages;
    const guardItem = chatListItems.find((item) => item.chatId === guardChatId);
    const currentChatStarted = Boolean(
      projectIR ||
      chatHasStarted(guardMessages) ||
      guardItem?.projectId ||
      guardItem?.projectCount
    );
    if (!currentChatStarted) return;

    const nextChatId = newBuildChatId();
    setActiveChatId(nextChatId);
    rememberChatItem({
      chatId: nextChatId,
      title: NEW_PROJECT_TITLE,
      projectId: "",
      createdAt: chatTimestamp(),
      projectCount: 0,
    });
    setChatMessages(initialChatMessages());
    setPrompt("");
    setProjectChatInput("");
    setPendingHumanContext(null);
    setGenerationInputNotice(null);
    setSelectedImage(null);
    setChatRouteTransition(null);
    setProjectIR(null);
    setActiveTab("chat");
    router.push("/");
  };

  const openChatItem = (item: ChatListItem) => {
    if (authRequired && !isSignedIn) {
      openSignIn({ redirectUrl: typeof window !== "undefined" ? chatRoute(item.chatId) : "/" });
      return;
    }
    setActiveChatId(item.chatId);
    setActiveTab("chat");
    const storedMessages = readStoredChatThread(item.chatId, null, chatStorageScope);
    if (storedMessages.length) {
      setChatThreads((current) => ({ ...current, [item.chatId]: storedMessages }));
      setChatMessages(storedMessages);
    }
    const projectAlreadyLoaded = Boolean(
      item.projectId && projectIdFromIR(projectIR) === item.projectId
    );
    setChatRouteTransition(
      item.projectId && !projectAlreadyLoaded
        ? { chatId: item.chatId, title: item.title || "Opening chat", projectId: item.projectId, error: null }
        : null
    );
    if (!item.projectId) setProjectIR(null);
    syncChatRoute(item.chatId);
  };

  const openChatById = (chatId: string) => {
    const item = chatListItems.find((candidate) => candidate.chatId === chatId);
    if (item) {
      openChatItem(item);
      return;
    }
    setActiveChatId(chatId);
    setActiveTab("chat");
    setChatRouteTransition({
      chatId,
      title: "Opening chat",
      projectId: "",
      error: null,
    });
    router.push(chatRoute(chatId));
  };

  const syncProjectRoute = (projectId: string, mode: "push" | "replace" = "push") => {
    const nextPath = projectRoute(projectId);
    if (window.location.pathname === nextPath) return;
    if (mode === "replace") {
      router.replace(nextPath);
    } else {
      router.push(nextPath);
    }
  };

  const syncChatRoute = (chatId: string, mode: "push" | "replace" = "push") => {
    if (typeof window === "undefined" || !chatId) return;
    const nextPath = chatRoute(chatId);
    if (window.location.pathname === nextPath) return;
    if (mode === "replace") {
      window.history.replaceState(window.history.state, "", nextPath);
    } else {
      window.history.pushState(window.history.state, "", nextPath);
    }
  };

  useLayoutEffect(() => {
    setLocalChatItems(authRequired ? [] : readStoredChatIndex(chatStorageScope));
    setChatIndexLoaded(true);
    setChatMessages((current) => (
      current.length === 1 && current[0]?.id === "assistant-welcome"
        ? [{ ...current[0], timestamp: chatTimestamp() }]
        : current
    ));
  }, [authRequired, chatStorageScope]);

  useEffect(() => {
    if (homeView !== "projects") return;
    void fetchProjectHistory();
    // Public gallery data becomes critical only when its route is active.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeView]);

  useDeferredTask(() => {
    if (!projectHistoryLoaded) void fetchProjectHistory();
  }, {
    delayMs: 1200,
    enabled: homeView !== "projects" && !projectHistoryLoaded,
    taskKey: homeView,
    timeoutMs: 1800,
  });

  useDeferredTask(() => {
    void checkServerStatus();
  }, { delayMs: 150, timeoutMs: 700 });

  useDeferredTask(() => {
    void fetchGenerationWorkflows();
  }, { delayMs: 300, timeoutMs: 900 });

  useDeferredTask(() => {
    if (!authRequired) void fetchRuntimeConfig();
  }, { delayMs: 500, enabled: !authRequired, timeoutMs: 1100 });

  useEffect(() => {
    if (!authRequired || !authLoaded) return;
    generationLlmRequestIdRef.current += 1;
    setGenerationLlmsLoaded(false);
    setGenerationLlms([]);
    setGenerationLlmKeyValue("");
    setImageGenerationConfig({ configured: null, provider: null, reason: null });
    setImageGenerationConfigLoaded(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authIdentityKey, authLoaded, authRequired, isSignedIn]);

  useDeferredTask(() => {
    // Reload BYOK providers once Clerk has resolved the current user. The
    // initial production render cannot safely query user integrations yet.
    void fetchRuntimeConfig();
  }, {
    delayMs: 250,
    enabled: authRequired && authLoaded,
    taskKey: authIdentityKey,
    timeoutMs: 1000,
  });

  useEffect(() => {
    if (authRequired && !authLoaded) {
      setMyProjectHistoryLoaded(false);
      setPrivateChatsLoaded(false);
      return;
    }
    setMyProjectHistoryLoaded(false);
    setPrivateChatsLoaded(false);
    void fetchMyProjectHistory();
    void fetchPrivateChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authIdentityKey, authLoaded, authRequired, isSignedIn]);

  useDeferredTask(() => {
    void fetchAgentPipelineSteps(generationWorkflow);
  }, { delayMs: 1100, timeoutMs: 1400 });

  useEffect(() => {
    if (!pipelineStepsRequestStartedRef.current) return;
    if (pipelineStepsLastRequestedWorkflowRef.current === generationWorkflow) return;
    void fetchAgentPipelineSteps(generationWorkflow);
    // The first request is staged by useDeferredTask; later workflow changes
    // load immediately and cancel any response for the previous workflow.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationWorkflow]);

  useEffect(() => {
    if (!isLoading) return;

    const intervalId = window.setInterval(() => {
      const nowMs = Date.now();
      setChatMessages((current) => advancePipelineMessages(current, nowMs));
      setChatThreads((current) => {
        let changed = false;
        const nextThreads: Record<string, ChatMessage[]> = {};
        Object.entries(current).forEach(([chatId, messages]) => {
          const nextMessages = advancePipelineMessages(messages, nowMs);
          if (nextMessages !== messages) changed = true;
          nextThreads[chatId] = nextMessages;
        });
        return changed ? nextThreads : current;
      });
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isLoading]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatMessageScrollKey]);

  useEffect(() => {
    projectChatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [projectChatMessageScrollKey]);

  const checkServerStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/`);
      const nextStatus = res.ok ? "connected" : "disconnected";
      lastKnownServerStatus = nextStatus;
      setServerStatus(nextStatus);
    } catch {
      lastKnownServerStatus = "disconnected";
      setServerStatus("disconnected");
    }
  };

  const fetchRuntimeConfig = async () => {
    const requestId = ++generationLlmRequestIdRef.current;
    const requestIsCurrent = () => generationLlmRequestIdRef.current === requestId;
    try {
      const applyActiveUserLlms = async () => {
        try {
          const integrationsResponse = await fetch(`${API_URL}/user/integrations`, {
            cache: "no-store",
            headers: await optionalAuthHeaders(),
          });
          if (!integrationsResponse.ok) return false;
          const integrationsPayload = (await integrationsResponse.json()) as IntegrationsPayload;
          if (!requestIsCurrent()) return false;
          const activeLlms = activeLlmsFromIntegrations(integrationsPayload, defaultGenerationLlms, generationLlmLabel);
          if (activeLlms.length > 0) {
            setGenerationLlms(activeLlms);
            setGenerationLlmKeyValue((current) => (activeLlms.some((option) => generationLlmKey(option) === current) ? current : generationLlmKey(activeLlms[0])));
          } else {
            setGenerationLlms([]);
            setGenerationLlmKeyValue("");
          }
          return true;
        } catch (error) {
          console.warn("Unable to load active user LLM settings", error);
          return false;
        }
      };
      const appliedActiveUserLlms = await applyActiveUserLlms();
      if (!requestIsCurrent()) return;
      const res = await fetch(`${API_URL}/debug/config`, {
        headers: await optionalAuthHeaders(),
      });
      if (!res.ok) return;

      const config = await res.json();
      if (!requestIsCurrent()) return;
      if (config.video_generation) {
        setVideoGenerationConfig({
          configured: Boolean(config.video_generation.configured),
          reason: typeof config.video_generation.reason === "string" ? config.video_generation.reason : null,
        });
      }
      if (config.video_self_correction) {
        setVideoSelfCorrectionConfig({
          configured: Boolean(config.video_self_correction.configured),
          reason: typeof config.video_self_correction.reason === "string" ? config.video_self_correction.reason : null,
        });
      }
      if (config.image_output) {
        const imageOutput = config.image_output;
        const imageProviderConfigured = Boolean(imageOutput.request_capable ?? imageOutput.configured);
        setImageGenerationConfig({
          configured: imageProviderConfigured,
          provider: typeof imageOutput.request_provider === "string"
            ? imageOutput.request_provider
            : typeof imageOutput.provider === "string"
              ? imageOutput.provider
              : null,
          reason: typeof imageOutput.reason === "string" ? imageOutput.reason : null,
        });
        if (!imageProviderConfigured) setGenerateProductImage(false);
      }
      if (Array.isArray(config.workflows) && config.workflows.length > 0) {
        setGenerationWorkflows(config.workflows);
      }
      if (appliedActiveUserLlms) return;
      const runtime = config.runtime || {};
      const allowedProviders = Array.isArray(runtime.allowed_providers) ? runtime.allowed_providers.map((item: any) => String(item)) : null;
      const configuredProviders = Array.isArray(runtime.configured_providers) ? runtime.configured_providers.map((item: any) => String(item)) : null;
      const runtimeProvider = typeof runtime.runtime_provider === "string" ? runtime.runtime_provider : null;
      const runtimeModel = typeof runtime.runtime_model === "string" ? runtime.runtime_model : null;
      const providerCanAppear = (provider: string) =>
        (!allowedProviders || allowedProviders.includes(provider)) &&
        (!configuredProviders || configuredProviders.includes(provider));
      const filteredLlms = defaultGenerationLlms.filter((option) => providerCanAppear(option.provider));
      const nextLlms = [...filteredLlms];
      if (
        runtimeProvider &&
        runtimeModel &&
        providerCanAppear(runtimeProvider) &&
        !nextLlms.some((option) => option.provider === runtimeProvider && option.model === runtimeModel)
      ) {
        nextLlms.unshift({
          provider: runtimeProvider,
          model: runtimeModel,
          label: generationLlmLabel(runtimeProvider, runtimeModel),
        });
      }
      if (nextLlms.length > 0) {
        setGenerationLlms(nextLlms);
        setGenerationLlmKeyValue((current) => (nextLlms.some((option) => generationLlmKey(option) === current) ? current : generationLlmKey(nextLlms[0])));
      } else {
        setGenerationLlms([]);
        setGenerationLlmKeyValue("");
      }
    } catch (e) {
      if (requestIsCurrent()) console.error("Error fetching runtime config", e);
    } finally {
      if (requestIsCurrent()) {
        setGenerationLlmsLoaded(true);
        setImageGenerationConfigLoaded(true);
      }
    }
  };

  const fetchGenerationWorkflows = async () => {
    try {
      const res = await fetch(`${API_URL}/workflows`);
      if (!res.ok) return;
      const workflows = await res.json();
      if (Array.isArray(workflows) && workflows.length > 0) {
        setGenerationWorkflows(workflows);
        setGenerationWorkflow((current) => workflows.some((workflow: GenerationWorkflowOption) => workflow.id === current) ? current : workflows[0].id);
      }
    } catch (e) {
      console.error("Error fetching generation workflows", e);
    }
  };

  const fetchAgentPipelineSteps = async (workflowId: string) => {
    pipelineStepsRequestStartedRef.current = true;
    pipelineStepsLastRequestedWorkflowRef.current = workflowId;
    pipelineStepsAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = pipelineStepsRequestIdRef.current + 1;
    pipelineStepsAbortRef.current = controller;
    pipelineStepsRequestIdRef.current = requestId;
    try {
      const params = new URLSearchParams({ workflow: workflowId || "default", include_image: "true" });
      const res = await fetch(`${API_URL}/pipeline/steps?${params.toString()}`, { signal: controller.signal });
      if (!res.ok) return;
      const data = await res.json();
      if (controller.signal.aborted || pipelineStepsRequestIdRef.current !== requestId) return;
      setAgentPipelineSteps(normalizeAgentPipelineSteps(data));
    } catch (e) {
      if (controller.signal.aborted) return;
      console.error("Error fetching agent pipeline steps", e);
    } finally {
      if (pipelineStepsAbortRef.current === controller) pipelineStepsAbortRef.current = null;
    }
  };


  const fetchProjectHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/projects`, {
        headers: await optionalAuthHeaders(),
      });
      if (res.ok) {
        const projects = await res.json();
        setProjectHistory(projects);
        if (!authRequired) {
          setLocalChatItems((current) => {
            const repairedItems = buildChatListItems(projects, current);
            writeStoredChatIndex(repairedItems, chatStorageScope);
            return repairedItems;
          });
        }
      }
    } catch (e) {
      console.error("Error fetching project history", e);
    } finally {
      setProjectHistoryLoaded(true);
    }
  };

  const fetchMyProjectHistory = async () => {
    if (authRequired && !authLoaded) {
      setMyProjectHistoryLoaded(false);
      return;
    }
    if (authRequired && !isSignedIn) {
      setMyProjectHistory([]);
      setMyProjectHistoryLoaded(true);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/my/projects`, {
        headers: await generationRequestHeaders(),
      });
      if (res.ok) {
        setMyProjectHistory(await res.json());
      } else if (res.status === 401) {
        setMyProjectHistory([]);
      } else {
        throw new Error(await readApiErrorMessage(res));
      }
    } catch (e) {
      console.error("Error fetching my project history", e);
    } finally {
      setMyProjectHistoryLoaded(true);
    }
  };

  const fetchPrivateChats = async () => {
    if (authRequired && !authLoaded) {
      setPrivateChatsLoaded(false);
      return;
    }
    if (authRequired && !isSignedIn) {
      setPrivateChatItems([]);
      setSessionChatItems([]);
      setPrivateChatsLoaded(true);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/chats`, {
        headers: await generationRequestHeaders(),
      });
      if (res.ok) {
        const chats = await res.json();
        setPrivateChatItems(normalizePrivateChatItems(chats));
        const threadUpdates: Record<string, ChatMessage[]> = {};
        if (Array.isArray(chats)) {
          chats.forEach((chat: any) => {
            const chatId = typeof chat?.chat_id === "string" ? chat.chat_id.trim() : "";
            const messages = persistableChatMessages(Array.isArray(chat?.messages) ? chat.messages : []);
            if (!chatId || !messages.length) return;
            threadUpdates[chatId] = messages;
            writeStoredChatThread(chatId, messages, chatStorageScope);
          });
        }
        if (Object.keys(threadUpdates).length) {
          setChatThreads((current) => ({ ...current, ...threadUpdates }));
          if (activeChatId && threadUpdates[activeChatId]) {
            setChatMessages(threadUpdates[activeChatId]);
          }
        }
      } else if (res.status === 401) {
        setPrivateChatItems([]);
        setSessionChatItems([]);
      } else {
        throw new Error(await readApiErrorMessage(res));
      }
    } catch (e) {
      console.error("Error fetching private chats", e);
    } finally {
      setPrivateChatsLoaded(true);
    }
  };

  const refreshProjectAndChatLists = () => {
    fetchProjectHistory();
    if (!authRequired || isSignedIn) {
      void fetchMyProjectHistory();
      void fetchPrivateChats();
    }
  };

  const changeJobStatusFilter = (status: string) => {
    setJobStatusFilter(status);
  };


  useEffect(() => {
    if (!normalizeTab(activeTab)) setActiveTab("chat");
  }, [activeTab]);


  useEffect(() => {
    if (!a2aJobs.length) return;
    const jobsById = new Map(a2aJobs.map((job) => [job.job_id, job]));

    setChatMessages((current) => mergeMessagesWithJobs(current, jobsById, generateProductImage));
    setChatThreads((current) => {
      let changed = false;
      const nextThreads: Record<string, ChatMessage[]> = {};
      Object.entries(current).forEach(([chatId, messages]) => {
        const nextMessages = mergeMessagesWithJobs(messages, jobsById, generateProductImage);
        if (nextMessages !== messages) {
          changed = true;
          writeStoredChatThread(chatId, nextMessages, chatStorageScope);
          persistChatThread(chatId, nextMessages);
        }
        nextThreads[chatId] = nextMessages;
      });
      return changed ? nextThreads : current;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a2aJobs, generateProductImage]);

  useEffect(() => {
    if (!waitingGenerationJobKey || jobsViewActive || (authRequired && !isSignedIn)) return;
    const jobIds = waitingGenerationJobKey.split("\n").filter(Boolean);
    let cancelled = false;
    let polling = false;
    let nextJobIndex = 0;

    const reconcileWaitingJobs = async () => {
      if (polling) return;
      polling = true;
      try {
        const now = Date.now();
        const eligibleJobIds = jobIds.filter(
          (jobId) => (recoveryJobMissesRef.current.get(jobId)?.retryAfter || 0) <= now
        );
        if (!eligibleJobIds.length) return;
        const batchSize = Math.min(RECOVERY_JOB_BATCH_SIZE, eligibleJobIds.length);
        const batch = Array.from({ length: batchSize }, (_, offset) => (
          eligibleJobIds[(nextJobIndex + offset) % eligibleJobIds.length]
        ));
        nextJobIndex = (nextJobIndex + batchSize) % eligibleJobIds.length;
        const jobs: A2AJob[] = [];
        for (const jobId of batch) {
          if (cancelled) return;
          const job = await fetchA2aJob(jobId);
          if (job) {
            recoveryJobMissesRef.current.delete(jobId);
            jobs.push(job);
          } else {
            const previousMisses = recoveryJobMissesRef.current.get(jobId)?.misses || 0;
            const misses = previousMisses + 1;
            const backoffMs = Math.min(
              JOB_POLL_INTERVAL_MS * (2 ** Math.min(misses, 4)),
              RECOVERY_JOB_MAX_BACKOFF_MS
            );
            recoveryJobMissesRef.current.set(
              jobId,
              { misses, retryAfter: Date.now() + backoffMs }
            );
          }
        }
        if (cancelled || !jobs.length) return;
        const jobsById = new Map(jobs.map((job) => [job.job_id, job]));
        setChatMessages((current) => mergeMessagesWithJobs(current, jobsById, generateProductImage));
        setChatThreads((current) => {
          let changed = false;
          const nextThreads: Record<string, ChatMessage[]> = {};
          Object.entries(current).forEach(([chatId, messages]) => {
            const nextMessages = mergeMessagesWithJobs(messages, jobsById, generateProductImage);
            if (nextMessages !== messages) {
              changed = true;
              writeStoredChatThread(chatId, nextMessages, chatStorageScope);
              persistChatThread(chatId, nextMessages);
            }
            nextThreads[chatId] = nextMessages;
          });
          return changed ? nextThreads : current;
        });
      } finally {
        polling = false;
      }
    };

    const pollWhenVisible = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void reconcileWaitingJobs();
      }
    };
    pollWhenVisible();
    const intervalId = window.setInterval(pollWhenVisible, JOB_POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", pollWhenVisible);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", pollWhenVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequired, fetchA2aJob, generateProductImage, isSignedIn, jobsViewActive, waitingGenerationJobKey]);


  useEffect(() => {
    if (currentRouteProjectId || projectIR) return;
    const visibleProjectIds = new Set(visibleProjectGalleryIds);
    if (!visibleProjectIds.size) return;

    const imageProjects = mergeProjectRecords(
      mergeProjectRecords(projectHistory, myProjectHistory),
      projectRecordsFromChatItems(chatListItems)
    ).filter((project: any) => {
      const projectId = project?.project_id ? String(project.project_id) : "";
      return projectId && visibleProjectIds.has(projectId);
    });
    const missingProjects = imageProjects.filter((project: any) => {
      const projectId = project?.project_id ? String(project.project_id) : "";
      const summaryImage =
        resolveProjectImageCandidates({
          product_visual_sequence: project.product_visual_sequence,
          product_image_url: project.product_image_url,
          product_image_data: project.product_image_data,
          product_image_content_type: project.product_image_content_type,
          product_image_model: project.product_image_model,
          image_output_model: project.image_output_model,
        })[0] || null;
      return projectId && !summaryImage && projectGalleryImages[projectId] === undefined;
    });
    if (!missingProjects.length) return;

    let cancelled = false;
    const controller = new AbortController();

    Promise.all(
      missingProjects.map(async (project: any): Promise<[string, ProjectImageCandidate | null]> => {
        const projectId = String(project.project_id);
        try {
          const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/image-summary`, {
            signal: controller.signal,
            headers: await optionalAuthHeaders(),
          });
          if (!res.ok) return [projectId, null];

          const data = await res.json();
          return [projectId, resolveProjectImageCandidates(data || {})[0] || null];
        } catch (error) {
          if (!controller.signal.aborted) {
            console.error("Error fetching project image", error);
          }
          return [projectId, null];
        }
      })
    ).then((entries) => {
      if (cancelled) return;
      setProjectGalleryImages((current) => {
        const next = { ...current };
        entries.forEach(([projectId, image]) => {
          next[projectId] = image;
        });
        return next;
      });
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [chatListItems, currentRouteProjectId, myProjectHistory, optionalAuthHeaders, projectHistory, projectGalleryImages, projectIR, visibleProjectGalleryIds]);

  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      setGenerationInputNotice(null);
      setSelectedImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const removeSelectedImage = () => {
    setGenerationInputNotice(null);
    setSelectedImage(null);
    if (fileInputRefSidebar.current) fileInputRefSidebar.current.value = "";
    if (fileInputRefCenter.current) fileInputRefCenter.current.value = "";
  };

  const beginGenerationRun = (kind: ActiveGenerationRun["kind"], chatId: string): ActiveGenerationRun => {
    const run: ActiveGenerationRun = {
      kind,
      controller: new AbortController(),
      jobId: null,
      chatId,
      assistantMessageId: null,
      cancelled: false,
    };
    activeGenerationRef.current = run;
    setActiveGeneration({ kind, jobId: null });
    setIsLoading(true);
    return run;
  };

  const setGenerationRunJob = (run: ActiveGenerationRun, jobId: string, assistantMessageId: string) => {
    run.jobId = jobId;
    run.assistantMessageId = assistantMessageId;
    if (activeGenerationRef.current === run) {
      setActiveGeneration({ kind: run.kind, jobId });
    }
  };

  const finishGenerationRun = (run: ActiveGenerationRun) => {
    if (activeGenerationRef.current !== run) return;
    activeGenerationRef.current = null;
    setActiveGeneration(null);
    setIsLoading(false);
  };

  const cancelGenerationJob = async (jobId: string) => {
    // The stop click can win the race with the server creating the job, so retry
    // a short-lived 404 before giving up.
    for (let attempt = 0; attempt < 5; attempt += 1) {
      try {
        const res = await fetch(`${API_URL}/a2a/jobs/${encodeURIComponent(jobId)}/cancel`, {
          method: "POST",
          headers: await generationRequestHeaders(),
        });
        if (res.ok || res.status !== 404) return;
      } catch (error) {
        console.warn("Could not notify the backend that generation was stopped.", error);
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
  };

  const stopActiveGeneration = () => {
    const run = activeGenerationRef.current;
    if (!run) return;

    run.cancelled = true;
    run.controller.abort();
    if (run.assistantMessageId) {
      const patch: Partial<Omit<ChatMessage, "id">> = {
        content: "Generation stopped by you.",
        status: "cancelled",
      };
      if (run.kind === "chat") updateChatMessage(run.assistantMessageId, patch);
      updateThreadMessage(run.chatId, run.assistantMessageId, patch);
    }
    setGenerationInputNotice("Generation stopped. You can send another message whenever you're ready.");
    if (run.jobId) void cancelGenerationJob(run.jobId);
    finishGenerationRun(run);
  };

  const handleGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (activeGenerationRef.current) return;
    if (!(await requireSignedInForGeneration())) return;
    if (!selectedGenerationLlm) {
      setGenerationInputNotice("Turn on at least one model provider in Settings before building.");
      return;
    }
    const contextCheckpoint = pendingHumanContext;
    const validationSubject = contextCheckpoint ? contextCheckpoint.basePrompt : prompt;
    const validation = validateGenerationInput(validationSubject, Boolean(selectedImage));
    if (!validation.isValid) {
      setGenerationInputNotice(validation.message);
      if (validation.message) {
        appendChatMessage({
          role: "assistant",
          content: validation.message,
          status: "error",
        });
      }
      return;
    }

    const rawPromptText = contextCheckpoint
      ? contextCheckpoint.basePrompt
      : validationSubject.trim() || "Infer a buildable hardware project from the uploaded reference image.";
    const imageData = selectedImage;
    const requestChatId = activeChatId || newBuildChatId();
    const generationRun = beginGenerationRun("chat", requestChatId);

    if (!contextCheckpoint) {
      setGenerationInputNotice(null);
      try {
        const clarification = await requestHumanContextQuestions(
          validationSubject.trim(),
          generationWorkflow,
          Boolean(imageData),
          generationRun.controller.signal
        );
        if (generationRun.cancelled) return;
        if (clarification.shouldAsk) {
          const answers = Object.fromEntries(clarification.questions.map((question) => [question.id, ""]));
          setActiveChatId(requestChatId);
          rememberChatItem({
            chatId: requestChatId,
            title: rawPromptText,
            projectId: "",
            createdAt: chatTimestamp(),
            projectCount: 0,
          });
          syncChatRoute(requestChatId);
          appendChatMessage({
            role: "user",
            content: rawPromptText,
            status: "idle",
          });
          appendThreadMessage(requestChatId, {
            role: "user",
            content: rawPromptText,
            status: "idle",
          });
          appendChatMessage({
            role: "assistant",
            content: [
              "A few quick questions before I build.",
              "",
              ...clarification.questions.map((question) => `- ${question.label}: ${question.question}`),
            ].join("\n"),
            status: "idle",
          });
          appendThreadMessage(requestChatId, {
            role: "assistant",
            content: [
              "A few quick questions before I build.",
              "",
              ...clarification.questions.map((question) => `- ${question.label}: ${question.question}`),
            ].join("\n"),
            status: "idle",
          });
          setPendingHumanContext({
            basePrompt: rawPromptText,
            questions: clarification.questions,
            answers,
          });
          setPrompt("");
          setGenerationInputNotice(clarification.reason || "Answer the context questions, then build.");
          finishGenerationRun(generationRun);
          return;
        }
      } catch (error) {
        if (generationRun.cancelled || (error instanceof Error && error.name === "AbortError")) return;
        finishGenerationRun(generationRun);
        throw error;
      }
    }

    if (generationRun.cancelled) return;

    const finalContextNotes = contextCheckpoint ? prompt.trim() : "";
    const promptText = contextCheckpoint
      ? humanContextPromptSection(contextCheckpoint, finalContextNotes)
      : rawPromptText;
    const userMessageContent = contextCheckpoint
      ? humanContextChatSummary(contextCheckpoint, finalContextNotes)
      : rawPromptText;
    let generatedProject = false;
    let generatedProjectId: string | null = null;
    const frontendJobId = newFrontendJobId();
    const userMessageId = newChatMessageId();
    const assistantMessageId = newChatMessageId();
    const pipelineProgress = createAgentPipelineProgress(agentPipelineSteps, generateProductImage, chatTimestamp(), frontendJobId);
    const externalSourceProviderForRequest = selectedWorkflowUsesExternalSources ? FIRECRAWL_EXTERNAL_SOURCE_PROVIDER : null;
    const workflowLabel = selectedGenerationWorkflow?.label || generationWorkflow;
    const providerSuffix = externalSourceProviderForRequest ? " via Firecrawl" : "";
    const loadingMessage = `Running ${workflowLabel}${providerSuffix} with ${selectedGenerationLlm.label}.`;
    let progressPollId: number | null = null;
    const syncProgressFromJob = async () => {
      const job = await fetchA2aJob(frontendJobId);
      if (!job) return;
      applyChatPipelineProgressFromJob(assistantMessageId, job, pipelineProgress, generateProductImage);
      applyThreadPipelineProgressFromJob(requestChatId, assistantMessageId, job, pipelineProgress, generateProductImage);
    };
    setActiveChatId(requestChatId);
    rememberChatItem({
      chatId: requestChatId,
      title: rawPromptText,
      projectId: "",
      createdAt: chatTimestamp(),
      projectCount: 0,
    });
    syncChatRoute(requestChatId);
    appendChatMessage({
      id: userMessageId,
      role: "user",
      content: userMessageContent,
      status: "idle",
    });
    appendThreadMessage(requestChatId, {
      id: userMessageId,
      role: "user",
      content: userMessageContent,
      status: "idle",
    });
    appendChatMessage({
      id: assistantMessageId,
      role: "assistant",
      content: loadingMessage,
      status: "loading",
      pipelineProgress,
    });
    appendThreadMessage(requestChatId, {
      id: assistantMessageId,
      role: "assistant",
      content: loadingMessage,
      status: "loading",
      pipelineProgress,
    });
    setGenerationRunJob(generationRun, frontendJobId, assistantMessageId);

    setGenerationInputNotice(null);
    setPendingHumanContext(null);
    setPrompt("");
    checkServerStatus();
    progressPollId = window.setInterval(() => {
      void syncProgressFromJob();
    }, ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS);
    void syncProgressFromJob();

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        signal: generationRun.controller.signal,
        body: JSON.stringify({
          prompt: promptText,
          workflow: generationWorkflow,
          external_source_provider: externalSourceProviderForRequest,
          provider: selectedGenerationLlm.provider,
          model: selectedGenerationLlm.model,
          chat_id: requestChatId,
          client_job_id: frontendJobId,
          image_data: imageData || null,
          generate_image: generateProductImage,
        }),
      });

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (apiError.debug) {
          console.error("Forma API debug trace", apiError);
        }
        const errorMessage = apiError.message;
        const displayErrorMessage = compactDiagnosticText(errorMessage) || errorMessage;
        if (res.status === 400) {
          setGenerationInputNotice(displayErrorMessage);
          updateChatMessage(assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          updateThreadMessage(requestChatId, assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          return;
        }
        if (apiError.code === "llm_output_invalid" || apiError.code === "llm_generation_unavailable") {
          setGenerationInputNotice(displayErrorMessage);
          updateChatMessage(assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          updateThreadMessage(requestChatId, assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          return;
        }
        if (res.status === 503) {
          setGenerationInputNotice(displayErrorMessage);
          updateChatMessage(assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          updateThreadMessage(requestChatId, assistantMessageId, {
            content: displayErrorMessage,
            status: "error",
          });
          return;
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();
      if (data.job) {
        applyChatPipelineProgressFromJob(assistantMessageId, data.job, pipelineProgress, generateProductImage);
        applyThreadPipelineProgressFromJob(requestChatId, assistantMessageId, data.job, pipelineProgress, generateProductImage);
      }
      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      const projectId = projectIdFromIR(ir);
      const responseChatId = chatIdFromIR(ir) || data.chat_id || requestChatId;
      generatedProjectId = projectId;
      setActiveChatId(responseChatId);
      rememberProjectRecord({
        project_id: projectId,
        chat_id: responseChatId,
        title: ir?.overview?.title || rawPromptText,
        prompt: promptText,
        created_at: data.created_at || chatTimestamp(),
        can_chat: true,
        creator_display: "you",
        creator_image_url: userImageUrl,
        parts_count: Array.isArray(ir?.components) ? ir.components.length : 0,
        star_count: 0,
      });
      const successMessage = `${ir?.overview?.title || "Project"} is ready. I generated the project object, wiring view, BOM, docs, and validation metadata.`;
      rememberChatItem({
        chatId: responseChatId,
        title: ir?.overview?.title || rawPromptText,
        projectId: projectId || "",
        createdAt: chatTimestamp(),
        projectCount: projectId ? 1 : 0,
      });
      updateChatMessage(assistantMessageId, {
        content: successMessage,
        status: "success",
        projectId,
      });
      if (projectId) {
        updateThreadMessage(requestChatId, userMessageId, {
          projectId,
        });
        updateThreadMessage(requestChatId, assistantMessageId, {
          content: successMessage,
          status: "success",
          projectId,
        });
      }
      refreshProjectAndChatLists();
      fetchA2aJobs(jobStatusFilter, { silent: true });
      generatedProject = true;
    } catch (error) {
      if (generationRun.cancelled || (error instanceof Error && error.name === "AbortError")) {
        updateChatMessage(assistantMessageId, {
          content: "Generation stopped by you.",
          status: "cancelled",
        });
        updateThreadMessage(requestChatId, assistantMessageId, {
          content: "Generation stopped by you.",
          status: "cancelled",
        });
        return;
      }
      console.warn("Using local simulation fallback", error);
      try {
        const mockRes = await runMockCompilation(promptText, imageData);
        mockRes.project_ir.assembly_metadata = {
          ...(mockRes.project_ir.assembly_metadata || {}),
          chat_id: requestChatId,
        };
        setProjectIR(mockRes.project_ir);
        const fallbackProjectId = projectIdFromIR(mockRes.project_ir);
        generatedProjectId = fallbackProjectId;
        const fallbackMessage = `${mockRes.project_ir?.overview?.title || "Local example"} is loaded from local fallback because live generation failed.`;
        rememberProjectRecord({
          project_id: fallbackProjectId,
          chat_id: requestChatId,
          title: mockRes.project_ir?.overview?.title || rawPromptText,
          prompt: promptText,
          created_at: chatTimestamp(),
          can_chat: true,
          creator_display: "you",
          creator_image_url: userImageUrl,
          parts_count: Array.isArray(mockRes.project_ir?.components) ? mockRes.project_ir.components.length : 0,
          star_count: 0,
        });
        rememberChatItem({
          chatId: requestChatId,
          title: mockRes.project_ir?.overview?.title || rawPromptText,
          projectId: fallbackProjectId || "",
          createdAt: chatTimestamp(),
          projectCount: fallbackProjectId ? 1 : 0,
        });
        updateChatMessage(assistantMessageId, {
          content: fallbackMessage,
          status: "success",
          projectId: fallbackProjectId,
        });
        if (fallbackProjectId) {
          updateThreadMessage(requestChatId, userMessageId, {
            projectId: fallbackProjectId,
          });
          updateThreadMessage(requestChatId, assistantMessageId, {
            content: fallbackMessage,
            status: "success",
            projectId: fallbackProjectId,
          });
        }
        generatedProject = true;
      } catch (fallbackError) {
        const message = fallbackError instanceof Error ? fallbackError.message : "Local example fallback failed.";
        const errorMessage = generationFailureChatMessage(`Generation failed and local fallback was unavailable: ${message}`);
        setGenerationInputNotice(errorMessage);
        updateChatMessage(assistantMessageId, {
          content: errorMessage,
          status: "error",
        });
        updateThreadMessage(requestChatId, assistantMessageId, {
          content: errorMessage,
          status: "error",
        });
      }
    } finally {
      if (progressPollId !== null) window.clearInterval(progressPollId);
      if (generatedProject) {
        setSelectedImage(null);
        setActiveTab("chat");
      }
      if (generatedProjectId) {
        refreshProjectAndChatLists();
      }
      finishGenerationRun(generationRun);
    }
  };

  const handleProjectChatGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (activeGenerationRef.current) return;
    if (!(await requireSignedInForGeneration())) return;
    if (!currentProjectCanChat) {
      setGenerationInputNotice("You can only chat with projects you own.");
      return;
    }
    if (!currentProjectId || !projectIR) return;

    const userMessage = projectChatInput.trim();
    if (!userMessage) return;

    const sourceProjectId = currentProjectId;
    const sourceProjectTitle = projectTitle;
    const sourceChatId = currentProjectChatId || activeChatId || newBuildChatId();
    const promptText = projectChatGenerationPrompt(projectIR, userMessage, activeTab);
    const generationRun = beginGenerationRun("project-chat", sourceChatId);
    setActiveChatId(sourceChatId);
    rememberChatItem({
      chatId: sourceChatId,
      title: projectTitle || userMessage,
      projectId: sourceProjectId,
      createdAt: chatTimestamp(),
      projectCount: 1,
    });
    syncChatRoute(sourceChatId);
    appendThreadMessage(sourceChatId, {
      role: "user",
      content: userMessage,
      status: "idle",
    });
    const frontendJobId = newFrontendJobId();
    const externalSourceProviderForRequest = selectedWorkflowUsesExternalSources ? FIRECRAWL_EXTERNAL_SOURCE_PROVIDER : null;
    const providerSuffix = externalSourceProviderForRequest ? " via Firecrawl" : "";
    const pipelineProgress = createAgentPipelineProgress(agentPipelineSteps, generateProductImage, chatTimestamp(), frontendJobId);
    const assistantMessageId = appendThreadMessage(sourceChatId, {
      role: "assistant",
      content: `Building a new project from ${sourceProjectTitle}${providerSuffix}.`,
      status: "loading",
      pipelineProgress,
    });
    setGenerationRunJob(generationRun, frontendJobId, assistantMessageId);
    let progressPollId: number | null = null;
    const syncProgressFromJob = async () => {
      const job = await fetchA2aJob(frontendJobId);
      if (!job) return;
      applyThreadPipelineProgressFromJob(sourceChatId, assistantMessageId, job, pipelineProgress, generateProductImage);
    };

    setProjectChatInput("");
    setGenerationInputNotice(null);
    checkServerStatus();
    progressPollId = window.setInterval(() => {
      void syncProgressFromJob();
    }, ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS);
    void syncProgressFromJob();

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        signal: generationRun.controller.signal,
        body: JSON.stringify({
          prompt: promptText,
          workflow: generationWorkflow,
          external_source_provider: externalSourceProviderForRequest,
          provider: selectedGenerationLlm.provider,
          model: selectedGenerationLlm.model,
          chat_id: sourceChatId,
          source_project_id: sourceProjectId,
          client_job_id: frontendJobId,
          image_data: null,
          generate_image: generateProductImage,
        }),
      });

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (apiError.debug) {
          console.error("Forma API debug trace", apiError);
        }
        throw new Error(compactDiagnosticText(apiError.message) || apiError.message);
      }

      const data = await res.json();
      if (data.job) {
        applyThreadPipelineProgressFromJob(sourceChatId, assistantMessageId, data.job, pipelineProgress, generateProductImage);
      }
      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      const newProjectId = projectIdFromIR(ir);
      const responseChatId = chatIdFromIR(ir) || data.chat_id || sourceChatId;
      setActiveChatId(responseChatId);
      rememberProjectRecord({
        project_id: newProjectId,
        chat_id: responseChatId,
        title: ir?.overview?.title || projectTitle || userMessage,
        prompt: promptText,
        created_at: data.created_at || chatTimestamp(),
        can_chat: true,
        creator_display: "you",
        creator_image_url: userImageUrl,
        parts_count: Array.isArray(ir?.components) ? ir.components.length : 0,
        star_count: 0,
      });
      const successMessage = `${ir?.overview?.title || "Project"} is ready as a new project from this chat.`;
      rememberChatItem({
        chatId: responseChatId,
        title: ir?.overview?.title || projectTitle || userMessage,
        projectId: newProjectId || sourceProjectId,
        createdAt: chatTimestamp(),
        projectCount: newProjectId ? 2 : 1,
      });

      updateThreadMessage(sourceChatId, assistantMessageId, {
        content: successMessage,
        status: "success",
        projectId: newProjectId || sourceProjectId,
      });

      setActiveTab("chat");
      refreshProjectAndChatLists();
      fetchA2aJobs(jobStatusFilter, { silent: true });
    } catch (error) {
      if (generationRun.cancelled || (error instanceof Error && error.name === "AbortError")) {
        updateThreadMessage(sourceChatId, assistantMessageId, {
          content: "Generation stopped by you.",
          status: "cancelled",
        });
        return;
      }
      const message = error instanceof Error ? error.message : "Project chat generation failed.";
      updateThreadMessage(sourceChatId, assistantMessageId, {
        content: message,
        status: "error",
      });
    } finally {
      if (progressPollId !== null) window.clearInterval(progressPollId);
      finishGenerationRun(generationRun);
    }
  };

  const loadExample = async (filename: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`/examples/${filename}`);
      if (!res.ok) return;

      const ir = await res.json();
      setProjectIR(ir);
      setActiveTab("overview");
    } catch (error) {
      console.error("Error loading example", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const example = params.get("example");
    const tab = normalizeTab(params.get("tab"));
    if (!example) {
      if (tab) setActiveTab(tab);
      return;
    }

    const filename = example.endsWith(".json") ? example : `${example}.json`;
    loadExample(filename).then(() => {
      if (tab) setActiveTab(tab);
    });
  }, []);


  const runMockCompilation = async (userPrompt: string, imageData?: string | null): Promise<any> => {
    const promptLower = userPrompt.toLowerCase();
    let file = "biometric_deadbolt.json";

    if (
      imageData ||
      promptLower.includes("mp3") ||
      promptLower.includes("audio") ||
      promptLower.includes("music") ||
      promptLower.includes("player") ||
      promptLower.includes("pocket")
    ) {
      file = "pocket_mp3_player.json";
    } else if (promptLower.includes("water") || promptLower.includes("plant") || promptLower.includes("soil") || promptLower.includes("garden")) {
      file = "plant_watering.json";
    } else if (promptLower.includes("thermostat") || promptLower.includes("temperature") || promptLower.includes("weather")) {
      file = "smart_thermostat.json";
    }

    const res = await fetch(`/examples/${file}`);
    if (!res.ok) {
      throw new Error(`Could not load local example ${file}.`);
    }
    const ir = await res.json();
    ir.assembly_metadata = {
      ...(ir.assembly_metadata || {}),
      reference_image_data: imageData || ir.assembly_metadata?.reference_image_data || null,
      input_mode: imageData ? "prompt_image" : "prompt",
      image_features: ir.assembly_metadata?.image_features || ir.constraints || [],
    };
    return {
      project_ir: ir,
    };
  };

  const loadOldProject = async (
    projectId: string,
    options: { syncRoute?: boolean; signal?: AbortSignal; tab?: string | null } = {}
  ): Promise<boolean> => {
    if (options.signal?.aborted) return false;

    const shouldSyncRoute = options.syncRoute ?? true;
    const signal = options.signal;
    setIsLoading(true);
    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
        signal,
        headers: await optionalAuthHeaders(),
      });
      if (!res.ok) return false;

      const data = await res.json();
      if (signal?.aborted) return false;

      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      if (canChatWithProjectIR(ir)) {
        ensureChatThread(projectId, ir, data.prompt);
      }
      setActiveTab(normalizeTab(options.tab || "") || "chat");
      if (shouldSyncRoute) syncProjectRoute(projectId);
      return true;
    } catch (error) {
      const errorName = error instanceof Error ? error.name : "";
      if (errorName !== "AbortError") {
        console.error(error);
      }
      return false;
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  };

  const routedProjectId = currentRouteProjectId ? safeDecodeProjectId(currentRouteProjectId) : "";

  useEffect(() => {
    if (!routedProjectId) {
      setRouteProjectError(null);
      return;
    }

    const controller = new AbortController();
    const projectId = routedProjectId;
    const tab = normalizeTab(new URLSearchParams(window.location.search).get("tab"));
    setChatRouteTransition(null);
    setRouteProjectError(null);

    if (projectIdFromIR(projectIR) === projectId) {
      setActiveTab(tab || "chat");
      return;
    }

    setProjectIR(null);

    loadOldProject(projectId, { syncRoute: false, signal: controller.signal, tab }).then((loaded) => {
      if (controller.signal.aborted) return;
      if (!loaded) {
        setRouteProjectError("Could not load that saved project.");
        return;
      }
    });

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routedProjectId]);

  const routedChatId = currentRouteChatId && !currentRouteProjectId ? safeDecodeChatId(currentRouteChatId) : "";
  const routedChatItem = routedChatId
    ? chatListItems.find((item) => item.chatId === routedChatId) || null
    : null;
  const routedChatFound = Boolean(routedChatItem);
  const routedChatProjectId = routedChatItem?.projectId || "";
  const routedChatTitle = routedChatItem?.title || "Opening chat";

  useEffect(() => {
    if (!routedChatId || currentRouteProjectId) return;
    if (authRequired && !isSignedIn) return;

    const controller = new AbortController();
    const chatId = routedChatId;
    const chatSourcesReady = chatIndexLoaded && chatHistoryLoaded;
    const storedMessages = !authRequired || (chatSourcesReady && routedChatFound)
      ? readStoredChatThread(chatId, null, chatStorageScope)
      : [];
    setActiveChatId(chatId);
    setActiveTab("chat");
    setRouteProjectError(null);
    if (storedMessages.length) {
      setChatThreads((current) => ({ ...current, [chatId]: storedMessages }));
      setChatMessages(storedMessages);
    } else {
      setChatMessages(initialChatMessages());
    }

    if (!chatSourcesReady) {
      setChatRouteTransition({ chatId, title: "Opening chat", projectId: "", error: null });
      return () => {
        controller.abort();
      };
    }

    if (!routedChatFound && chatSourcesReady && authRequired) {
      setProjectIR(null);
      setChatRouteTransition({
        chatId,
        title: "Chat unavailable",
        projectId: "",
        error: "This chat does not exist or is not available to this account.",
      });
      return () => {
        controller.abort();
      };
    }

    if (!routedChatFound && chatSourcesReady) {
      rememberChatItem({
        chatId,
        title: NEW_PROJECT_TITLE,
        projectId: "",
        createdAt: chatTimestamp(),
        projectCount: 0,
      });
    }

    if (!routedChatProjectId) {
      setChatRouteTransition(null);
      setProjectIR(null);
      return () => {
        controller.abort();
      };
    }

    if (projectIdFromIR(projectIR) === routedChatProjectId) {
      setChatRouteTransition(null);
      return () => {
        controller.abort();
      };
    }

    setChatRouteTransition({
      chatId,
      title: routedChatTitle,
      projectId: routedChatProjectId,
      error: null,
    });
    loadOldProject(routedChatProjectId, { syncRoute: false, signal: controller.signal, tab: "chat" }).then((loaded) => {
      if (controller.signal.aborted) return;
      if (loaded) {
        setChatRouteTransition(null);
        return;
      }
      setProjectIR(null);
      setActiveTab("chat");
      const nextMessages = messagesWithoutMissingProject(
        storedMessages.length ? storedMessages : initialChatMessages(),
        routedChatProjectId
      );
      setChatThreads((current) => ({
        ...current,
        [chatId]: nextMessages,
      }));
      setChatMessages(nextMessages);
      writeStoredChatThread(chatId, nextMessages, chatStorageScope);
      persistChatThread(chatId, nextMessages, routedChatTitle);
      detachMissingProjectFromChat(chatId, routedChatProjectId, routedChatTitle);
      setChatRouteTransition(null);
    });

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routedChatId, currentRouteProjectId, routedChatFound, routedChatProjectId, chatIndexLoaded, chatHistoryLoaded, authRequired, isSignedIn, chatStorageScope]);

  const findProjectForJob = (job: A2AJob) => {
    const projectId = job.result_summary?.project_id;
    if (projectId) {
      const directMatch = projectHistory.find((project: any) => project.project_id === projectId);
      return directMatch || { project_id: projectId };
    }

    const prompt = job.payload?.prompt;
    const title = job.result_summary?.title;
    if (!prompt && !title) return null;

    return projectHistory.find((project: any) => {
      const promptMatches = prompt ? project.prompt === prompt : true;
      const titleMatches = title ? project.title === title : true;
      return promptMatches && titleMatches;
    }) || null;
  };

  const chatItemForJob = (job: A2AJob, project: any = findProjectForJob(job)): ChatListItem | null => {
    const chatId = chatIdFromJob(job);
    if (!chatId) return null;

    const existing = chatListItems.find((item) => item.chatId === chatId);
    const projectId = String(project?.project_id || job.result_summary?.project_id || existing?.projectId || "").trim();
    return {
      chatId,
      title: existing?.title || job.result_summary?.title || job.payload?.prompt || job.action || NEW_PROJECT_TITLE,
      projectId,
      createdAt: existing?.createdAt || job.created_at || chatTimestamp(),
      projectCount: projectId ? 1 : existing?.projectCount || 0,
    };
  };

  const loadProjectForJob = async (job: A2AJob) => {
    const project = findProjectForJob(job);
    const chatItem = chatItemForJob(job, project);
    if (chatItem) {
      openChatItem(chatItem);
      return;
    }
    if (!project?.project_id) return;
    await loadOldProject(project.project_id);
  };

  const downloadJSONIR = () => {
    if (!projectIR) return;
    if (!currentProjectCanChat) {
      if (authRequired && !isSignedIn) {
        openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" });
      }
      return;
    }
    const title = projectIR.overview?.title || "blueprint_project";
    downloadBrowserFile(
      JSON.stringify(projectIR, null, 2),
      `${title.toLowerCase().replace(/\s+/g, "_")}_blueprint.json`,
      "application/json"
    );
  };

  const downloadMarkdownDocs = () => {
    if (!projectIR) return;
    if (!currentProjectCanChat) {
      if (authRequired && !isSignedIn) {
        openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" });
      }
      return;
    }

    const title = projectIR.overview?.title || "Untitled Hardware Project";
    const markdown = buildProjectDocsMarkdown({
      title,
      description: projectIR.overview?.description,
      assembly: projectIR.assembly || [],
      issues: [
        ...(projectIR.validation?.critical || []),
        ...(projectIR.validation?.warning || []),
        ...(projectIR.validation?.info || []),
        ...(projectIR.validation_issues || []),
      ],
    });

    downloadBrowserFile(markdown, docsExportFilename(title), "text/markdown;charset=utf-8");
  };

  const getOverviewMetrics = () => {
    if (!projectIR?.components) {
      return { electricalParts: 0, mechanicalParts: 0, totalParts: 0, electricalCost: 0, mechanicalCost: 0, totalCost: 0 };
    }

    let electricalParts = 0;
    let mechanicalParts = 0;
    let electricalCost = 0;
    let mechanicalCost = 0;

    projectIR.components.forEach((component: any) => {
      const category = component.category?.toLowerCase() || "";
      const quantity = component.quantity || 1;
      const unitPrice = component.unit_price || 0;

      if (["mechanical", "3d print"].includes(category)) {
        mechanicalParts += quantity;
        mechanicalCost += unitPrice * quantity;
      } else {
        electricalParts += quantity;
        electricalCost += unitPrice * quantity;
      }
    });

    return {
      electricalParts,
      mechanicalParts,
      totalParts: electricalParts + mechanicalParts,
      electricalCost: Number(electricalCost.toFixed(2)),
      mechanicalCost: Number(mechanicalCost.toFixed(2)),
      totalCost: Number((electricalCost + mechanicalCost).toFixed(2)),
    };
  };

  const metrics = getOverviewMetrics();
  const components = projectIR?.components || [];
  const assembly = projectIR?.assembly || [];
  const constraints = projectIR?.constraints || [];
  const imageFeatures = projectIR?.assembly_metadata?.image_features?.length
    ? projectIR.assembly_metadata.image_features
    : constraints;
  const issues = [
    ...(projectIR?.validation?.critical || []),
    ...(projectIR?.validation?.warning || []),
    ...(projectIR?.validation?.info || []),
    ...(projectIR?.validation_issues || []),
  ];
  const projectTitle = projectIR?.overview?.title || "Untitled Hardware Project";
  const projectDescription = projectIR?.overview?.description || "Generated hardware package";
  const projectImageCandidates = useMemo(
    () => resolveProjectImageCandidates(projectIR?.assembly_metadata || {}),
    [projectIR]
  );
  const videoImageOptions = useMemo(
    () => projectImageCandidates.filter((candidate) => !candidate.label.toLowerCase().includes("uploaded")),
    [projectImageCandidates]
  );
  const defaultVideoImage = projectImageCandidates[0]?.src || "";
  const currentProjectId = projectIR?.assembly_metadata?.project_id || null;
  const currentProjectCanChat = Boolean(projectIR && canChatWithProjectIR(projectIR) && (!authRequired || isSignedIn));
  const currentProjectCanDownloadAssets = currentProjectCanChat;
  const projectVideo = useProjectVideo({
    apiUrl: API_URL,
    enabled: Boolean(projectIR && activeTab === "video"),
    projectId: currentProjectId,
    authIdentityKey,
    canManageProject: currentProjectCanChat,
    canLoadProjectVideos: currentProjectCanDownloadAssets,
    imageOptions: videoImageOptions,
    defaultImage: defaultVideoImage,
    authorizeGeneration: requireSignedInForGeneration,
    getRequestHeaders: generationRequestHeaders,
    readError: readApiErrorMessage,
    modelControls: {
      models: videoModels,
      loading: videoModelsLoading,
      error: videoModelsError,
      selectedModel: selectedVideoModel,
      setSelectedModel: setSelectedVideoModel,
      aspectRatios: videoAspectRatios,
      aspectRatio: videoAspectRatio,
      setAspectRatio: setVideoAspectRatio,
    },
    generationAvailability: videoGenerationConfig,
    reviewAvailability: videoSelfCorrectionConfig,
    globalBusy: isLoading,
    setGlobalBusy: setIsLoading,
    updateProject: (nextProjectIR, response) => {
      setProjectIR(withProjectResponseMetadata(nextProjectIR, response));
    },
    refreshProjectAndChatLists,
    refreshJobs: () => {
      void fetchA2aJobs(jobStatusFilter, { silent: true });
    },
  });
  const currentProjectChatId = projectIR
    ? currentProjectCanChat
      ? (chatIdFromIR(projectIR) || currentProjectId || activeChatId)
      : null
    : activeChatId;
  const currentProjectJobId = projectIR?.assembly_metadata?.frontend_job_id || null;
  const currentProjectChatMessages = useMemo(
    () => currentProjectChatId ? chatThreads[currentProjectChatId] || [] : [],
    [chatThreads, currentProjectChatId]
  );
  const activeSidebarChatId = currentProjectChatId || activeChatId;
  const activeSidebarChatItem = chatListItems.find((item) => item.chatId === activeSidebarChatId);
  const activeSidebarChatStarted = Boolean(
    projectIR ||
    chatHasStarted(projectIR ? currentProjectChatMessages : chatMessages) ||
    activeSidebarChatItem?.projectId ||
    activeSidebarChatItem?.projectCount
  );
  const waitingChatIds = useMemo(() => {
    const ids = new Set<string>();
    Object.entries(chatThreads).forEach(([chatId, messages]) => {
      if (chatIsWaiting(messages)) ids.add(chatId);
    });
    if (activeChatId && chatIsWaiting(chatMessages)) ids.add(activeChatId);
    if (currentProjectChatId && chatIsWaiting(currentProjectChatMessages)) ids.add(currentProjectChatId);
    return ids;
  }, [activeChatId, chatMessages, chatThreads, currentProjectChatId, currentProjectChatMessages]);
  const projectJobs = a2aJobs.filter((job) => {
    if (currentProjectJobId && job.job_id === currentProjectJobId) return true;
    if (currentProjectId && job.result_summary?.project_id === currentProjectId) return true;
    return false;
  });
  const visibleWorkspaceTabs = useMemo(
    () => workspaceTabs,
    []
  );
  const activeWorkspaceTab = workspaceTabMeta(activeTab);
  const activeWorkspaceNamespace = workspaceNamespaceForTab(activeTab);
  const projectNamespaceContent = (() => {
    switch (activeWorkspaceTab.id) {
      case "overview":
        return (
          <OverviewPanel
            title={projectTitle}
            description={projectDescription}
            imageCandidates={projectImageCandidates}
            features={imageFeatures}
            metrics={metrics}
            metadata={projectIR?.assembly_metadata || {}}
          />
        );
      case "bom":
        return (
          <BomPanel
            components={components}
            metrics={metrics}
            cadSources={(projectIR?.mechanical && Array.isArray(projectIR.mechanical.cad_sources)) ? projectIR.mechanical.cad_sources : []}
            fabricationCost={Number(projectIR?.mechanical?.fabrication_cost_estimate_usd || 0)}
            canDownloadAssets={currentProjectCanDownloadAssets}
          />
        );
      case "mechanical":
        return (
          <MechanicalPanel
            toggles={mechToggles}
            setToggles={setMechToggles}
            electricalActive={mechElectricalActive}
            setElectricalActive={setMechElectricalActive}
            components={components}
            features={imageFeatures}
            metadata={projectIR?.assembly_metadata || {}}
            mechanical={projectIR?.mechanical || {}}
          />
        );
      case "schematic":
        return <SchematicCanvas project={projectIR} />;
      case "assembly":
        return (
          <AssemblyPanel
            assembly={assembly}
            issues={issues}
            onDownloadJSON={downloadJSONIR}
            onDownloadMarkdown={downloadMarkdownDocs}
            canDownloadAssets={currentProjectCanDownloadAssets}
          />
        );
      case "video":
        return (
          <VideoPanel {...projectVideo} />
        );
      case "jobs":
        return (
          <JobsPanel
            jobs={projectJobs}
            loading={jobsLoading}
            error={jobsError}
            statusFilter={jobStatusFilter}
            onStatusFilterChange={changeJobStatusFilter}
            onRefresh={() => fetchA2aJobs(jobStatusFilter)}
            onOpenProject={loadProjectForJob}
            findProjectForJob={findProjectForJob}
            lastUpdatedAt={jobsLastUpdatedAt}
            pollIntervalMs={JOB_POLL_INTERVAL_MS}
            title="Project Jobs"
            description="Only jobs tied to this project are shown here."
            emptyMessage="No jobs recorded for this project and filter."
            formatLlmLabel={generationLlmLabel}
          />
        );
      case "logs":
        return canViewAdminTools ? (
          <LogsPanel
            logs={backendLogs}
            loading={logsLoading}
            error={logsError}
            lastUpdatedAt={logsLastUpdatedAt}
            onRefresh={() => fetchBackendLogs()}
            pollIntervalMs={LOG_POLL_INTERVAL_MS}
          />
        ) : null;
      case "chat":
      default:
        return (
          <ChatNamespaceSummaryPanel
            projectId={currentProjectId}
            title={projectTitle}
            description={projectDescription}
            namespace={activeWorkspaceNamespace}
            totalGenerationTime={formatTotalGenerationTime(projectIR?.assembly_metadata || {})}
            components={components}
            metrics={metrics}
            issues={issues}
          />
        );
    }
  })();

  useEffect(() => {
    if (!currentProjectCanChat) return;
    if (!currentProjectId || currentProjectChatMessages.length) return;
    ensureChatThread(currentProjectId, projectIR, projectIR?.assembly_metadata?.source_prompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProjectCanChat, currentProjectId, currentProjectChatMessages.length, projectIR]);

  const loadedProjectId = projectIdFromIR(projectIR);
  const implicitChatRouteTransition: ChatRouteTransition | null = routedChatId && (
    activeChatId !== routedChatId ||
    !chatIndexLoaded ||
    !chatHistoryLoaded ||
    Boolean(routedChatProjectId && loadedProjectId !== routedChatProjectId)
  )
    ? {
        chatId: routedChatId,
        title: routedChatTitle,
        projectId: routedChatProjectId,
        error: null,
      }
    : null;
  const visibleChatRouteTransition = chatRouteTransition?.chatId === routedChatId
    ? chatRouteTransition
    : implicitChatRouteTransition;
  const chatTransitionProjectId = visibleChatRouteTransition?.projectId || "";
  const showChatRouteFallback = Boolean(
    routedChatId &&
      visibleChatRouteTransition &&
      (visibleChatRouteTransition.error || !chatTransitionProjectId || loadedProjectId !== chatTransitionProjectId)
  );
  const privateChatRouteRequested = Boolean(authRequired && currentRouteChatId && !currentRouteProjectId);
  const privateChatRouteDenied = privateChatRouteRequested && authLoaded && !isSignedIn;

  if (privateChatRouteDenied) {
    return (
      <AuthRequiredRouteScreen
        loading={false}
        title="Private chat"
        message="Sign in to open this chat."
        onHome={goHome}
      />
    );
  }

  if (showChatRouteFallback && visibleChatRouteTransition) {
    return (
      <WorkspaceFrame
        collapsed={sidebarCollapsed}
        mobileSidebar={(
          <MobileSidebarDrawer
            open={mobileSidebarOpen}
            onClose={() => setMobileSidebarOpen(false)}
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={visibleChatRouteTransition.chatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
        desktopSidebar={(
          <ChatSidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={visibleChatRouteTransition.chatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
      >
        <ChatRouteFallbackPanel
          transition={visibleChatRouteTransition}
          onHome={goHome}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
        />
      </WorkspaceFrame>
    );
  }

  if (routedProjectId && loadedProjectId !== routedProjectId) {
    return (
      <WorkspaceFrame
        collapsed={sidebarCollapsed}
        mobileSidebar={(
          <MobileSidebarDrawer
            open={mobileSidebarOpen}
            onClose={() => setMobileSidebarOpen(false)}
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={activeChatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
        desktopSidebar={(
          <ChatSidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={activeChatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
      >
        <ProjectRouteFallbackPanel
          projectId={routedProjectId}
          error={routeProjectError}
          onHome={goHome}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
        />
      </WorkspaceFrame>
    );
  }

  if ((!currentRouteProjectId && !currentRouteChatId) || !projectIR) {
    return (
      <WorkspaceFrame
        collapsed={sidebarCollapsed}
        homeMobileTopPadding
        mobileSidebar={(
          <MobileSidebarDrawer
            open={mobileSidebarOpen}
            onClose={() => setMobileSidebarOpen(false)}
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={activeChatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
        desktopSidebar={(
          <ChatSidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            onHome={goHome}
            chats={chatListItems}
            activeChatId={activeChatId}
            onNewChat={startNewProjectChat}
            newChatDisabled={!activeSidebarChatStarted}
            onOpenChat={openChatItem}
            waitingChatIds={waitingChatIds}
            chatsLoading={sidebarChatsLoading}
            showJobs={canViewJobs}
            jobsPending={sidebarJobsPending}
            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
            serverStatus={serverStatus}
          />
        )}
      >
        <MobileWorkspaceBar onOpenSidebar={() => setMobileSidebarOpen(true)} serverStatus={serverStatus} authRequired={authRequired} />
	        <main className={`mx-auto w-full ${homeView === "chat" ? "max-w-none" : "max-w-6xl"} ${
	          homeView === "chat"
	            ? "flex min-h-0 flex-1 flex-col overflow-hidden px-0 pb-0 pt-3 sm:pt-4"
            : "min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-5 sm:py-8"
        }`}>
          {homeView === "projects" ? (
            <>
              <WorkspacePageHeading
                icon={Layers}
                title="Projects"
                description="Saved generated projects, grouped from the chat and project history."
              />
              <ProjectGallery
                sectionRef={projectsSectionRef}
                items={projectGalleryItems}
                loading={projectsPageLoading}
                onOpenChat={openChatById}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
                onVisibleProjectIdsChange={handleVisibleProjectGalleryIdsChange}
                standalone
              />
            </>
	          ) : homeView === "my-projects" ? (
            <>
              <WorkspacePageHeading
                icon={Database}
                title="My Projects"
                description="Projects created by your signed-in account."
              />
              <ProjectGallery
                sectionRef={projectsSectionRef}
                items={myProjectGalleryItems}
                loading={myProjectsPageLoading}
                onOpenChat={openChatById}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
                onVisibleProjectIdsChange={handleVisibleProjectGalleryIdsChange}
                standalone
              />
            </>
          ) : homeView === "jobs" ? (
            <>
              <WorkspacePageHeading
                icon={History}
                title="Jobs"
                description="Generated-project jobs, pipeline events, image status, and operation errors."
              />
              {canViewJobs ? (
                <JobsPanel
                  jobs={a2aJobs}
                  loading={jobsLoading}
                  error={jobsError}
                  statusFilter={jobStatusFilter}
                  onStatusFilterChange={changeJobStatusFilter}
                  onRefresh={() => fetchA2aJobs(jobStatusFilter)}
                  onOpenProject={loadProjectForJob}
                  findProjectForJob={findProjectForJob}
                  lastUpdatedAt={jobsLastUpdatedAt}
                  pollIntervalMs={JOB_POLL_INTERVAL_MS}
                  title="Jobs"
                  description="Generation and example project job metadata. Polling stays active while this page is open."
                  emptyMessage="No jobs recorded for this filter."
                  formatLlmLabel={generationLlmLabel}
                />
              ) : (
                <div className="border border-[#2a2c33] bg-[#17181d] p-6 text-sm leading-6 text-slate-400">
                  {adminSessionLoaded ? "Admin access is required to view deployment jobs." : "Checking admin access..."}
                </div>
              )}
            </>
          ) : homeView === "logs" ? (
            <>
              <WorkspacePageHeading
                icon={Terminal}
                title="Backend Logs"
                description="Recent backend log lines for local debugging and package observability."
              />
              {canViewAdminTools ? (
                <LogsPanel
                  logs={backendLogs}
                  loading={logsLoading}
                  error={logsError}
                  lastUpdatedAt={logsLastUpdatedAt}
                  onRefresh={() => fetchBackendLogs()}
                  pollIntervalMs={LOG_POLL_INTERVAL_MS}
                />
              ) : (
                <div className="border border-[#2a2c33] bg-[#17181d] p-6 text-sm leading-6 text-slate-400">
                  {adminSessionLoaded ? "Admin access is required to view backend logs." : "Checking admin access..."}
                </div>
              )}
            </>
          ) : (
            <HomeChatView
              started={activeSidebarChatStarted}
              messages={chatMessages}
              endRef={chatEndRef}
              renderPipelineProgress={(message) => (
                <AgentPipelineProgressView
                  progress={message.pipelineProgress as AgentPipelineProgress | null}
                  status={message.status}
                  compact
                />
              )}
              onOpenProject={(projectId) => {
                void loadOldProject(projectId, { tab: "chat" });
              }}
              examples={samplePrompts}
              onSelectExample={(example) => {
                setGenerationInputNotice(null);
                setPendingHumanContext(null);
                setPrompt(example);
              }}
              onSubmit={handleGenerate}
              pendingContext={pendingHumanContext}
              onContextAnswer={updateHumanContextAnswer}
              onClearContext={clearHumanContextCheckpoint}
              isLoading={isLoading}
              generationReady={generationLlmsReady}
              needsGenerationProvider={needsGenerationProvider}
              needsImageProvider={needsImageProvider}
              selectedImage={selectedImage}
              onRemoveImage={removeSelectedImage}
              notice={visibleGenerationInputNotice}
              prompt={prompt}
              onPromptChange={(value) => {
                setGenerationInputNotice(null);
                setPrompt(value);
              }}
              generationActive={Boolean(activeGeneration)}
              onStop={stopActiveGeneration}
              hasGenerationInput={hasGenerationInput}
              inputValid={generationInputValidation.isValid}
              imageInputRef={fileInputRefCenter}
              onImageChange={handleImageChange}
              webResearchEnabled={webResearchEnabled}
              onWebResearchChange={(enabled) => {
                setGenerationWorkflow(enabled ? WEB_RESEARCH_WORKFLOW_ID : DEFAULT_WORKFLOW_ID);
              }}
              llmKey={generationLlmKeyValue}
              onLlmChange={setGenerationLlmKeyValue}
              llms={generationLlms}
              llmsLoaded={generationLlmsLoaded}
              imageGenerationConfigLoaded={imageGenerationConfigLoaded}
              generateImages={generateProductImage}
              onGenerateImagesChange={setGenerateProductImage}
            />
          )}
        </main>
      </WorkspaceFrame>
    );
  }

  return (
    <WorkspaceFrame
      collapsed={sidebarCollapsed}
      mobileSidebar={(
        <MobileSidebarDrawer
          open={mobileSidebarOpen}
          onClose={() => setMobileSidebarOpen(false)}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((value) => !value)}
          onHome={goHome}
          chats={chatListItems}
          activeChatId={currentProjectChatId || activeChatId}
          onNewChat={startNewProjectChat}
          newChatDisabled={!activeSidebarChatStarted}
          onOpenChat={openChatItem}
          waitingChatIds={waitingChatIds}
          chatsLoading={sidebarChatsLoading}
          showJobs={canViewJobs}
          jobsPending={sidebarJobsPending}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
      )}
      desktopSidebar={(
        <ChatSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((value) => !value)}
          onHome={goHome}
          chats={chatListItems}
          activeChatId={currentProjectChatId || activeChatId}
          onNewChat={startNewProjectChat}
          newChatDisabled={!activeSidebarChatStarted}
          onOpenChat={openChatItem}
          waitingChatIds={waitingChatIds}
          chatsLoading={sidebarChatsLoading}
          showJobs={canViewJobs}
          jobsPending={sidebarJobsPending}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
      )}
    >
      <main className="flex min-h-0 min-w-0 flex-col">
        <header className="flex min-h-[78px] min-w-0 items-center gap-2 overflow-hidden border-b border-[#282a30] bg-[#17181d] px-3 sm:gap-3 sm:px-4">
          <MobileSidebarButton onClick={() => setMobileSidebarOpen(true)} />
          <input
            ref={projectVideo.fileInputRef}
            type="file"
            accept="image/*"
            onChange={projectVideo.onImageFileChange}
            className="hidden"
          />

            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-black uppercase tracking-[0.16em] text-white">{projectTitle}</div>
              <div className="mt-1 flex min-w-0 items-center gap-2 text-[11px] font-mono text-slate-600">
                <span className="truncate">{currentProjectId || "No project id"}</span>
                <span className="text-slate-800">/</span>
                <span className="truncate text-cyan-300/70">{activeWorkspaceNamespace}</span>
              </div>
            </div>
          </header>

          <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
            <ProjectChatPanel
              projectId={currentProjectId}
              chatId={currentProjectChatId}
              projectTitle={projectTitle}
              messages={currentProjectChatMessages}
              input={projectChatInput}
              setInput={setProjectChatInput}
              onSubmit={handleProjectChatGenerate}
              isLoading={isLoading}
              canStop={activeGeneration?.kind === "project-chat"}
              onStop={stopActiveGeneration}
              canChat={currentProjectCanChat}
              endRef={projectChatEndRef}
              namespaceTabs={visibleWorkspaceTabs}
              activeNamespace={activeWorkspaceTab.id}
              activeNamespaceLabel={activeWorkspaceTab.label}
              activeNamespaceName={activeWorkspaceNamespace}
              onNamespaceChange={setActiveTab}
              namespaceContent={projectNamespaceContent}
              chatVisible={projectChatVisible}
              onToggleChat={() => setProjectChatVisible((value) => !value)}
              onOpenProject={(projectId) => {
                if (currentProjectChatId) syncChatRoute(currentProjectChatId);
                loadOldProject(projectId, { syncRoute: false, tab: "chat" });
              }}
            />
          </section>
      </main>
    </WorkspaceFrame>
  );
}

export default FormaWorkspace;

function buildChatListItems(projectHistory: any[], localChatItems: ChatListItem[] = []): ChatListItem[] {
  const groups = new Map<string, { latest: any; projectCount: number }>();

  projectHistory
    .filter((project: any) => project?.project_id)
    .forEach((project: any) => {
      const projectId = String(project.project_id);
      const chatId = String(project.chat_id || projectId).trim();
      if (!chatId) return;

      const existing = groups.get(chatId);
      if (!existing) {
        groups.set(chatId, { latest: project, projectCount: 1 });
        return;
      }

      const currentTime = Date.parse(existing.latest?.created_at || "");
      const nextTime = Date.parse(project.created_at || "");
      groups.set(chatId, {
        latest: Number.isNaN(nextTime) || nextTime <= (Number.isNaN(currentTime) ? 0 : currentTime)
          ? existing.latest
          : project,
        projectCount: existing.projectCount + 1,
      });
    });

  const savedItems = Array.from(groups.entries())
    .map(([chatId, group]) => ({
      chatId,
      title: group.latest?.title || "Untitled chat",
      projectId: String(group.latest?.project_id || ""),
      createdAt: typeof group.latest?.created_at === "string" ? group.latest.created_at : null,
      projectCount: group.projectCount,
    }));

  const merged = new Map<string, ChatListItem>();
  localChatItems.forEach((item) => {
    if (item.chatId) merged.set(item.chatId, item);
  });
  savedItems.forEach((item) => {
    const existing = merged.get(item.chatId);
    merged.set(item.chatId, {
      ...existing,
      ...item,
      createdAt: latestChatListItemDate(existing?.createdAt, item.createdAt),
      projectCount: Math.max(existing?.projectCount || 0, item.projectCount),
    });
  });

  return sortChatListItems(Array.from(merged.values()));
}

function normalizePrivateChatItems(value: any): ChatListItem[] {
  const chats = Array.isArray(value) ? value : [];
  return chats
    .map((chat: any): ChatListItem | null => {
      const chatId = typeof chat?.chat_id === "string" ? chat.chat_id.trim() : "";
      if (!chatId) return null;
      return {
        chatId,
        title: typeof chat.title === "string" && chat.title.trim() ? chat.title.trim() : NEW_PROJECT_TITLE,
        projectId: "",
        createdAt: typeof chat.updated_at === "string" ? chat.updated_at : typeof chat.created_at === "string" ? chat.created_at : null,
        projectCount: 0,
      };
    })
    .filter((item: ChatListItem | null): item is ChatListItem => Boolean(item));
}

function mergeChatListItems(primary: ChatListItem[], secondary: ChatListItem[]): ChatListItem[] {
  const merged = new Map<string, ChatListItem>();
  secondary.forEach((item) => {
    if (item.chatId) merged.set(item.chatId, item);
  });
  primary.forEach((item) => {
    if (!item.chatId) return;
    const existing = merged.get(item.chatId);
    merged.set(item.chatId, {
      ...existing,
      ...item,
      createdAt: latestChatListItemDate(existing?.createdAt, item.createdAt),
      projectCount: Math.max(existing?.projectCount || 0, item.projectCount),
    });
  });
  return sortChatListItems(Array.from(merged.values()));
}

function mergeProjectRecords(primary: any[], secondary: any[]): any[] {
  const merged = new Map<string, any>();
  primary.forEach((project: any) => {
    const projectId = project?.project_id ? String(project.project_id) : "";
    if (projectId) merged.set(projectId, project);
  });
  secondary.forEach((project: any) => {
    const projectId = project?.project_id ? String(project.project_id) : "";
    if (projectId) merged.set(projectId, project);
  });
  return Array.from(merged.values());
}

function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function projectRecordsFromChatItems(chatItems: ChatListItem[]): any[] {
  return chatItems
    .filter((item) => item.projectId)
    .map((item) => ({
      project_id: item.projectId,
      chat_id: item.chatId,
      title: item.title || "Untitled project",
      prompt: item.title || "",
      created_at: item.createdAt || chatTimestamp(),
      can_chat: true,
      creator_display: "unknown",
      creator_username: "unknown",
      creator_image_url: null,
      parts_count: 0,
      star_count: 0,
    }));
}

function WorkspacePageHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <section className="mb-6 border-b border-[#2a2c33] pb-5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="inline-flex h-11 w-11 shrink-0 items-center justify-center border border-cyan-300/30 bg-cyan-300/10 text-cyan-200">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-xl font-black uppercase tracking-[0.18em] text-white">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">{description}</p>
        </div>
      </div>
    </section>
  );
}

function ProjectRouteFallbackPanel({
  projectId,
  error,
  onHome,
  onOpenSidebar,
}: {
  projectId: string;
  error: string | null;
  onHome: () => void;
  onOpenSidebar: () => void;
}) {
  return (
    <main className="flex min-h-0 min-w-0 flex-col">
      <header className="flex min-h-[78px] items-center gap-3 border-b border-[#282a30] bg-[#17181d] px-4">
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-black uppercase tracking-[0.16em] text-white">
            {error ? "Project unavailable" : "Opening project"}
          </div>
          <div className="mt-1 truncate text-[11px] font-mono text-cyan-300/70">{projectId}</div>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 items-center justify-center p-5">
        <div className="w-full max-w-md border border-[#2c2f37] bg-[#17181d] p-6 text-center shadow-2xl shadow-black/30">
          <div className="mx-auto flex h-11 w-11 items-center justify-center border border-[#2c2f37] bg-black text-white">
            {error ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <RefreshCw className="h-5 w-5 animate-spin text-cyan-300" />}
          </div>
          <h1 className="mt-5 text-lg font-black uppercase tracking-[0.18em] text-white">
            {error ? "Project unavailable" : "Opening project"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            {error || "Loading the saved hardware plan."}
          </p>
          {error && (
            <button type="button" onClick={onHome} className="mt-5 inline-flex h-10 items-center gap-2 border border-[#2a2c33] px-4 text-xs font-black uppercase text-white transition hover:bg-white hover:text-black">
              <ArrowLeft className="h-4 w-4" />
              Back home
            </button>
          )}
        </div>
      </section>
    </main>
  );
}

function AuthRequiredRouteScreen({
  loading,
  title,
  message,
  onHome,
}: {
  loading: boolean;
  title: string;
  message: string;
  onHome: () => void;
}) {
  const { openSignIn } = useFormaAuth();
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#141519] px-5 font-sans text-slate-100">
      <div className="w-full max-w-md border border-[#2c2f37] bg-[#17181d] p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center border border-cyan-300/30 bg-cyan-300/10 text-cyan-100">
            <KeyRound className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-black uppercase tracking-[0.18em] text-white">{title}</h1>
            <p className="mt-1 text-sm text-slate-500">{loading ? "Checking session..." : message}</p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onHome}
            className="inline-flex h-10 items-center justify-center border border-[#2c2f37] px-3 text-xs font-black uppercase text-slate-200 transition hover:bg-white hover:text-black"
          >
            Home
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" })}
            className="inline-flex h-10 items-center justify-center border border-cyan-300/35 px-3 text-xs font-black uppercase text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-wait disabled:border-slate-700 disabled:text-slate-600 disabled:hover:bg-transparent disabled:hover:text-slate-600"
          >
            Sign in
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatRouteFallbackPanel({
  transition,
  onHome,
  onOpenSidebar,
}: {
  transition: ChatRouteTransition;
  onHome: () => void;
  onOpenSidebar: () => void;
}) {
  const hasProjectTarget = Boolean(transition.projectId);
  return (
    <main className="flex min-h-0 min-w-0 flex-col">
      <header className="flex min-h-[78px] min-w-0 items-center gap-2 overflow-hidden border-b border-[#282a30] bg-[#17181d] px-3 sm:gap-3 sm:px-4">
        <MobileSidebarButton onClick={onOpenSidebar} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-black uppercase tracking-[0.16em] text-white">{transition.title || "Opening chat"}</div>
          <div className="mt-1 flex min-w-0 items-center gap-2 text-[11px] font-mono text-slate-600">
            <span className="truncate">{transition.projectId || transition.chatId}</span>
            <span className="text-slate-800">/</span>
            <span className="truncate text-cyan-300/70">project.chat</span>
          </div>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 items-center justify-center bg-[#141519] p-5">
        <div className="w-full max-w-md border border-[#2c2f37] bg-[#17181d] p-6 text-center shadow-2xl shadow-black/30">
          <div className="mx-auto flex h-11 w-11 items-center justify-center border border-[#2c2f37] bg-black text-white">
            {transition.error ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <RefreshCw className="h-5 w-5 animate-spin text-cyan-300" />}
          </div>
          <h1 className="mt-5 text-lg font-black uppercase tracking-[0.18em] text-white">
            {transition.error ? "Chat unavailable" : hasProjectTarget ? "Opening project chat" : "Opening chat"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            {transition.error || (hasProjectTarget ? "Loading the active project for this chat." : "Preparing the chat workspace.")}
          </p>
          <div className="mt-4 space-y-2">
            <div className="truncate border border-[#2c2f37] bg-[#141519] px-3 py-2 text-xs font-mono text-slate-500">
              {transition.chatId}
            </div>
            {transition.projectId && (
              <div className="truncate border border-cyan-300/20 bg-cyan-300/5 px-3 py-2 text-xs font-mono text-cyan-100">
                {transition.projectId}
              </div>
            )}
          </div>
          {transition.error && (
            <button
              type="button"
              onClick={onHome}
              className="mt-5 inline-flex h-10 items-center gap-2 border border-[#2a2c33] px-4 text-xs font-black uppercase text-white transition hover:bg-white hover:text-black"
            >
              <ArrowLeft className="h-4 w-4" />
              Back home
            </button>
          )}
        </div>
      </section>
    </main>
  );
}


function VideoPanel({
  projectId,
  readOnly,
  models,
  modelsLoading,
  modelsError,
  selectedModel,
  setSelectedModel,
  mode,
  setMode,
  imageInput,
  setImageInput,
  imageOptions,
  selectedImageSources,
  setSelectedImageSources,
  defaultImage,
  sourceVideoUrl,
  setSourceVideoUrl,
  prompt,
  setPrompt,
  duration,
  setDuration,
  aspectRatio,
  setAspectRatio,
  aspectRatios,
  status,
  statusMessage,
  requestId,
  storedVideo,
  gallery,
  galleryLoading,
  galleryError,
  generationAvailable,
  generationUnavailableReason,
  reviewStatus,
  reviewMessage,
  reviewAvailable,
  reviewUnavailableReason,
  selectedReviewVideoKey,
  setSelectedReviewVideoKey,
  makeNewVideo,
  setMakeNewVideo,
  promptGenerating,
  promptMessage,
  onGenerate,
  onGeneratePrompt,
  onReview,
  onReviewVideo,
  onUploadImage,
  onUseProjectImage,
  onRefreshGallery,
  canGenerate,
  canReview,
  canMakeNewVideo,
  canGeneratePrompt,
}: {
  projectId: string | null;
  readOnly: boolean;
  models: VideoModelOption[];
  modelsLoading: boolean;
  modelsError: string | null;
  selectedModel: string;
  setSelectedModel: (value: string) => void;
  mode: VideoGenerationMode;
  setMode: (value: VideoGenerationMode) => void;
  imageInput: string;
  setImageInput: (value: string) => void;
  imageOptions: ProjectImageCandidate[];
  selectedImageSources: string[];
  setSelectedImageSources: (value: string[]) => void;
  defaultImage: string;
  sourceVideoUrl: string;
  setSourceVideoUrl: (value: string) => void;
  prompt: string;
  setPrompt: (value: string) => void;
  duration: string;
  setDuration: (value: string) => void;
  aspectRatio: string;
  setAspectRatio: (value: string) => void;
  aspectRatios: string[];
  status: string;
  statusMessage: string | null;
  requestId: string | null;
  storedVideo: StoredVideoInfo | null;
  gallery: StoredVideoInfo[];
  galleryLoading: boolean;
  galleryError: string | null;
  generationAvailable: boolean;
  generationUnavailableReason: string | null;
  reviewStatus: string;
  reviewMessage: string | null;
  reviewAvailable: boolean;
  reviewUnavailableReason: string | null;
  selectedReviewVideoKey: string | null;
  setSelectedReviewVideoKey: (value: string | null) => void;
  makeNewVideo: boolean;
  setMakeNewVideo: (value: boolean) => void;
  promptGenerating: boolean;
  promptMessage: string | null;
  onGenerate: () => void;
  onGeneratePrompt: () => void;
  onReview: () => void;
  onReviewVideo: (video: StoredVideoInfo) => void;
  onUploadImage: () => void;
  onUseProjectImage: () => void;
  onRefreshGallery: () => void;
  canGenerate: boolean;
  canReview: boolean;
  canMakeNewVideo: boolean;
  canGeneratePrompt: boolean;
}) {
  const modeModels = models.filter((model) => model.mode === mode);
  const sourceVideos = gallery
    .map((video, index) => ({
      video,
      url: videoSourceUrl(video),
      label: videoLabel(video, `Video ${index + 1}`),
    }))
    .filter((item) => item.url);
  const videoToVideoAvailable = sourceVideos.length > 0;
  const selectedImagePreviewSource = selectedImageSources[0] || imageInput;
  const imagePreview = mode === "image-to-video" ? previewableImageSrc(selectedImagePreviewSource) : null;
  const sourceVideoPreview = mode === "video-to-video" ? sourceVideoUrl : "";
  const isGenerating = status === "loading" || Boolean(requestId && !storedVideo && !isFinalVideoStatus(status));
  const isReviewing = reviewStatus === "loading";
  const generateDisabled = !canGenerate || isGenerating || !modeModels.length;
  const reviewDisabled = !canReview || isReviewing;
  const savedHref = readOnly ? null : storedVideo?.publicUrl || null;
  const allProjectImagesSelected = imageOptions.length > 0 && imageOptions.every((candidate) => selectedImageSources.includes(candidate.src));
  const toggleImageSource = (source: string) => {
    setSelectedImageSources(
      selectedImageSources.includes(source)
        ? selectedImageSources.filter((item) => item !== source)
        : [...selectedImageSources, source]
    );
  };

  if (!generationAvailable) {
    return (
      <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
        <div className="mx-auto max-w-6xl">
          <section className="border border-[#2a2c33] bg-[#17181d] p-4 sm:p-5">
            <div className="flex flex-col gap-4 border-b border-[#2a2c33] pb-5 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Film className="h-4 w-4 text-cyan-400" />
                  <h2 className="text-base font-black uppercase tracking-[0.16em] text-white">Video</h2>
                </div>
                <div className="mt-2 truncate font-mono text-[11px] text-slate-600">{projectId || "No project id"}</div>
              </div>
              <button
                type="button"
                onClick={onReview}
                disabled={reviewDisabled}
                className="inline-flex h-11 shrink-0 items-center justify-center gap-2 border border-cyan-300/40 px-4 text-xs font-black uppercase tracking-[0.12em] text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isReviewing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Review
              </button>
            </div>

            {readOnly && (
              <div className="mt-5 border border-[#2a2c33] bg-black/25 p-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                Read-only project. Video actions are available only to the owner.
              </div>
            )}

            <div className="mt-5 border border-cyan-500/30 bg-cyan-950/20 p-4">
              <div className="flex items-start gap-3">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
                <div className="min-w-0">
                  <div className="text-xs font-black uppercase tracking-[0.14em] text-cyan-200">Alpha</div>
                  <p className="mt-2 text-sm leading-6 text-slate-300">
                    We are in alpha and video generation is coming soon.
                  </p>
                  {generationUnavailableReason && (
                    <p className="mt-2 break-words text-xs leading-5 text-slate-500">{generationUnavailableReason}</p>
                  )}
                </div>
              </div>
            </div>

            <VideoReviewStatus
              status={reviewStatus}
              message={reviewMessage}
              available={reviewAvailable}
              unavailableReason={reviewUnavailableReason}
              isReviewing={isReviewing}
              makeNewVideo={makeNewVideo}
              setMakeNewVideo={setMakeNewVideo}
              canMakeNewVideo={canMakeNewVideo}
            />

            <VideoGallery
              videos={gallery}
              loading={galleryLoading}
              error={galleryError}
              onRefresh={onRefreshGallery}
              selectedKey={selectedReviewVideoKey}
              onSelect={setSelectedReviewVideoKey}
              onReview={onReviewVideo}
              canReview={canReview}
              canOpenAssets={!readOnly}
              reviewing={isReviewing}
            />
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <div className="mx-auto grid max-w-6xl gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(360px,0.6fr)]">
        <section className="min-w-0 border border-[#2a2c33] bg-[#17181d] p-4 sm:p-5">
          <div className="mb-5 flex flex-col gap-4 border-b border-[#2a2c33] pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Film className="h-4 w-4 text-cyan-400" />
                <h2 className="text-base font-black uppercase tracking-[0.16em] text-white">Video</h2>
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-slate-600">{projectId || "No project id"}</div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                type="button"
                onClick={onReview}
                disabled={reviewDisabled}
                className="inline-flex h-11 items-center justify-center gap-2 border border-cyan-300/40 px-4 text-xs font-black uppercase tracking-[0.12em] text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isReviewing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Review
              </button>
              <button
                type="button"
                onClick={onGenerate}
                disabled={generateDisabled}
                className="inline-flex h-11 items-center justify-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-[0.12em] text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isGenerating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
                Generate
              </button>
            </div>
          </div>

          {readOnly && (
            <div className="mb-5 border border-[#2a2c33] bg-black/25 p-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
              Read-only project. Video actions are available only to the owner.
            </div>
          )}

          <div className="mb-4 grid grid-cols-2 border border-[#2a2c33]">
            {([
              { value: "image-to-video" as VideoGenerationMode, label: "Image" },
              { value: "video-to-video" as VideoGenerationMode, label: "Video", disabled: !videoToVideoAvailable },
            ]).map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  if (!item.disabled) setMode(item.value);
                }}
                disabled={item.disabled}
                className={`flex h-11 items-center justify-center gap-2 border-r border-[#2a2c33] text-xs font-black uppercase last:border-r-0 ${
                  mode === item.value ? "bg-white text-black" : "bg-black text-slate-500 hover:text-white"
                } disabled:cursor-not-allowed disabled:text-slate-800 disabled:hover:text-slate-800`}
              >
                {item.value === "video-to-video" ? <Film className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                {item.label}
              </button>
            ))}
          </div>

          <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_170px_180px]">
            <label className="block text-xs font-black uppercase tracking-[0.14em] text-slate-500">
              Model
              <select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                disabled={modelsLoading || !modeModels.length}
                className="mt-2 h-11 w-full border border-[#2a2c33] bg-black px-3 text-sm normal-case tracking-normal text-white outline-none focus:border-cyan-300 disabled:opacity-50"
              >
                {!modeModels.length && <option value="">No models</option>}
                {modeModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-black uppercase tracking-[0.14em] text-slate-500">
              Aspect Ratio
              <select
                value={aspectRatio}
                onChange={(event) => setAspectRatio(event.target.value)}
                className="mt-2 h-11 w-full border border-[#2a2c33] bg-black px-3 text-sm normal-case tracking-normal text-white outline-none focus:border-cyan-300"
              >
                {aspectRatios.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <div>
              <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Duration</div>
              <div className="mt-2 grid grid-cols-2 border border-[#2a2c33]">
                {["5", "10"].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setDuration(value)}
                    className={`h-11 border-r border-[#2a2c33] text-xs font-black uppercase last:border-r-0 ${
                      duration === value ? "bg-white text-black" : "bg-black text-slate-500 hover:text-white"
                    }`}
                  >
                    {value}s
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="video-prompt" className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">
                Prompt
              </label>
              <button
                type="button"
                onClick={onGeneratePrompt}
                disabled={!canGeneratePrompt}
                className="inline-flex h-9 items-center gap-2 border border-cyan-300/40 px-3 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100 hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
                title="Generate an image-to-video prompt from project namespaces"
              >
                {promptGenerating ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Generate prompt
              </button>
            </div>
            <textarea
              id="video-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={VIDEO_PROMPT_MAX_CHARS}
              placeholder="Slow orbit, reveal ports, show display glow."
              className="mt-2 min-h-[132px] w-full resize-none border border-[#2a2c33] bg-black px-3 py-3 text-sm normal-case leading-6 tracking-normal text-white outline-none placeholder:text-slate-700 focus:border-cyan-300"
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              {promptMessage ? (
                <p className="break-words text-[11px] leading-5 text-slate-500">{promptMessage}</p>
              ) : (
                <span />
              )}
              <span className={`font-mono text-[10px] ${prompt.length > VIDEO_PROMPT_MAX_CHARS - 120 ? "text-amber-300" : "text-slate-600"}`}>
                {prompt.length}/{VIDEO_PROMPT_MAX_CHARS}
              </span>
            </div>
          </div>

          {mode === "image-to-video" ? (
            <div className="mt-5 border border-[#2a2c33] bg-[#141519] p-3">
              <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Image Source</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onUploadImage}
                    className="inline-flex h-9 items-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black"
                  >
                    <Paperclip className="h-4 w-4" />
                    Upload
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedImageSources(allProjectImagesSelected ? [] : imageOptions.map((candidate) => candidate.src))}
                    disabled={!imageOptions.length}
                    className="inline-flex h-9 items-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Layers className="h-4 w-4" />
                    {allProjectImagesSelected ? "Clear" : "All"}
                  </button>
                  <button
                    type="button"
                    onClick={onUseProjectImage}
                    disabled={!defaultImage}
                    className="inline-flex h-9 items-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Eye className="h-4 w-4" />
                    First
                  </button>
                </div>
              </div>

              {imageOptions.length > 0 && (
                <div className="mb-3 grid gap-2 sm:grid-cols-3">
                  {imageOptions.map((candidate) => {
                    const selected = selectedImageSources.includes(candidate.src);
                    return (
                      <button
                        key={candidate.src}
                        type="button"
                        onClick={() => toggleImageSource(candidate.src)}
                        className={`min-w-0 border p-2 text-left transition ${
                          selected ? "border-cyan-300 bg-cyan-300/10 text-cyan-100" : "border-[#2a2c33] bg-black text-slate-500 hover:border-slate-500 hover:text-white"
                        }`}
                        aria-pressed={selected}
                      >
                        <div className="relative h-20 overflow-hidden bg-black">
                          <img src={candidate.src} alt={candidate.label} className="h-full w-full object-cover" />
                          <span className={`absolute right-2 top-2 flex h-5 w-5 items-center justify-center border text-[10px] font-black ${
                            selected ? "border-cyan-200 bg-cyan-200 text-black" : "border-white/40 bg-black/60 text-white"
                          }`}>
                            {selected ? <CheckCircle className="h-3.5 w-3.5" /> : null}
                          </span>
                        </div>
                        <div className="mt-2 truncate text-[10px] font-black uppercase tracking-[0.12em]">{candidate.label}</div>
                      </button>
                    );
                  })}
                </div>
              )}

              <input
                value={imageInput}
                onChange={(event) => {
                  setImageInput(event.target.value);
                  setSelectedImageSources([]);
                }}
                placeholder="https://... or data:image/..."
                className="h-11 w-full border border-[#2a2c33] bg-black px-3 font-mono text-xs text-white outline-none placeholder:text-slate-700 focus:border-cyan-300"
              />
              <div className="mt-2 text-[11px] leading-5 text-slate-600">
                {selectedImageSources.length
                  ? `${selectedImageSources.length} project image${selectedImageSources.length === 1 ? "" : "s"} selected.`
                  : "No project images selected; the manual image field will be used."}
              </div>
            </div>
          ) : (
            <label className="mt-5 block text-xs font-black uppercase tracking-[0.14em] text-slate-500">
              Source Video
              <select
                value={sourceVideoUrl}
                onChange={(event) => setSourceVideoUrl(event.target.value)}
                disabled={!sourceVideos.length}
                className="mt-2 h-11 w-full border border-[#2a2c33] bg-black px-3 text-sm normal-case tracking-normal text-white outline-none focus:border-cyan-300 disabled:opacity-50"
              >
                {!sourceVideos.length && <option value="">No saved videos</option>}
                {sourceVideos.map((item) => (
                  <option key={item.url} value={item.url}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <VideoGallery
            videos={gallery}
            loading={galleryLoading}
            error={galleryError}
            onRefresh={onRefreshGallery}
            selectedKey={selectedReviewVideoKey}
            onSelect={setSelectedReviewVideoKey}
            onReview={onReviewVideo}
            canReview={canReview}
            canOpenAssets={!readOnly}
            reviewing={isReviewing}
          />
        </section>

        <aside className="min-w-0 border border-[#2a2c33] bg-[#17181d] p-4 sm:p-5">
          <div className="aspect-video overflow-hidden border border-[#2a2c33] bg-black">
            {mode === "video-to-video" && sourceVideoPreview ? (
              <video src={sourceVideoPreview} controls preload="metadata" className="h-full w-full object-contain" />
            ) : imagePreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={imagePreview} alt="Video source preview" className="h-full w-full object-contain" />
            ) : (
              <div className="flex h-full items-center justify-center text-xs font-black uppercase tracking-[0.18em] text-slate-700">
                No source
              </div>
            )}
          </div>
          {mode === "image-to-video" && selectedImageSources.length > 0 && (
            <div className="mt-2 border border-[#2a2c33] bg-[#141519] px-3 py-2 text-[11px] leading-5 text-slate-500">
              Previewing the first selected image. Generate will queue {selectedImageSources.length} image source{selectedImageSources.length === 1 ? "" : "s"}.
            </div>
          )}

          <div className="mt-4 border border-[#2a2c33] bg-[#141519] p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Status</span>
              <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] font-black uppercase ${statusTone(status)}`}>
                {status === "failed" ? <AlertTriangle className="h-3.5 w-3.5" /> : status === "succeeded" ? <CheckCircle className="h-3.5 w-3.5" /> : <RefreshCw className={`h-3.5 w-3.5 ${isGenerating ? "animate-spin" : ""}`} />}
                {status}
              </span>
            </div>
            {requestId && <div className="mt-3 truncate font-mono text-[11px] text-slate-600">{requestId}</div>}
            {statusMessage && <p className="mt-3 break-words text-xs leading-5 text-slate-400">{statusMessage}</p>}
            {modelsError && <p className="mt-3 break-words text-xs leading-5 text-amber-300">{modelsError}</p>}
          </div>

          <VideoReviewStatus
            status={reviewStatus}
            message={reviewMessage}
            available={reviewAvailable}
            unavailableReason={reviewUnavailableReason}
            isReviewing={isReviewing}
            makeNewVideo={makeNewVideo}
            setMakeNewVideo={setMakeNewVideo}
            canMakeNewVideo={canMakeNewVideo}
          />

          {storedVideo && (
            <div className="mt-4 border border-emerald-500/30 bg-emerald-950/20 p-4">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-emerald-300">
                <CheckCircle className="h-4 w-4" />
                Saved
              </div>
              {savedHref ? (
                <a
                  href={savedHref}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex max-w-full items-center gap-2 border border-emerald-400/40 px-3 py-2 text-xs font-black uppercase text-emerald-100 hover:bg-emerald-300 hover:text-black"
                >
                  <ExternalLink className="h-4 w-4 shrink-0" />
                  Open saved video
                </a>
              ) : (
                <div className="mt-3 break-all font-mono text-xs leading-5 text-emerald-100">{storedVideo.s3Uri || storedVideo.key}</div>
              )}
              {storedVideo.key && <div className="mt-3 break-all font-mono text-[11px] leading-5 text-emerald-300/70">{storedVideo.key}</div>}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function VideoReviewStatus({
  status,
  message,
  available,
  unavailableReason,
  isReviewing,
  makeNewVideo,
  setMakeNewVideo,
  canMakeNewVideo,
}: {
  status: string;
  message: string | null;
  available: boolean;
  unavailableReason: string | null;
  isReviewing: boolean;
  makeNewVideo: boolean;
  setMakeNewVideo: (value: boolean) => void;
  canMakeNewVideo: boolean;
}) {
  return (
    <div className="mt-4 border border-[#2a2c33] bg-[#141519] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Review</span>
        <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] font-black uppercase ${statusTone(status)}`}>
          {status === "failed" ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : status === "succeeded" ? (
            <CheckCircle className="h-3.5 w-3.5" />
          ) : isReviewing ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" />
          )}
          {status}
        </span>
      </div>
      <label className={`mt-3 flex min-h-10 items-center gap-3 border border-[#2a2c33] bg-black px-3 py-2 text-xs font-black uppercase tracking-[0.12em] ${
        canMakeNewVideo ? "text-cyan-100" : "text-slate-600"
      }`}>
        <input
          type="checkbox"
          checked={makeNewVideo}
          onChange={(event) => setMakeNewVideo(event.target.checked)}
          disabled={!canMakeNewVideo || isReviewing}
          className="h-4 w-4 accent-cyan-300 disabled:cursor-not-allowed"
        />
        <span>Make new video</span>
      </label>
      {message && <p className="mt-3 break-words text-xs leading-5 text-slate-400">{message}</p>}
      {!available && unavailableReason && <p className="mt-3 break-words text-xs leading-5 text-amber-300">{unavailableReason}</p>}
    </div>
  );
}

function VideoGallery({
  videos,
  loading,
  error,
  onRefresh,
  selectedKey,
  onSelect,
  onReview,
  canReview,
  canOpenAssets,
  reviewing,
}: {
  videos: StoredVideoInfo[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  selectedKey: string | null;
  onSelect: (value: string | null) => void;
  onReview: (video: StoredVideoInfo) => void;
  canReview: boolean;
  canOpenAssets: boolean;
  reviewing: boolean;
}) {
  return (
    <div className="mt-5 border border-[#2a2c33] bg-[#141519] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Film className="h-4 w-4 text-cyan-400" />
          <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Gallery</div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={!canOpenAssets}
          className="flex h-9 w-9 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-400"
          title={canOpenAssets ? "Refresh gallery" : "Videos are available only on projects you generated."}
          aria-label="Refresh gallery"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="mb-3 break-words border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-300">
          {error}
        </div>
      )}

      {loading && !videos.length ? (
        <div className="border border-[#2a2c33] bg-black p-4 text-xs font-bold uppercase tracking-[0.12em] text-slate-600">
          Loading
        </div>
      ) : videos.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {videos.map((video, index) => {
            const key = videoIdentity(video, `video-${index}`);
            const reviewable = Boolean(videoSourceUrl(video));
            return (
              <VideoGalleryItem
                key={key}
                video={video}
                identity={key}
                selected={selectedKey === key}
                onSelect={() => onSelect(key)}
                onReview={() => onReview(video)}
                canReview={canReview && reviewable}
                canOpenAssets={canOpenAssets}
                reviewing={reviewable && reviewing && selectedKey === key}
                reviewable={reviewable}
              />
            );
          })}
        </div>
      ) : (
        <div className="border border-[#2a2c33] bg-black p-4 text-xs font-bold uppercase tracking-[0.12em] text-slate-600">
          Empty
        </div>
      )}
    </div>
  );
}

function VideoGalleryItem({
  video,
  identity,
  selected,
  onSelect,
  onReview,
  canReview,
  canOpenAssets,
  reviewing,
  reviewable,
}: {
  video: StoredVideoInfo;
  identity: string;
  selected: boolean;
  onSelect: () => void;
  onReview: () => void;
  canReview: boolean;
  canOpenAssets: boolean;
  reviewing: boolean;
  reviewable: boolean;
}) {
  const playableUrl = canOpenAssets ? videoSourceUrl(video) || null : null;
  const openUrl = canOpenAssets ? playableUrl || null : null;
  const label = videoLabel(video);
  const prompt = videoPromptText(video);

  return (
    <article className={`min-w-0 overflow-hidden border bg-black transition ${
      selected ? "border-cyan-300 shadow-[0_0_0_1px_rgba(103,232,249,0.35)]" : "border-[#2a2c33]"
    }`}>
      <div className="aspect-video bg-black">
        {playableUrl ? (
          <video src={playableUrl} controls preload="metadata" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs font-black uppercase tracking-[0.16em] text-slate-700">
            Video saved
          </div>
        )}
      </div>
      <div className="border-t border-[#2a2c33] p-3">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-mono text-[11px] text-slate-400">{label}</div>
            <div className="mt-1 truncate font-mono text-[10px] text-slate-700">{identity}</div>
          </div>
          <span className={`shrink-0 border px-2 py-1 text-[10px] font-black uppercase ${
            selected ? "border-cyan-300/60 bg-cyan-950/30 text-cyan-200" : "border-[#2a2c33] text-slate-600"
          }`}>
            {selected ? "Selected" : reviewable ? "Reviewable" : "No URL"}
          </span>
        </div>
        <div className="mt-3 border border-[#2a2c33] bg-[#141519] p-3">
          <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-600">Prompt</div>
          <p className="mt-2 max-h-28 overflow-y-auto break-words text-xs leading-5 text-slate-400">
            {prompt || "No prompt saved for this video."}
          </p>
        </div>
        {video.key && <div className="mt-2 break-all font-mono text-[10px] leading-4 text-slate-600">{video.key}</div>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-600">{formatBytes(video.sizeBytes || 0)}</span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSelect}
              disabled={!reviewable || !canOpenAssets}
              className="inline-flex h-8 items-center gap-1.5 border border-[#2a2c33] px-2 text-[10px] font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
              title={canOpenAssets ? (reviewable ? "Select video for review" : "This saved video needs an HTTP(S) URL before review") : "Videos are available only on projects you generated."}
            >
              {selected ? <CheckCircle className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              Select
            </button>
            <button
              type="button"
              onClick={() => {
                onSelect();
                onReview();
              }}
              disabled={!canReview || reviewing}
              className="inline-flex h-8 items-center gap-1.5 border border-cyan-300/40 px-2 text-[10px] font-black uppercase text-cyan-100 hover:bg-cyan-300 hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
              title={reviewable ? "Review selected video" : "This saved video needs an HTTP(S) URL before review"}
            >
              {reviewing ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              Review
            </button>
            {openUrl ? (
              <a
                href={openUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 border border-[#2a2c33] px-2 text-[10px] font-black uppercase text-white hover:bg-white hover:text-black"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open
              </a>
            ) : (
              <span className="truncate font-mono text-[10px] text-slate-600">{video.s3Uri || "-"}</span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function ProjectChatPanel({
  projectId,
  chatId,
  projectTitle,
  messages,
  input,
  setInput,
  onSubmit,
  isLoading,
  canStop,
  onStop,
  canChat,
  endRef,
  namespaceTabs,
  activeNamespace,
  activeNamespaceLabel,
  activeNamespaceName,
  onNamespaceChange,
  namespaceContent,
  chatVisible,
  onToggleChat,
  onOpenProject,
}: {
  projectId: string | null;
  chatId: string | null;
  projectTitle: string;
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
  isLoading: boolean;
  canStop: boolean;
  onStop: () => void;
  canChat: boolean;
  endRef: React.RefObject<HTMLDivElement>;
  namespaceTabs: typeof workspaceTabs;
  activeNamespace: string;
  activeNamespaceLabel: string;
  activeNamespaceName: string;
  onNamespaceChange: (value: string) => void;
  namespaceContent: React.ReactNode;
  chatVisible: boolean;
  onToggleChat: () => void;
  onOpenProject: (projectId: string) => void;
}) {
  const effectiveChatVisible = canChat && chatVisible;
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-[#141519]">
      <div className="flex min-h-[62px] flex-wrap items-center justify-between gap-3 border-b border-[#2a2c33] bg-[#17181d] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {canChat ? <MessageSquare className="h-4 w-4 text-cyan-300" /> : <Eye className="h-4 w-4 text-cyan-300" />}
            <h2 className="truncate text-sm font-black uppercase tracking-[0.18em] text-white">
              {canChat ? "Build Chat" : "Read-only project"}
            </h2>
          </div>
          <div className="mt-1 truncate text-[11px] text-slate-500">
            {canChat ? `Active project item: ${projectTitle}` : "Public project preview"}
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {canChat && (
            <button
              type="button"
              onClick={onToggleChat}
              className={`inline-flex h-10 items-center gap-2 border px-3 text-xs font-black uppercase ${
                chatVisible
                  ? "border-cyan-300/40 bg-cyan-300/10 text-cyan-100 hover:bg-white hover:text-black"
                  : "border-[#2a2c33] bg-[#111216] text-slate-400 hover:bg-white hover:text-black"
              }`}
              aria-pressed={chatVisible}
              aria-label={chatVisible ? "Hide chat panel" : "Show chat panel"}
              title={chatVisible ? "Hide chat panel" : "Show chat panel"}
            >
              <MessageSquare className="h-4 w-4" />
              <span className="hidden sm:inline">{chatVisible ? "Hide chat" : "Show chat"}</span>
            </button>
          )}
          <div className="truncate border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 font-mono text-[11px] text-cyan-100">
            {activeNamespaceName}
          </div>
          {canChat && (
            <div className="truncate border border-[#2a2c33] px-3 py-2 font-mono text-[11px] text-slate-500">
              {chatId || projectId || "No chat"}
            </div>
          )}
        </div>
      </div>

      <nav className="flex min-h-[48px] min-w-0 overflow-x-auto border-b border-[#2a2c33] bg-[#111216]">
        {namespaceTabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeNamespace === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onNamespaceChange(tab.id)}
              className={`inline-flex h-12 min-w-12 items-center justify-center gap-2 border-r border-[#2a2c33] px-4 text-xs font-black uppercase tracking-widest transition last:border-r-0 ${
                active ? "bg-white text-black" : "bg-[#111216] text-slate-500 hover:text-white"
              }`}
              aria-pressed={active}
              title={`${tab.label} / ${workspaceNamespaceForTab(tab.id)}`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className={active ? "inline" : "hidden sm:inline"}>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <div className={`grid min-h-0 flex-1 grid-cols-1 overflow-y-auto xl:overflow-hidden ${
        effectiveChatVisible ? "xl:grid-cols-[minmax(360px,0.78fr)_minmax(0,1.22fr)]" : "xl:grid-cols-1"
      }`}>
        {effectiveChatVisible && (
        <div className="flex min-h-[520px] min-w-0 flex-col overflow-hidden xl:min-h-0">
          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-5 pb-6">
            <div className="mx-auto flex min-w-0 max-w-3xl flex-col gap-3">
              {messages.length ? (
                messages.map((message) => {
                  const isUser = message.role === "user";
                  const isSystem = message.role === "system";
                  return (
                    <div key={message.id} className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`min-w-0 max-w-[92%] overflow-hidden border px-4 py-3 ${
                          isUser
                            ? "border-cyan-300/30 bg-cyan-300/10 text-cyan-50"
                            : message.status === "error"
                              ? "border-rose-400/30 bg-rose-950/25 text-rose-100"
                              : message.status === "cancelled"
                                ? "border-amber-300/30 bg-amber-950/20 text-amber-50"
                              : isSystem
                                ? "border-[#2a2c33] bg-black/25 text-slate-400"
                                : "border-[#2a2c33] bg-[#17181d] text-slate-200"
                        }`}
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                          <span>{isUser ? "You" : isSystem ? "Context" : "Forma"}</span>
                          <span className="text-slate-700">/</span>
                          <span suppressHydrationWarning>{formatChatTimestamp(message.timestamp)}</span>
                          {message.status === "loading" && <RefreshCw className="h-3 w-3 animate-spin text-cyan-300" />}
                          {message.status === "cancelled" && <Square className="h-3 w-3 fill-current text-amber-300" />}
                        </div>
                        <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                        <AgentPipelineProgressView progress={message.pipelineProgress} status={message.status} compact />
                        {message.projectId && message.projectId !== projectId && (
                          <button
                            type="button"
                            onClick={() => onOpenProject(message.projectId || "")}
                            className="mt-3 inline-flex h-9 items-center gap-2 border border-emerald-300/40 px-3 text-xs font-black uppercase text-emerald-100 hover:bg-emerald-300 hover:text-black"
                          >
                            <Eye className="h-4 w-4" />
                            Open project
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="border border-[#2a2c33] bg-[#17181d] p-5 text-sm leading-6 text-slate-500">
                  This chat has no project messages yet.
                </div>
              )}
              <div ref={endRef} />
            </div>
          </div>

          <form onSubmit={onSubmit} className="fixed bottom-0 left-0 right-0 z-30 shrink-0 border-y border-[#2a2c33] bg-[#111216]/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:p-4 md:sticky md:bottom-0 md:left-auto md:right-auto md:z-20 md:border-b-0 md:pb-4">
            <div className="mx-auto max-w-3xl">
              <div className="relative">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      if (isLoading) return;
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={`Ask about ${activeNamespaceLabel.toLowerCase()}...`}
                  className="min-h-[92px] w-full resize-none border border-[#2c2f37] bg-[#0f1014] p-4 pr-16 text-sm leading-7 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300"
                />
                <button
                  type={canStop ? "button" : "submit"}
                  onClick={canStop ? onStop : undefined}
                  disabled={!canStop && (isLoading || !projectId || !input.trim())}
                  className="absolute bottom-4 right-4 inline-flex h-10 w-10 items-center justify-center bg-white text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label={canStop ? "Stop generation" : "Generate project from chat"}
                  title={canStop ? "Stop generation" : `Generate project from ${activeNamespaceName}`}
                >
                  {canStop ? <Square className="h-4 w-4 fill-current" /> : isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </form>
          <div className="h-[172px] shrink-0 md:hidden" aria-hidden="true" />
        </div>
        )}

        <div className={`min-h-[520px] min-w-0 overflow-hidden border-t border-[#2a2c33] xl:min-h-0 xl:border-t-0 ${
          effectiveChatVisible ? "xl:border-l" : ""
        }`}>
          {namespaceContent}
        </div>
      </div>
    </div>
  );
}

function AgentPipelineProgressView({
  progress,
  status,
  compact = false,
}: {
  progress?: AgentPipelineProgress | null;
  status?: ChatMessage["status"];
  compact?: boolean;
}) {
  if (!progress) return null;

  const steps = progress.steps.length ? progress.steps : defaultAgentPipelineSteps;
  const events = normalizeAgentPipelineEvents(progress.events);
  const lastEvent = latestPipelineEvent(events);
  const activeStep = activePipelineStep({ ...progress, steps });
  const activeStepId = activeStep?.id || null;
  const nowMs = Date.now();
  const startedMs = timestampMs(progress.startedAt);
  const elapsedSeconds = startedMs === null ? null : Math.max(1, Math.round((nowMs - startedMs) / 1000));
  const lastEventMs = pipelineEventTimestampMs(lastEvent);
  const quietMs = lastEventMs === null ? null : nowMs - lastEventMs;
  const isLoading = status === "loading";
  const isCancelled = status === "cancelled";
  const hasFailedEvent = events.some((event) => isFailedPipelineStatus(event.status));
  const isError = status === "error" || hasFailedEvent;
  const waitingForFirstEvent = isLoading && !events.length && startedMs !== null && nowMs - startedMs >= PIPELINE_STALE_AFTER_MS;
  const backendQuiet = isLoading && quietMs !== null && quietMs >= PIPELINE_STALE_AFTER_MS;
  const completedCount = completedPipelineStepCount({ ...progress, steps });
  const progressPercent = Math.min(100, Math.max(6, Math.round((completedCount / Math.max(steps.length, 1)) * 100)));
  const visibleEvents = events.slice(compact ? -4 : -6);
  const signalLabel = isError
    ? "error"
    : isCancelled
    ? "stopped"
    : progress.synced
    ? backendQuiet
      ? "backend quiet"
      : "backend synced"
    : waitingForFirstEvent
      ? "waiting for job event"
      : "estimated";
  const signalTone = isError
    ? "border-rose-400/35 bg-rose-950/25 text-rose-200"
    : isCancelled
    ? "border-amber-300/35 bg-amber-950/20 text-amber-100"
    : backendQuiet || waitingForFirstEvent
    ? "border-amber-400/35 bg-amber-950/25 text-amber-200"
    : progress.synced
      ? "border-cyan-300/30 bg-cyan-950/25 text-cyan-100"
      : "border-slate-500/25 bg-black/25 text-slate-400";

  return (
    <div className="mt-3 border border-[#2a2c33] bg-black/25 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Agent pipeline</span>
            <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] font-black uppercase ${signalTone}`}>
              {isError ? <AlertTriangle className="h-3 w-3" /> : isCancelled ? <Square className="h-3 w-3 fill-current" /> : isLoading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
              {signalLabel}
            </span>
          </div>
          {progress.jobId && (
            <div className="mt-1 truncate font-mono text-[10px] text-slate-600">{progress.jobId}</div>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[11px] font-black text-slate-300">{completedCount}/{steps.length}</div>
          <div className="text-[10px] uppercase text-slate-600">{formatDurationSeconds(elapsedSeconds)}</div>
        </div>
      </div>

      <div className="mt-3 h-1.5 bg-[#111216]">
        <div className={`h-full ${isError ? "bg-rose-300" : isCancelled ? "bg-amber-300" : backendQuiet || waitingForFirstEvent ? "bg-amber-300" : "bg-cyan-300"}`} style={{ width: `${progressPercent}%` }} />
      </div>

      <div className="mt-3 flex min-w-0 items-start gap-2 border border-[#25272e] bg-[#111216] p-3">
        {isError ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" /> : isCancelled ? <Square className="mt-0.5 h-4 w-4 shrink-0 fill-current text-amber-300" /> : isLoading ? <RefreshCw className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-cyan-300" /> : <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0">
          <div className="truncate text-xs font-black uppercase text-white">{activeStep?.label || "Preparing job"}</div>
          <div className="mt-1 truncate text-[11px] font-bold text-cyan-200">{activeStep?.agent || "Forma runtime"}</div>
          {activeStep?.description && !compact && (
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500">{activeStep.description}</div>
          )}
          {lastEvent && (
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase text-slate-500">
              <span>last: {lastEvent.label || lastEvent.step_id}</span>
              <span>{String(lastEvent.status).replace(/_/g, " ")}</span>
              <span>{formatPipelineAge(lastEvent.observed_at, nowMs)} ago</span>
            </div>
          )}
        </div>
      </div>

      {(backendQuiet || waitingForFirstEvent) && (
        <div className="mt-2 flex gap-2 border border-amber-400/30 bg-amber-950/20 p-2 text-[11px] leading-4 text-amber-100">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            {events.length
              ? `No new backend event for ${formatDurationSeconds(Math.round((quietMs || 0) / 1000))}. Waiting on the active provider or backend call.`
              : "No backend event has been persisted yet. The job poller is still active."}
          </span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {steps.map((step) => (
          <span
            key={step.id}
            className="inline-flex items-center gap-1.5 border border-[#25272e] bg-[#111216] px-2 py-1 text-[10px] text-slate-500"
            title={`${step.agent}: ${step.label}`}
          >
            <PipelineStepDot status={pipelineStepStatus({ ...progress, steps }, step, activeStepId)} />
            <span className="max-w-[120px] truncate">{step.label}</span>
          </span>
        ))}
      </div>

      <div className="mt-3 border-t border-[#25272e] pt-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-600">Recent events</span>
          <span className="font-mono text-[10px] text-slate-600">{events.length}</span>
        </div>
        {visibleEvents.length ? (
          <div className="space-y-1.5">
            {visibleEvents.map((event, index) => {
              const details = formatPipelineDetails(event.details);
              return (
                <div key={`${event.step_id}-${event.status}-${event.observed_at || index}`} className="min-w-0 border border-[#25272e] bg-[#0f1014] px-2 py-1.5">
                  <div className="flex min-w-0 flex-wrap items-center gap-2 text-[10px] uppercase">
                    <span className="max-w-[160px] truncate font-black text-slate-300">{event.label || event.step_id}</span>
                    <span className={`${isFailedPipelineStatus(event.status) ? "text-rose-300" : isCompletedPipelineStatus(event.status) ? "text-emerald-300" : "text-cyan-300"}`}>
                      {String(event.status).replace(/_/g, " ")}
                    </span>
                    <span className="text-slate-600">{formatPipelineAge(event.observed_at, nowMs)} ago</span>
                  </div>
                  {details && !compact && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500">{details}</div>}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="border border-[#25272e] bg-[#0f1014] px-2 py-2 text-[11px] leading-4 text-slate-500">
            Polling job metadata. Backend pipeline events will appear here as agents report progress.
          </div>
        )}
      </div>
    </div>
  );
}
