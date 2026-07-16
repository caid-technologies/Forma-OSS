"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SignInButton, UserButton, useAuth, useClerk, useUser } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactFlow, {
  Background,
  Controls,
  Node,
  Edge,
  Handle,
  NodeProps,
  Position,
  useNodesState,
  useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import MechanicalScene from "../components/mechanical-scene";
import {
  Sparkles,
  Wrench,
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
  Download,
  Database,
  ArrowRight,
  ArrowLeft,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  Plus,
  Battery,
  Monitor,
  Printer,
  Sliders,
  Info,
  Layers,
  Volume2,
  Paperclip,
  X,
  ExternalLink,
  Handshake,
  KeyRound,
  Terminal,
  MessageSquare,
  Star,
  Clock3,
  Wifi,
  WifiOff,
} from "lucide-react";

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
const VIDEO_POLL_INTERVAL_MS = 4000;
const VIDEO_PROMPT_MAX_CHARS = 2500;
const LOG_POLL_INTERVAL_MS = 5000;
const CHAT_THREAD_STORAGE_PREFIX = "blueprint.chat.";
const CHAT_INDEX_STORAGE_KEY = "blueprint.chatIndex";
const LEGACY_PROJECT_CHAT_STORAGE_PREFIX = "blueprint.projectChat.";
const MAX_PROJECT_CHAT_MESSAGES = 80;
const MAX_CHAT_INDEX_ITEMS = 200;
const INITIAL_CHAT_TIMESTAMP = "2000-01-01T00:00:00.000Z";
const NEW_PROJECT_TITLE = "New project";

type GenerationWorkflowOption = {
  id: string;
  label: string;
  description?: string;
  uses_catalog?: boolean;
  uses_web_research?: boolean;
  uses_firecrawl_mcp?: boolean;
  uses_external_sources?: boolean;
};

type GenerationLlmOption = {
  provider: string;
  model: string;
  label: string;
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
  status?: "idle" | "loading" | "success" | "error";
  timestamp: string;
  projectId?: string | null;
  pipelineProgress?: AgentPipelineProgress | null;
};

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
const NVIDIA_QWEN_CODER_32B_MODEL = "qwen/qwen2.5-coder-32b-instruct";
const NVIDIA_LLAMA_8B_MODEL = "meta/llama-3.1-8b-instruct";

const localOnlyGenerationLlms: GenerationLlmOption[] =
  process.env.NODE_ENV === "development"
    ? [{ provider: "baseten", model: BASETEN_DEEPSEEK_MODEL, label: "Baseten DeepSeek V4 Pro" }]
    : [];

const defaultGenerationLlms: GenerationLlmOption[] = [
  { provider: "openai", model: "gpt-5.5", label: "OpenAI GPT-5.5" },
  { provider: "runpod", model: RUNPOD_PARTI_BASE_MODEL, label: "Runpod Parti Base" },
  { provider: "runpod-serverless", model: RUNPOD_PARTI_BASE_MODEL, label: RUNPOD_PARTI_BASE_MODEL },
  { provider: "baseten", model: BASETEN_GLM_MODEL, label: "GLM 5.2" },
  ...localOnlyGenerationLlms,
  { provider: "gmi", model: "anthropic/claude-fable-5", label: "GMI Claude Fable 5" },
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

function generationLlmKey(option: Pick<GenerationLlmOption, "provider" | "model">) {
  return `${option.provider}/${option.model}`;
}

function generationLlmLabel(provider: string, model: string) {
  if (provider === "runpod-serverless" && model === RUNPOD_PARTI_BASE_MODEL) return RUNPOD_PARTI_BASE_MODEL;
  if (provider === "runpod" && model === RUNPOD_PARTI_BASE_MODEL) return "Runpod Parti Base";
  if (provider === "baseten" && model === BASETEN_GLM_MODEL) return "GLM 5.2";
  if (provider === "baseten" && model === BASETEN_DEEPSEEK_MODEL) return "Baseten DeepSeek V4 Pro";
  if (provider === "gmi" && model === "anthropic/claude-fable-5") return "GMI Claude Fable 5";
  if (provider === "nvidia" && model === NVIDIA_QWEN_CODER_32B_MODEL) return "NVIDIA Qwen2.5 Coder 32B";
  if (provider === "nvidia" && model === NVIDIA_LLAMA_8B_MODEL) return "NVIDIA Llama 3.1 8B";
  if (provider === "simulation") return "Local Simulation";
  return `${provider} ${model}`.trim();
}

function projectLlmDisplayLabel(provider: string, model: string) {
  if (provider === "runpod-serverless" && model === RUNPOD_PARTI_BASE_MODEL) return RUNPOD_PARTI_BASE_MODEL;
  if (provider === "baseten" && model === BASETEN_GLM_MODEL) return "GLM 5.2";
  return `${provider}/${model}`;
}

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function isTruthyEnv(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value || "").trim().toLowerCase());
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
  return ["idle", "loading", "success", "error"].includes(value) ? value : "idle";
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

function chatThreadStorageKey(chatId: string) {
  return `${CHAT_THREAD_STORAGE_PREFIX}${chatId}`;
}

function legacyProjectChatStorageKey(projectId: string) {
  return `${LEGACY_PROJECT_CHAT_STORAGE_PREFIX}${projectId}`;
}

function readStoredChatThread(chatId: string, legacyProjectId?: string | null): ChatMessage[] {
  if (typeof window === "undefined" || !chatId) return [];
  try {
    const raw = window.localStorage.getItem(chatThreadStorageKey(chatId))
      || (legacyProjectId ? window.localStorage.getItem(legacyProjectChatStorageKey(legacyProjectId)) : null);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatMessage).filter(Boolean) as ChatMessage[] : [];
  } catch {
    return [];
  }
}

function writeStoredChatThread(chatId: string, messages: ChatMessage[]) {
  if (typeof window === "undefined" || !chatId) return;
  try {
    window.localStorage.setItem(chatThreadStorageKey(chatId), JSON.stringify(messages.slice(-MAX_PROJECT_CHAT_MESSAGES)));
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

function readStoredChatIndex(): ChatListItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CHAT_INDEX_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeChatListItem).filter(Boolean) as ChatListItem[] : [];
  } catch {
    return [];
  }
}

function writeStoredChatIndex(items: ChatListItem[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CHAT_INDEX_STORAGE_KEY, JSON.stringify(items.slice(0, MAX_CHAT_INDEX_ITEMS)));
  } catch {
    // Local chat index is best-effort.
  }
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
  return [nextItem, ...items.filter((current) => current.chatId !== item.chatId)]
    .sort((left, right) => {
      const leftTime = Date.parse(left.createdAt || "");
      const rightTime = Date.parse(right.createdAt || "");
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    })
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
    "Create a new Blueprint hardware project from this project chat message.",
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
      question: "What should Blueprint optimize in the first version?",
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

async function requestHumanContextQuestions(promptText: string, workflow: string, hasImage: boolean) {
  try {
    const res = await fetch(`${API_URL}/clarifying-questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

type ProjectGalleryItem = {
  key: string;
  title: string;
  projectId: string;
  chatId: string;
  canChat: boolean;
  creatorDisplay: string;
  creatorImageUrl: string | null;
  createdAt: string | null;
  partsCount: number;
  starCount: number;
  image: ProjectImageCandidate | null;
};

type ChatListItem = {
  chatId: string;
  title: string;
  projectId: string;
  createdAt: string | null;
  projectCount: number;
};

type ChatRouteTransition = {
  chatId: string;
  title: string;
  projectId: string;
  error?: string | null;
};

type AlphaGateConfig = {
  gateActive: boolean;
};

type VideoGenerationConfig = {
  configured: boolean | null;
  reason: string | null;
};

const PROJECT_GALLERY_PAGE_SIZES = {
  mobile: 3,
  tablet: 6,
  desktop: 8,
} as const;

const pipelineMermaidCode = `graph LR
  IMAGE["Image Input"] --> FEATURES["Feature Extraction"]
  FEATURES --> IR["Typed Hardware IR (Pydantic JSON)"]
  IR --> BOM["BOM"]
  IR --> CAD["Mechanical CAD"]`;

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

const categoryTone: Record<string, { text: string; bg: string; border: string; label: string }> = {
  microcontroller: { text: "text-cyan-400", bg: "bg-cyan-950/40", border: "border-cyan-500/40", label: "MCU" },
  sensor: { text: "text-emerald-400", bg: "bg-emerald-950/30", border: "border-emerald-500/30", label: "SENSOR" },
  actuator: { text: "text-orange-400", bg: "bg-orange-950/35", border: "border-orange-500/40", label: "ACTUATOR" },
  display: { text: "text-pink-400", bg: "bg-pink-950/35", border: "border-pink-500/40", label: "DISPLAY" },
  power: { text: "text-yellow-400", bg: "bg-yellow-950/35", border: "border-yellow-500/40", label: "POWER" },
  passives: { text: "text-violet-400", bg: "bg-violet-950/35", border: "border-violet-500/40", label: "IO" },
  mechanical: { text: "text-rose-400", bg: "bg-rose-950/30", border: "border-rose-500/35", label: "MECH" },
  "3d print": { text: "text-indigo-300", bg: "bg-indigo-950/35", border: "border-indigo-400/35", label: "3D PRINT" },
  default: { text: "text-slate-300", bg: "bg-slate-900", border: "border-slate-700", label: "PART" },
};

type SchematicPin = {
  pin_id: string;
  name?: string;
  pin_type?: string;
  voltage?: number | null;
  connected?: boolean;
  netTypes?: string[];
};

type A2AJob = {
  job_id: string;
  message_id?: string;
  correlation_id?: string | null;
  action: string;
  sender: string;
  recipient: string;
  status: string;
  server_owned?: boolean;
  created_at?: string;
  updated_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  payload?: Record<string, any>;
  result_summary?: Record<string, any> | null;
  source_usage?: Record<string, any>;
  progress_events?: AgentPipelineEvent[];
  error?: string | null;
  error_debug?: Record<string, any> | null;
};

type BackendLogs = {
  enabled?: boolean;
  configured?: boolean;
  path?: string | null;
  size_bytes?: number;
  line_count?: number;
  truncated?: boolean;
  lines?: string[];
  message?: string;
  updated_at?: string;
};

type VideoGenerationMode = "image-to-video" | "video-to-video";

type VideoModelOption = {
  id: string;
  label: string;
  mode: VideoGenerationMode;
};

const defaultVideoAspectRatios = ["16:9", "9:16", "1:1", "4:3", "3:4"];

type StoredVideoInfo = {
  bucket?: string;
  key?: string;
  s3Uri?: string;
  publicUrl?: string | null;
  signedUrl?: string | null;
  url?: string | null;
  contentType?: string;
  sizeBytes?: number;
  metadata?: Record<string, any>;
};

type VideoPollContext = {
  model?: string;
  mode?: VideoGenerationMode;
  prompt?: string;
  sourceUrl?: string;
  aspectRatio?: string;
};

function normalizeVideoGenerationMode(value: any): VideoGenerationMode {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (["video-to-video", "video_to_video", "video2video", "v2v", "video"].includes(normalized)) return "video-to-video";
  return "image-to-video";
}

function videoIdentity(video: StoredVideoInfo | null | undefined, fallback = ""): string {
  return video?.key || video?.s3Uri || video?.url || video?.publicUrl || video?.signedUrl || fallback;
}

function videoSourceUrl(video: StoredVideoInfo | null | undefined): string {
  return video?.url || video?.publicUrl || video?.signedUrl || "";
}

function videoMetadataString(video: StoredVideoInfo | null | undefined, keys: string[]): string {
  const metadata = video?.metadata || {};
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  const lowered = new Map(
    Object.entries(metadata).map(([key, value]) => [key.toLowerCase(), value])
  );
  for (const key of keys) {
    const value = lowered.get(key.toLowerCase());
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function videoPromptText(video: StoredVideoInfo | null | undefined): string {
  return videoMetadataString(video, ["prompt", "videoPrompt", "video_prompt", "promptPreview", "prompt_preview"]);
}

function fitVideoPromptForProvider(prompt: string, suffix = "") {
  const cleanPrompt = String(prompt || "").trim();
  const cleanSuffix = String(suffix || "");
  if (!cleanSuffix) return cleanPrompt.length > VIDEO_PROMPT_MAX_CHARS ? cleanPrompt.slice(0, VIDEO_PROMPT_MAX_CHARS).trimEnd() : cleanPrompt;
  if (cleanSuffix.length >= VIDEO_PROMPT_MAX_CHARS) return cleanSuffix.slice(0, VIDEO_PROMPT_MAX_CHARS).trimEnd();
  const availablePromptChars = VIDEO_PROMPT_MAX_CHARS - cleanSuffix.length;
  const fittedPrompt = cleanPrompt.length > availablePromptChars ? cleanPrompt.slice(0, availablePromptChars).trimEnd() : cleanPrompt;
  return `${fittedPrompt}${cleanSuffix}`;
}

function videoPromptWasTrimmed(original: string, fitted: string) {
  return String(original || "").trim().length > fitted.length;
}

function videoLabel(video: StoredVideoInfo | null | undefined, fallback = "video"): string {
  return videoMetadataString(video, ["requestId", "request_id"]) || video?.key?.split("/").pop() || fallback;
}

type SchematicNodeData = {
  component: any;
  leftPins: SchematicPin[];
  rightPins: SchematicPin[];
  tone: {
    label: string;
    border: string;
    text: string;
    soft: string;
  };
  roleLabel: string;
  connectionSide: "left" | "right" | "both";
  isController: boolean;
};

type PlacementPoint = {
  x: number;
  y: number;
};

type ProjectImageCandidate = {
  src: string;
  label: string;
  viewId?: string;
  prompt?: string;
  dimensions?: string;
};

function validRemoteImageUrl(value: any): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return trimmed;
  } catch {
    return null;
  }
}

function safeImageContentType(value: any) {
  return typeof value === "string" && /^image\/[a-z0-9.+-]+$/i.test(value.trim()) ? value.trim() : "image/png";
}

function normalImageSrc(value: any, contentType?: any): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("data:image/") || validRemoteImageUrl(trimmed)) return trimmed;
  const compact = trimmed.replace(/\s+/g, "");
  if (/^[A-Za-z0-9+/]+={0,2}$/.test(compact) && compact.length > 20) {
    return `data:${safeImageContentType(contentType)};base64,${compact}`;
  }
  return trimmed;
}

function previewableImageSrc(value: any): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("data:image/") || validRemoteImageUrl(trimmed)) return normalImageSrc(trimmed);
  const compact = trimmed.replace(/\s+/g, "");
  if (/^[A-Za-z0-9+/]+={0,2}$/.test(compact) && compact.length > 20) return normalImageSrc(trimmed);
  return null;
}

function resolveProjectImageCandidates(metadata: Record<string, any> = {}): ProjectImageCandidate[] {
  const generatedLabel = `Generated by ${metadata.product_image_model || metadata.image_output_model || "image model"}`;
  const sequence = Array.isArray(metadata.product_visual_sequence) ? metadata.product_visual_sequence : [];
  const sequenceCandidates = sequence
    .filter((item: any) => {
      if (!item || typeof item !== "object") return false;
      const viewId = typeof item.view_id === "string" ? item.view_id.trim().toLowerCase() : "";
      const labelKey = typeof item.label === "string" ? item.label.trim().toLowerCase().replace(/\s+/g, "-") : "";
      return viewId !== "diagram" && labelKey !== "subsystem-physical-layout";
    })
    .map((item: any): ProjectImageCandidate | null => {
      if (!item || typeof item !== "object") return null;
      const src =
        normalImageSrc(item.url, item.content_type) ||
        normalImageSrc(item.data, item.content_type) ||
        normalImageSrc(metadata[`product_${item.view_id}_image_url`], metadata[`product_${item.view_id}_image_content_type`]) ||
        normalImageSrc(metadata[`product_${item.view_id}_image_data`], metadata[`product_${item.view_id}_image_content_type`]);
      if (!src) return null;
      return {
        src,
        label: typeof item.label === "string" && item.label.trim() ? item.label : generatedLabel,
        viewId: typeof item.view_id === "string" ? item.view_id : undefined,
        prompt: typeof item.prompt === "string" ? item.prompt : undefined,
      };
    })
    .filter((candidate: ProjectImageCandidate | null): candidate is ProjectImageCandidate => Boolean(candidate));

  const stagedCandidates: Array<ProjectImageCandidate | null> = [
    normalImageSrc(metadata.product_case_image_url, metadata.product_case_image_content_type) ||
    normalImageSrc(metadata.product_case_image_data, metadata.product_case_image_content_type)
      ? {
          src:
            normalImageSrc(metadata.product_case_image_url, metadata.product_case_image_content_type) ||
            normalImageSrc(metadata.product_case_image_data, metadata.product_case_image_content_type) ||
            "",
          label: "Case exterior",
          viewId: "case",
        }
      : null,
    normalImageSrc(metadata.product_inside_image_url, metadata.product_inside_image_content_type) ||
    normalImageSrc(metadata.product_inside_image_data, metadata.product_inside_image_content_type)
      ? {
          src:
            normalImageSrc(metadata.product_inside_image_url, metadata.product_inside_image_content_type) ||
            normalImageSrc(metadata.product_inside_image_data, metadata.product_inside_image_content_type) ||
            "",
          label: "Transparent top-down assembly",
          viewId: "inside",
        }
      : null,
  ];

  const productUrl = validRemoteImageUrl(metadata.product_image_url);
  const productData = normalImageSrc(metadata.product_image_data, metadata.product_image_content_type);
  const referenceUrl = validRemoteImageUrl(metadata.reference_image_url);
  const referenceData = normalImageSrc(metadata.reference_image_data, metadata.reference_image_content_type);
  const hasGeneratedViews = sequenceCandidates.length > 0 || stagedCandidates.some(Boolean);
  const candidates: Array<ProjectImageCandidate | null> = [
    ...sequenceCandidates,
    ...stagedCandidates,
    !hasGeneratedViews && productUrl ? { src: productUrl, label: generatedLabel } : null,
    !hasGeneratedViews && productData ? { src: productData, label: generatedLabel } : null,
    referenceUrl ? { src: referenceUrl, label: "Uploaded hardware reference" } : null,
    referenceData ? { src: referenceData, label: "Uploaded hardware reference" } : null,
  ];

  const unique = new Map<string, ProjectImageCandidate>();
  candidates
    .filter((candidate): candidate is ProjectImageCandidate => Boolean(candidate && candidate.src))
    .forEach((candidate) => {
      if (!unique.has(candidate.src)) unique.set(candidate.src, candidate);
    });
  return Array.from(unique.values());
}

function mergeStoredVideoGallery(current: StoredVideoInfo[], incoming: StoredVideoInfo[]) {
  const byKey = new Map<string, StoredVideoInfo>();
  [...incoming, ...current].forEach((video, index) => {
    const key = video.key || video.s3Uri || video.url || video.publicUrl || video.signedUrl || `video-${index}`;
    byKey.set(key, video);
  });
  return Array.from(byKey.values());
}

const schematicTones: Record<string, { label: string; border: string; text: string; soft: string }> = {
  microcontroller: { label: "MCU", border: "#22d3ee", text: "#a5f3fc", soft: "#082f49" },
  sensor: { label: "SENSOR", border: "#60a5fa", text: "#bfdbfe", soft: "#10233f" },
  actuator: { label: "ACTUATOR", border: "#fb923c", text: "#fed7aa", soft: "#3a1b0c" },
  power: { label: "POWER", border: "#facc15", text: "#fef08a", soft: "#352a08" },
  passives: { label: "MODULE", border: "#a78bfa", text: "#ddd6fe", soft: "#24163f" },
  communication: { label: "MODULE", border: "#a78bfa", text: "#ddd6fe", soft: "#24163f" },
  display: { label: "DISPLAY", border: "#f472b6", text: "#fbcfe8", soft: "#3a1230" },
  default: { label: "PART", border: "#94a3b8", text: "#cbd5e1", soft: "#1e293b" },
};

const schematicNodeTypes = {
  schematicPart: SchematicPartNode,
};

function SchematicPartNode({ data }: NodeProps<SchematicNodeData>) {
  const { component, leftPins, rightPins, tone, roleLabel, connectionSide, isController } = data;
  const Icon = iconForCategory(component.category);
  const visibleLeftPins = leftPins.length ? leftPins : [];
  const visibleRightPins = rightPins.length ? rightPins : [];
  const modulePins = connectionSide === "left" ? visibleRightPins : visibleLeftPins;
  const modulePinSide = connectionSide === "left" ? "right" : "left";
  const visiblePinCount = visibleLeftPins.length + visibleRightPins.length;
  const partNumber = component.part_number || component.ref_des;
  const subtitle = component.category || component.part_type || roleLabel || tone.label;

  return (
    <div
      className={`schematic-node schematic-card ${isController ? "schematic-controller-card" : ""}`}
      style={{ ["--schematic-accent" as string]: tone.border, ["--schematic-soft" as string]: tone.soft, ["--schematic-text" as string]: tone.text }}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center border border-[var(--schematic-accent)] bg-[var(--schematic-soft)] text-[var(--schematic-text)]">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="text-[9px] font-black uppercase leading-none tracking-[0.16em] text-[var(--schematic-text)]">{roleLabel || tone.label}</div>
            <div className="h-px flex-1" style={{ backgroundColor: tone.border, opacity: 0.35 }} />
          </div>
          <div className="mt-1 truncate text-[13px] font-black leading-tight text-white">{component.name || component.ref_des}</div>
          <div className="mt-1 flex items-center gap-2 text-[8px] font-bold uppercase tracking-[0.08em] text-slate-500">
            <span className="truncate">{partNumber}</span>
            <span className="h-1 w-1 shrink-0 bg-slate-700" />
            <span className="shrink-0">{component.ref_des}</span>
          </div>
        </div>
      </div>

      {!isController && (
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#2b3038] pt-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
          <span className="truncate">{subtitle}</span>
          <span className="shrink-0 text-[var(--schematic-text)]">{visiblePinCount || 0} pins</span>
        </div>
      )}

      <div className={isController ? "mt-3 grid grid-cols-[1fr_72px_1fr] gap-2" : "mt-3"}>
        {isController && <PinColumn componentRef={component.ref_des} pins={visibleLeftPins} side="left" tone={tone} />}
        {isController && (
          <div className="flex min-h-[156px] flex-col items-center justify-center border border-[#334155] bg-[#0f1720] px-2 text-center">
            <Cpu className="mb-2 h-7 w-7 text-cyan-200" />
            <div className="text-[8px] font-black uppercase tracking-[0.12em] text-white">{component.ref_des}</div>
            <div className="mt-1 text-[7px] font-bold leading-tight text-slate-500">Controller</div>
          </div>
        )}
        {isController ? (
          <PinColumn componentRef={component.ref_des} pins={visibleRightPins} side="right" tone={tone} />
        ) : (
          <PinColumn componentRef={component.ref_des} pins={modulePins} side={modulePinSide} tone={tone} emptyLabel="No linked pins" />
        )}
      </div>
    </div>
  );
}

function PinColumn({
  componentRef,
  pins,
  side,
  tone,
  emptyLabel,
}: {
  componentRef: string;
  pins: SchematicPin[];
  side: "left" | "right";
  tone: SchematicNodeData["tone"];
  emptyLabel?: string;
}) {
  if (!pins.length) {
    return (
      <div className="border border-dashed border-[#333844] bg-[#101116] px-3 py-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-600">
        {emptyLabel || "No pins"}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {pins.map((pin) => {
        const handlePosition = side === "left" ? Position.Left : Position.Right;
        const handleStyle = side === "left" ? { left: -8, top: "50%" } : { right: -8, top: "50%" };
        return (
          <div
            key={`${side}-${pin.pin_id}`}
            className={`schematic-pin-row ${side === "left" ? "pl-2 text-left" : "pr-2 text-right"} ${pin.connected ? "schematic-pin-connected" : ""}`}
            title={`${pin.pin_id}${pin.name ? ` - ${pin.name}` : ""}${pin.voltage !== undefined && pin.voltage !== null ? ` / ${pin.voltage}V` : ""}`}
          >
            <Handle
              type="target"
              id={schematicHandleId(componentRef, pin.pin_id)}
              position={handlePosition}
              className="schematic-pin-handle"
              style={{ ...handleStyle, ["--handle-border" as string]: tone.border, ["--handle-color" as string]: pin.connected ? tone.border : "#111216" }}
            />
            <Handle
              type="source"
              id={schematicHandleId(componentRef, pin.pin_id)}
              position={handlePosition}
              className="schematic-pin-handle"
              style={{ ...handleStyle, ["--handle-border" as string]: tone.border, ["--handle-color" as string]: pin.connected ? tone.border : "#111216" }}
            />
            <span className="block truncate text-[8px] font-black uppercase leading-none text-white">{pin.pin_id}</span>
            {pin.name && <span className="mt-0.5 block truncate text-[6px] font-bold uppercase leading-none text-slate-500">{pin.name}</span>}
          </div>
        );
      })}
    </div>
  );
}

function schematicToneForCategory(category = "") {
  return schematicTones[category.toLowerCase()] || schematicTones.default;
}

function pinKey(pin: SchematicPin) {
  return pin.pin_id;
}

function schematicHandleId(refDes: string, pinId: string) {
  return `${refDes}.${pinId}`;
}

function normalizeSchematicCategory(category = "") {
  const normalized = category.toLowerCase();
  if (normalized.includes("micro") || normalized.includes("controller") || normalized === "mcu") return "microcontroller";
  if (normalized.includes("sensor")) return "sensor";
  if (normalized.includes("display") || normalized.includes("screen") || normalized.includes("oled")) return "display";
  if (normalized.includes("actuator") || normalized.includes("motor") || normalized.includes("servo") || normalized.includes("relay")) return "actuator";
  if (normalized.includes("power") || normalized.includes("battery") || normalized.includes("regulator")) return "power";
  if (normalized.includes("comm") || normalized.includes("radio") || normalized.includes("wifi") || normalized.includes("ble")) return "communication";
  if (normalized.includes("passive") || normalized.includes("module") || normalized.includes("io")) return "passives";
  return normalized || "default";
}

function isControllerComponent(component: any) {
  const category = normalizeSchematicCategory(component?.category || "");
  const text = `${component?.name || ""} ${component?.part_number || ""} ${component?.ref_des || ""}`.toLowerCase();
  return (
    category === "microcontroller" ||
    /^u1$/i.test(component?.ref_des || "") ||
    /\b(esp32|arduino|pico|stm32|devkit|teensy|mcu|microcontroller)\b/.test(text)
  );
}

function schematicRoleLabel(component: any) {
  const category = normalizeSchematicCategory(component?.category || "");
  if (isControllerComponent(component)) return "ESP32 DevKit v1";
  if (category === "display") return "Display";
  if (category === "sensor") return "Sensor module";
  if (category === "actuator") return "Actuator / driver";
  if (category === "power") return "Power module";
  if (category === "communication") return "Comms";
  if (category === "passives") return "Module";
  return "Peripheral";
}

function primaryControllerLabel(ir: any) {
  const parts = Array.isArray(ir?.components) ? ir.components : [];
  const controller = parts.find((component: any) => isControllerComponent(component));
  return controller?.part_number || controller?.name || controller?.ref_des || "Controller";
}

function pinSortScore(pin: SchematicPin) {
  const id = pin.pin_id.toLowerCase();
  const type = pin.pin_type?.toLowerCase() || "";
  if (/(vcc|vin|vbat|3v3|5v|12v|\+|pos)/.test(id) || type === "power") return `00-${id}`;
  if (/(gnd|ground|-|neg)/.test(id) || type === "ground") return `01-${id}`;
  if (/(sda|scl|i2c)/.test(id) || type === "i2c") return `02-${id}`;
  if (/(tx|rx|uart)/.test(id)) return `03-${id}`;
  if (/(sck|miso|mosi|cs|spi)/.test(id) || type === "spi") return `04-${id}`;
  if (/(pwm|sig|in|out|gpio|d\\d+|a\\d+)/.test(id)) return `05-${id}`;
  return `09-${id}`;
}

function sortSchematicPins(pins: SchematicPin[]) {
  return [...pins].sort((a, b) =>
    pinSortScore(a).localeCompare(pinSortScore(b), undefined, { numeric: true }) ||
    pinKey(a).localeCompare(pinKey(b), undefined, { numeric: true })
  );
}

function splitControllerPins(pins: SchematicPin[]) {
  const sorted = sortSchematicPins(pins);
  const connected = sorted.filter((pin) => pin.connected);
  const rest = sorted.filter((pin) => !pin.connected);
  const ordered = [...connected, ...rest].slice(0, 28);
  const leftPins: SchematicPin[] = [];
  const rightPins: SchematicPin[] = [];
  ordered.forEach((pin, index) => {
    const id = pin.pin_id.toLowerCase();
    if (/(vcc|vin|3v3|5v|gnd|en|rst|reset|gpio0|d0|a0|sda|scl)/.test(id)) {
      leftPins.push(pin);
    } else if (/(tx|rx|mosi|miso|sck|cs|pwm|gpio|d\\d+)/.test(id)) {
      rightPins.push(pin);
    } else if (leftPins.length <= rightPins.length) {
      leftPins.push(pin);
    } else {
      rightPins.push(pin);
    }
    if (Math.abs(leftPins.length - rightPins.length) > 4 && index > 6) {
      const source = leftPins.length > rightPins.length ? leftPins : rightPins;
      const target = leftPins.length > rightPins.length ? rightPins : leftPins;
      const moved = source.pop();
      if (moved) target.push(moved);
    }
  });
  return { leftPins, rightPins };
}

function schematicSideForComponent(component: any, index: number, counts: { left: number; right: number }) {
  const category = normalizeSchematicCategory(component?.category || "");
  if (["display", "sensor", "power"].includes(category)) return "left";
  if (["actuator", "communication", "passives"].includes(category)) return "right";
  return counts.left <= counts.right ? "left" : "right";
}

function schematicGridPosition(side: "left" | "right", index: number, rowsPerColumn: number): PlacementPoint {
  const row = index % rowsPerColumn;
  const column = Math.floor(index / rowsPerColumn);
  const rowGap = 126;
  const columnGap = 266;
  const top = 96;
  const innerLeftX = 320;
  const innerRightX = 910;
  return {
    x: side === "left" ? innerLeftX - column * columnGap : innerRightX + column * columnGap,
    y: top + row * rowGap,
  };
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

function normalizePlacement(value: any): PlacementPoint | null {
  if (!value || typeof value.x !== "number" || typeof value.y !== "number") return null;
  return { x: value.x, y: value.y };
}

type HomeProps = {
  routeProjectId?: string | null;
  routeChatId?: string | null;
  showDeveloperTools?: boolean;
  homeView?: "chat" | "projects" | "my-projects" | "jobs" | "logs";
  authRequired?: boolean;
};

export function BlueprintWorkspace({
  routeProjectId = null,
  routeChatId = null,
  showDeveloperTools = DEFAULT_SHOW_DEVELOPER_TOOLS,
  homeView = "chat",
  authRequired = false,
}: HomeProps = {}) {
  const router = useRouter();
  const { getToken, isLoaded: authLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const { openSignIn } = useClerk();
  const [prompt, setPrompt] = useState("");
  const [activeChatId, setActiveChatId] = useState(() => routeChatId ? safeDecodeChatId(routeChatId) : newBuildChatId());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => initialChatMessages());
  const [pendingHumanContext, setPendingHumanContext] = useState<PendingHumanContext | null>(null);
  const [chatThreads, setChatThreads] = useState<Record<string, ChatMessage[]>>({});
  const [projectChatInput, setProjectChatInput] = useState("");
  const [projectChatVisible, setProjectChatVisible] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const [projectIR, setProjectIR] = useState<any>(null);
  const [mermaidCode, setMermaidCode] = useState<string>("");
  const [svgSchematic, setSvgSchematic] = useState<string>("");
  const [projectHistory, setProjectHistory] = useState<any[]>([]);
  const [myProjectHistory, setMyProjectHistory] = useState<any[]>([]);
  const [projectHistoryLoaded, setProjectHistoryLoaded] = useState(false);
  const [myProjectHistoryLoaded, setMyProjectHistoryLoaded] = useState(false);
  const [localChatItems, setLocalChatItems] = useState<ChatListItem[]>([]);
  const [privateChatItems, setPrivateChatItems] = useState<ChatListItem[]>([]);
  const [chatIndexLoaded, setChatIndexLoaded] = useState(false);
  const [sessionChatItems, setSessionChatItems] = useState<ChatListItem[]>([]);
  const [a2aJobs, setA2aJobs] = useState<A2AJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobStatusFilter, setJobStatusFilter] = useState("all");
  const [jobsLastUpdatedAt, setJobsLastUpdatedAt] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminSessionLoaded, setAdminSessionLoaded] = useState(false);
  const [backendLogs, setBackendLogs] = useState<BackendLogs | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logsLastUpdatedAt, setLogsLastUpdatedAt] = useState<string | null>(null);
  const [videoModels, setVideoModels] = useState<VideoModelOption[]>([]);
  const [videoModelsLoading, setVideoModelsLoading] = useState(false);
  const [videoModelsError, setVideoModelsError] = useState<string | null>(null);
  const [selectedVideoModel, setSelectedVideoModel] = useState("");
  const [videoImageInput, setVideoImageInput] = useState("");
  const [selectedVideoImageSources, setSelectedVideoImageSources] = useState<string[]>([]);
  const [videoImageTouched, setVideoImageTouched] = useState(false);
  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoPromptGenerating, setVideoPromptGenerating] = useState(false);
  const [videoPromptMessage, setVideoPromptMessage] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState("5");
  const [videoAspectRatio, setVideoAspectRatio] = useState("16:9");
  const [videoAspectRatios, setVideoAspectRatios] = useState(defaultVideoAspectRatios);
  const [videoRequestId, setVideoRequestId] = useState<string | null>(null);
  const [videoStatus, setVideoStatus] = useState("idle");
  const [videoStatusMessage, setVideoStatusMessage] = useState<string | null>(null);
  const [videoMode, setVideoMode] = useState<VideoGenerationMode>("image-to-video");
  const [videoSourceVideoUrl, setVideoSourceVideoUrl] = useState("");
  const [storedVideo, setStoredVideo] = useState<StoredVideoInfo | null>(null);
  const [videoGallery, setVideoGallery] = useState<StoredVideoInfo[]>([]);
  const [videoGalleryLoading, setVideoGalleryLoading] = useState(false);
  const [videoGalleryError, setVideoGalleryError] = useState<string | null>(null);
  const [selectedVideoReviewKey, setSelectedVideoReviewKey] = useState<string | null>(null);
  const [videoReviewMakeNewVideo, setVideoReviewMakeNewVideo] = useState(false);
  const [projectGalleryImages, setProjectGalleryImages] = useState<Record<string, ProjectImageCandidate | null>>({});
  const [routeProjectError, setRouteProjectError] = useState<string | null>(null);
  const [chatRouteTransition, setChatRouteTransition] = useState<ChatRouteTransition | null>(null);
  const [catalogComponents, setCatalogComponents] = useState<any[]>([]);
  const [serverStatus, setServerStatus] = useState<"connected" | "disconnected">("disconnected");
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [generationInputNotice, setGenerationInputNotice] = useState<string | null>(null);
  const [alphaGateConfig, setAlphaGateConfig] = useState<AlphaGateConfig>({
    gateActive: false,
  });
  const [videoGenerationConfig, setVideoGenerationConfig] = useState<VideoGenerationConfig>({
    configured: null,
    reason: null,
  });
  const [videoSelfCorrectionConfig, setVideoSelfCorrectionConfig] = useState<VideoGenerationConfig>({
    configured: null,
    reason: null,
  });
  const [videoReviewStatus, setVideoReviewStatus] = useState("idle");
  const [videoReviewMessage, setVideoReviewMessage] = useState<string | null>(null);
  const [alphaSignupForm, setAlphaSignupForm] = useState({
    name: "",
    email: "",
    organization: "",
    additionalInfo: "",
  });
  const [alphaSignupStatus, setAlphaSignupStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [alphaSignupMessage, setAlphaSignupMessage] = useState<string | null>(null);
  const [generateProductImage, setGenerateProductImage] = useState(false);
  const [generationWorkflow, setGenerationWorkflow] = useState(DEFAULT_WORKFLOW_ID);
  const [generationWorkflows, setGenerationWorkflows] = useState<GenerationWorkflowOption[]>(defaultGenerationWorkflows);
  const [agentPipelineSteps, setAgentPipelineSteps] = useState<AgentPipelineStep[]>(defaultAgentPipelineSteps);
  const [generationLlms, setGenerationLlms] = useState<GenerationLlmOption[]>(defaultGenerationLlms);
  const [generationLlmKeyValue, setGenerationLlmKeyValue] = useState(generationLlmKey(defaultGenerationLlms[0]));
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
  const fileInputRefVideo = useRef<HTMLInputElement>(null);
  const projectsSectionRef = useRef<HTMLElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const projectChatEndRef = useRef<HTMLDivElement>(null);
  const chatPersistenceTimersRef = useRef<Record<string, number>>({});
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const projectGalleryItems = useMemo(
    () => buildProjectGalleryItems(projectHistory, projectGalleryImages).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, isSignedIn, projectHistory, projectGalleryImages]
  );
  const myProjectGalleryItems = useMemo(
    () => buildProjectGalleryItems(myProjectHistory, projectGalleryImages).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, isSignedIn, myProjectHistory, projectGalleryImages]
  );
  const visibleChatSourceProjects = authRequired ? myProjectHistory : projectHistory;
  const visibleChatSourceItems = useMemo(
    () => authRequired ? mergeChatListItems(sessionChatItems, privateChatItems) : localChatItems,
    [authRequired, localChatItems, privateChatItems, sessionChatItems]
  );
  const chatListItems = useMemo(
    () => buildChatListItems(visibleChatSourceProjects, visibleChatSourceItems),
    [visibleChatSourceProjects, visibleChatSourceItems]
  );
  const chatHistoryLoaded = authRequired ? myProjectHistoryLoaded : projectHistoryLoaded;
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
  const visibleGenerationInputNotice =
    generationInputNotice || ((prompt.trim() || pendingHumanContext) && !generationInputValidation.isValid ? generationInputValidation.message : null);
  const hasGenerationInput = Boolean(prompt.trim() || selectedImage || pendingHumanContext);
  const alphaGateActive = alphaGateConfig.gateActive;
  const canViewJobs = isAdmin;
  const canViewAdminTools = showDeveloperTools || isAdmin;
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
    () => generationLlms.find((option) => generationLlmKey(option) === generationLlmKeyValue) || generationLlms[0] || defaultGenerationLlms[0],
    [generationLlmKeyValue, generationLlms]
  );
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
      const storedMessages = readStoredChatThread(chatId, projectId);
      const nextMessages = storedMessages.length
        ? storedMessages
        : initialProjectChatMessages(projectId, ir?.overview?.title || "Project", sourcePrompt);
      writeStoredChatThread(chatId, nextMessages);
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
      writeStoredChatThread(chatId, nextMessages);
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
      writeStoredChatThread(chatId, nextMessages);
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
      writeStoredChatThread(chatId, nextMessages);
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
      writeStoredChatIndex(nextItems);
      return nextItems;
    });
    if (authRequired && normalizedItem) {
      const messages = chatThreads[item.chatId]
        || (activeChatId === item.chatId ? chatMessages : readStoredChatThread(item.chatId));
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
    setProjectHistory(mergeProject);
    if (authRequired) {
      setMyProjectHistory(mergeProject);
      setMyProjectHistoryLoaded(true);
    }
    setProjectHistoryLoaded(true);
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
      writeStoredChatIndex(nextItems);
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

  const fetchAdminSession = useCallback(async () => {
    if (!authLoaded) return;
    if (!isSignedIn) {
      setIsAdmin(false);
      setAdminSessionLoaded(true);
      return;
    }
    try {
      const res = await fetch(`${API_URL}/admin/session`, {
        headers: await optionalAuthHeaders(),
      });
      if (!res.ok) throw new Error(await readApiErrorMessage(res));
      const payload = await res.json();
      setIsAdmin(Boolean(payload?.is_admin));
    } catch (error) {
      console.error("Error fetching admin session", error);
      setIsAdmin(false);
    } finally {
      setAdminSessionLoaded(true);
    }
  }, [authLoaded, isSignedIn, optionalAuthHeaders]);

  useEffect(() => {
    setAdminSessionLoaded(false);
    void fetchAdminSession();
  }, [fetchAdminSession]);

  const persistChatThread = (chatId: string | null, messages: ChatMessage[], explicitTitle?: string | null) => {
    if (!authRequired || !isSignedIn || !chatId || typeof window === "undefined") return;
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
    setMermaidCode("");
    setSvgSchematic("");
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
    setMermaidCode("");
    setSvgSchematic("");
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
    const storedMessages = readStoredChatThread(item.chatId);
    if (storedMessages.length) {
      setChatThreads((current) => ({ ...current, [item.chatId]: storedMessages }));
      setChatMessages(storedMessages);
    }
    setChatRouteTransition(
      item.projectId
        ? { chatId: item.chatId, title: item.title || "Opening chat", projectId: item.projectId, error: null }
        : null
    );
    rememberChatItem(item);
    router.push(chatRoute(item.chatId));
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

  useEffect(() => {
    checkServerStatus();
    fetchRuntimeConfig();
    fetchGenerationWorkflows();
    fetchVideoModels();
    fetchCatalog();
    fetchProjectHistory();
    setLocalChatItems(readStoredChatIndex());
    setChatIndexLoaded(true);
    setChatMessages((current) => (
      current.length === 1 && current[0]?.id === "assistant-welcome"
        ? [{ ...current[0], timestamp: chatTimestamp() }]
        : current
    ));
	  }, []);

  useEffect(() => {
    if (!authRequired) return;
    setMyProjectHistoryLoaded(false);
    void fetchMyProjectHistory();
    void fetchPrivateChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequired, isSignedIn]);

  useEffect(() => {
    fetchAgentPipelineSteps(generationWorkflow);
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
      setServerStatus(res.ok ? "connected" : "disconnected");
    } catch {
      setServerStatus("disconnected");
    }
  };

  const fetchRuntimeConfig = async () => {
    try {
      const res = await fetch(`${API_URL}/debug/config`);
      if (!res.ok) return;

      const config = await res.json();
      const deployment = config.deployment || {};
      setAlphaGateConfig({
        gateActive: Boolean(deployment.alpha_generation_gate_active),
      });
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
      if (Array.isArray(config.workflows) && config.workflows.length > 0) {
        setGenerationWorkflows(config.workflows);
      }
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
      }
    } catch (e) {
      console.error("Error fetching runtime config", e);
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
    try {
      const params = new URLSearchParams({ workflow: workflowId || "default", include_image: "true" });
      const res = await fetch(`${API_URL}/pipeline/steps?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setAgentPipelineSteps(normalizeAgentPipelineSteps(data));
    } catch (e) {
      console.error("Error fetching agent pipeline steps", e);
    }
  };

  const fetchVideoModels = async () => {
    setVideoModelsLoading(true);
    setVideoModelsError(null);
    try {
      const res = await fetch(`${API_URL}/video/models`);
      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      const modelOptions: VideoModelOption[] = (Array.isArray(data.models) ? data.models : [])
        .map((item: any) => {
          if (typeof item === "string") return { id: item, label: item, mode: "image-to-video" as VideoGenerationMode };
          const id = typeof item?.id === "string" ? item.id : typeof item?.model === "string" ? item.model : "";
          const mode = normalizeVideoGenerationMode(item?.mode || item?.type || item?.inputType || item?.input_type);
          return id ? { id, label: typeof item?.label === "string" ? item.label : id, mode } : null;
        })
        .filter((item: VideoModelOption | null): item is VideoModelOption => Boolean(item));

      setVideoModels(modelOptions);
      const rawAspectRatios = data.aspectRatioOptions || data.aspect_ratio_options;
      const aspectRatios = (Array.isArray(rawAspectRatios) ? rawAspectRatios : [])
        .map((item: any) => (typeof item === "string" ? item.trim() : typeof item?.id === "string" ? item.id.trim() : ""))
        .filter(Boolean);
      const nextAspectRatios = aspectRatios.length ? aspectRatios : defaultVideoAspectRatios;
      setVideoAspectRatios(nextAspectRatios);
      setVideoAspectRatio((current) => (nextAspectRatios.includes(current) ? current : nextAspectRatios[0] || "16:9"));
      if ("generationConfigured" in data || "generation_configured" in data) {
        setVideoGenerationConfig({
          configured: Boolean(data.generationConfigured ?? data.generation_configured),
          reason: typeof data.reason === "string" ? data.reason : null,
        });
      }
      setSelectedVideoModel((current) => {
        if (current && modelOptions.some((item) => item.id === current)) return current;
        const defaultModel = data.defaultModel || data.default_model;
        if (typeof defaultModel === "string" && modelOptions.some((item) => item.id === defaultModel && item.mode === "image-to-video")) {
          return defaultModel;
        }
        return modelOptions.find((item) => item.mode === "image-to-video")?.id || modelOptions[0]?.id || "";
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Video models are unavailable.";
      setVideoModelsError(message);
    } finally {
      setVideoModelsLoading(false);
    }
  };

  const fetchProjectVideos = useCallback(async (projectId: string, options: { silent?: boolean } = {}) => {
    if (!projectId) return;
    if (!options.silent) setVideoGalleryLoading(true);
    setVideoGalleryError(null);
    try {
      const res = await fetch(`${API_URL}/video/projects/${encodeURIComponent(projectId)}`, {
        headers: await generationRequestHeaders(),
      });
      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      const videos = Array.isArray(data?.videos) ? data.videos : [];
      setVideoGallery(videos);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Video gallery is unavailable.";
      setVideoGalleryError(message);
    } finally {
      if (!options.silent) setVideoGalleryLoading(false);
    }
  }, [generationRequestHeaders]);

  const fetchCatalog = async () => {
    try {
      const res = await fetch(`${API_URL}/components`);
      if (res.ok) setCatalogComponents(await res.json());
    } catch (e) {
      console.error("Error fetching catalog", e);
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
            writeStoredChatIndex(repairedItems);
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
    if (!authRequired || !isSignedIn) {
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
    if (!authRequired || !isSignedIn) {
      setPrivateChatItems([]);
      setSessionChatItems([]);
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
            writeStoredChatThread(chatId, messages);
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
    }
  };

  const refreshProjectAndChatLists = () => {
    fetchProjectHistory();
    if (authRequired && isSignedIn) {
      void fetchMyProjectHistory();
      void fetchPrivateChats();
    }
  };

  const fetchA2aJobs = useCallback(async (status: string, options: { silent?: boolean } = {}) => {
    if (!canViewJobs) {
      setA2aJobs([]);
      setJobsLastUpdatedAt(null);
      setJobsError(null);
      return;
    }
    if (!options.silent) setJobsLoading(true);
    setJobsError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (status !== "all") params.set("status", status);
      const jobs: A2AJob[] = [];
      const errors: string[] = [];

      try {
        const res = await fetch(`${API_URL}/a2a/jobs?${params.toString()}`, {
          headers: await generationRequestHeaders(),
        });
        if (!res.ok) throw new Error(`A2A jobs endpoint returned ${res.status}`);
        const payload = await res.json();
        if (Array.isArray(payload)) jobs.push(...payload);
      } catch (error) {
        console.error("Error fetching A2A jobs", error);
        errors.push("A2A jobs");
      }

      try {
        const res = await fetch(`${API_URL}/example-project-object-jobs?${params.toString()}`, {
          headers: await generationRequestHeaders(),
        });
        if (!res.ok) throw new Error(`Example jobs endpoint returned ${res.status}`);
        const payload = await res.json();
        if (Array.isArray(payload)) jobs.push(...payload);
      } catch (error) {
        console.error("Error fetching example project object jobs", error);
        errors.push("example jobs");
      }

      jobs.sort((left, right) => {
        const leftTime = new Date(left.created_at || left.updated_at || 0).getTime();
        const rightTime = new Date(right.created_at || right.updated_at || 0).getTime();
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
      });

      setA2aJobs(jobs);
      setJobsLastUpdatedAt(new Date().toISOString());
      if (errors.length && !jobs.length) {
        setJobsError("Jobs are unavailable");
      } else if (errors.length) {
        setJobsError(`${errors.join(" and ")} unavailable`);
      }
    } catch (e) {
      console.error("Error fetching jobs", e);
      setJobsError("Jobs are unavailable");
    } finally {
      if (!options.silent) setJobsLoading(false);
    }
  }, [canViewJobs, generationRequestHeaders]);

  const fetchA2aJob = useCallback(async (jobId: string): Promise<A2AJob | null> => {
    if (!jobId) return null;
    try {
      const res = await fetch(`${API_URL}/a2a/jobs/${encodeURIComponent(jobId)}`, {
        headers: await generationRequestHeaders(),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (error) {
      console.error("Error fetching A2A job", error);
      return null;
    }
  }, [generationRequestHeaders]);

  const changeJobStatusFilter = (status: string) => {
    setJobStatusFilter(status);
    fetchA2aJobs(status);
  };

  const fetchBackendLogs = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!canViewAdminTools) {
      setBackendLogs(null);
      setLogsError(null);
      setLogsLastUpdatedAt(null);
      return;
    }
    if (!options.silent) setLogsLoading(true);
    setLogsError(null);
    try {
      const params = new URLSearchParams({ lines: "300" });
      const res = await fetch(`${API_URL}/logs/backend?${params.toString()}`, {
        headers: await generationRequestHeaders(),
      });
      if (!res.ok) throw new Error(await readApiErrorMessage(res));
      const payload = await res.json();
      setBackendLogs(payload);
      setLogsLastUpdatedAt(new Date().toISOString());
    } catch (e) {
      console.error("Error fetching backend logs", e);
      setLogsError(e instanceof Error ? e.message : "Backend logs are unavailable");
    } finally {
      if (!options.silent) setLogsLoading(false);
    }
  }, [canViewAdminTools, generationRequestHeaders]);

  useEffect(() => {
    if (!canViewAdminTools) return;
    fetchBackendLogs({ silent: true });
  }, [canViewAdminTools, fetchBackendLogs]);

  useEffect(() => {
    if (!normalizeTab(activeTab)) setActiveTab("chat");
  }, [activeTab]);

  useEffect(() => {
    if (!canViewJobs) {
      setA2aJobs([]);
      setJobsLastUpdatedAt(null);
      setJobsError(null);
      return;
    }
    fetchA2aJobs(jobStatusFilter);

    const pollJobs = () => {
      if (document.visibilityState === "visible") {
        fetchA2aJobs(jobStatusFilter, { silent: true });
      }
    };

    const intervalId = window.setInterval(pollJobs, JOB_POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", pollJobs);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", pollJobs);
    };
  }, [canViewJobs, fetchA2aJobs, jobStatusFilter]);

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
          writeStoredChatThread(chatId, nextMessages);
          persistChatThread(chatId, nextMessages);
        }
        nextThreads[chatId] = nextMessages;
      });
      return changed ? nextThreads : current;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a2aJobs, generateProductImage]);

  useEffect(() => {
    if (!canViewAdminTools) return;
    if (homeView !== "logs" && activeTab !== "logs") return;
    fetchBackendLogs();

    const pollLogs = () => {
      if (document.visibilityState === "visible") {
        fetchBackendLogs({ silent: true });
      }
    };

    const intervalId = window.setInterval(pollLogs, LOG_POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", pollLogs);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", pollLogs);
    };
  }, [activeTab, canViewAdminTools, fetchBackendLogs, homeView]);

  useEffect(() => {
    if (routeProjectId || projectIR) return;

    const imageProjects = mergeProjectRecords(projectHistory, myProjectHistory);
    const missingProjects = imageProjects.filter((project: any) => {
      const projectId = project?.project_id ? String(project.project_id) : "";
      return projectId && projectGalleryImages[projectId] === undefined;
    });
    if (!missingProjects.length) return;

    let cancelled = false;
    const controller = new AbortController();

    Promise.all(
      missingProjects.map(async (project: any): Promise<[string, ProjectImageCandidate | null]> => {
        const projectId = String(project.project_id);
        try {
          const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
            signal: controller.signal,
          });
          if (!res.ok) return [projectId, null];

          const data = await res.json();
          const ir = withProjectResponseMetadata(data.project_ir, data);
          return [projectId, resolveProjectImageCandidates(ir?.assembly_metadata || {})[0] || null];
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
  }, [myProjectHistory, projectHistory, projectGalleryImages, projectIR, routeProjectId]);

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

  const handleVideoImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      setVideoImageTouched(true);
      setVideoImageInput(reader.result as string);
      setSelectedVideoImageSources([]);
      setVideoStatusMessage(null);
    };
    reader.readAsDataURL(file);
  };

  const applyVideoStatusResponse = useCallback((data: any) => {
    const saved = data?.storedVideo || (Array.isArray(data?.savedVideos) ? data.savedVideos[0] : null);
    const statusValue = typeof data?.status === "string" ? data.status : saved ? "succeeded" : "queued";

    if (saved) {
      setStoredVideo(saved);
      setVideoGallery((current) => mergeStoredVideoGallery(current, [saved]));
      const savedKey = videoIdentity(saved);
      if (savedKey) setSelectedVideoReviewKey(savedKey);
      setVideoStatus("succeeded");
      setVideoStatusMessage("Video saved.");
      return;
    }

    setStoredVideo(null);
    setVideoStatus(statusValue);
    setVideoStatusMessage(statusValue === "queued" ? "Queued." : `Status: ${statusValue}.`);
  }, []);

  const pollVideoStatus = useCallback(async (requestId = videoRequestId, context: VideoPollContext = {}) => {
    const projectId = projectIdFromIR(projectIR);
    const model = (context.model || selectedVideoModel).trim();
    const modeForRequest = context.mode || videoMode;
    if (!requestId || !projectId || !model) return;

    const params = new URLSearchParams({
      projectId,
      model,
      mode: modeForRequest,
    });
    const promptForRequest = (context.prompt ?? videoPrompt).trim();
    const aspectRatioForRequest = (context.aspectRatio ?? videoAspectRatio).trim();
    const sourceUrlForRequest = (context.sourceUrl ?? (modeForRequest === "video-to-video" ? videoSourceVideoUrl : "")).trim();
    if (promptForRequest) params.set("prompt", promptForRequest);
    if (aspectRatioForRequest) params.set("aspectRatio", aspectRatioForRequest);
    if (sourceUrlForRequest) params.set("sourceUrl", sourceUrlForRequest);

    try {
      const res = await fetch(`${API_URL}/video/image-to-video/status/${encodeURIComponent(requestId)}?${params.toString()}`, {
        headers: await generationRequestHeaders(),
      });
      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      applyVideoStatusResponse(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network request failed.";
      setVideoStatus("failed");
      setVideoStatusMessage(message);
    }
  }, [applyVideoStatusResponse, generationRequestHeaders, projectIR, selectedVideoModel, videoAspectRatio, videoMode, videoPrompt, videoRequestId, videoSourceVideoUrl]);

  const handleGenerateVideoPrompt = async () => {
    const projectId = currentProjectId || projectIdFromIR(projectIR);
    if (!projectId) {
      setVideoPromptMessage("Open a generated project before creating a video prompt.");
      return;
    }

    setVideoPromptGenerating(true);
    setVideoPromptMessage("Generating prompt from project namespaces.");
    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/video-prompt`);
      if (!res.ok) throw new Error(await readApiErrorMessage(res));
      const data = await res.json();
      const nextPrompt = typeof data?.prompt === "string" ? data.prompt.trim() : "";
      if (!nextPrompt) throw new Error("The project did not return a usable video prompt.");
      const fittedPrompt = fitVideoPromptForProvider(nextPrompt);
      const providerMax = Number(data?.prompt_max_chars || VIDEO_PROMPT_MAX_CHARS);
      const wasTrimmed = Boolean(data?.prompt_truncated) || videoPromptWasTrimmed(nextPrompt, fittedPrompt);
      setVideoMode("image-to-video");
      setVideoPrompt(fittedPrompt);
      const namespaceCount = Array.isArray(data?.namespaces) ? data.namespaces.length : 0;
      setVideoPromptMessage(
        [
          namespaceCount
            ? `Prompt generated from ${namespaceCount} namespaces.`
            : "Prompt generated from project namespaces.",
          wasTrimmed ? `Trimmed to fit the video provider prompt limit (${providerMax} chars).` : "",
        ].filter(Boolean).join(" ")
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Video prompt generation failed.";
      setVideoPromptMessage(message);
    } finally {
      setVideoPromptGenerating(false);
    }
  };

  const handleGenerateVideo = async () => {
    if (!(await requireSignedInForGeneration())) return;
    if (videoGenerationConfig.configured === false) {
      setVideoStatus("idle");
      setVideoStatusMessage("Video generation is coming soon.");
      return;
    }

    const projectId = projectIdFromIR(projectIR);
    const manualImage = videoImageInput.trim();
    const selectedProjectImages = selectedVideoImageSources.filter((source) => source.trim());
    const images = selectedProjectImages.length ? selectedProjectImages : manualImage ? [manualImage] : [];
    const sourceVideo = videoSourceVideoUrl.trim();
    const rawPromptText = videoPrompt.trim();
    const promptText = fitVideoPromptForProvider(rawPromptText);
    const model = selectedVideoModel.trim();
    const isVideoToVideo = videoMode === "video-to-video";

    if (!projectId || !promptText || !model || (isVideoToVideo ? !sourceVideo : !images.length)) {
      setVideoStatus("failed");
      setVideoStatusMessage(`Project id, ${isVideoToVideo ? "source video" : "image"}, prompt, and model are required.`);
      return;
    }
    if (videoPromptWasTrimmed(rawPromptText, promptText)) {
      setVideoPrompt(promptText);
      setVideoPromptMessage(`Prompt trimmed to the video provider limit (${VIDEO_PROMPT_MAX_CHARS} chars).`);
    }

    setVideoRequestId(null);
    setStoredVideo(null);
    setVideoStatus("loading");
    setVideoStatusMessage("Starting.");
    setVideoReviewStatus("idle");
    setVideoReviewMessage(null);

    try {
      const sources = isVideoToVideo ? [sourceVideo] : images;
      for (let index = 0; index < sources.length; index += 1) {
        const source = sources[index];
        const selectedImage = !isVideoToVideo ? videoImageOptions.find((candidate) => candidate.src === source) : null;
        const sourceViewSuffix = selectedImage?.label ? `\nSource view: ${selectedImage.label}.` : "";
        const viewPrompt = fitVideoPromptForProvider(promptText, sourceViewSuffix);
        if (sourceViewSuffix && videoPromptWasTrimmed(`${promptText}${sourceViewSuffix}`, viewPrompt)) {
          setVideoPromptMessage(`Prompt trimmed so the selected image label fits the provider limit (${VIDEO_PROMPT_MAX_CHARS} chars).`);
        }
        setVideoStatusMessage(sources.length > 1 ? `Starting ${index + 1} of ${sources.length}.` : "Starting.");

        const res = await fetch(`${API_URL}/video/${isVideoToVideo ? "video-to-video" : "image-to-video"}`, {
          method: "POST",
          headers: await generationRequestHeaders(),
          body: JSON.stringify({
            projectId,
            ...(isVideoToVideo ? { video: source } : { image: source }),
            prompt: viewPrompt,
            model,
            duration: videoDuration,
            aspectRatio: videoAspectRatio,
            sound: "off",
          }),
        });

        if (!res.ok) throw new Error(await readApiErrorMessage(res));

        const data = await res.json();
        const requestId = typeof data?.requestId === "string" ? data.requestId : null;
        setVideoRequestId(requestId);
        applyVideoStatusResponse(data);
        if (requestId && !data?.storedVideo) {
          window.setTimeout(() => {
            pollVideoStatus(requestId, {
              model,
              mode: videoMode,
              prompt: viewPrompt,
              sourceUrl: source,
              aspectRatio: videoAspectRatio,
            });
          }, 800 + index * 400);
        }
      }
      setVideoStatusMessage(sources.length > 1 ? `Queued ${sources.length} video requests.` : null);
      fetchProjectVideos(projectId, { silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network request failed.";
      setVideoStatus("failed");
      setVideoStatusMessage(message);
    }
  };

  const handleVideoSelfCorrect = async (targetVideo?: StoredVideoInfo) => {
    if (!(await requireSignedInForGeneration())) return;
    if (videoSelfCorrectionConfig.configured === false) {
      setVideoReviewStatus("failed");
      setVideoReviewMessage(videoSelfCorrectionConfig.reason || "Video review is not configured.");
      return;
    }

    const projectId = currentProjectId || projectIdFromIR(projectIR);
    const reviewTarget = targetVideo || selectedReviewVideo;
    const targetKey = videoIdentity(reviewTarget);
    const videoUrl = (videoSourceUrl(reviewTarget) || reviewableVideoUrl).trim();
    if (!projectId || !videoUrl || !reviewTarget) {
      setVideoReviewStatus("failed");
      setVideoReviewMessage("A project and saved video with a reviewable URL are required.");
      return;
    }
    if (targetKey) setSelectedVideoReviewKey(targetKey);

    setIsLoading(true);
    setVideoReviewStatus("loading");
    setVideoReviewMessage(videoReviewMakeNewVideo ? "Reviewing video. New video will queue after correction." : "Reviewing video.");

    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/video-self-correct`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        body: JSON.stringify({
          video_url: videoUrl,
          video_key: reviewTarget.key || null,
          save: true,
        }),
      });

      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);

      const review = data.video_review || {};
      const issueCount = Array.isArray(review.issues) ? review.issues.length : 0;
      const summary = typeof review.summary === "string" ? review.summary : "Video review iteration applied.";
      const reviewMessage = issueCount ? `${summary} ${issueCount} issue${issueCount === 1 ? "" : "s"} applied.` : summary;
      setVideoReviewStatus("succeeded");
      setVideoReviewMessage(reviewMessage);
      refreshProjectAndChatLists();
      fetchA2aJobs(jobStatusFilter, { silent: true });

      if (videoReviewMakeNewVideo) {
        if (videoGenerationConfig.configured === false) {
          const message = videoGenerationConfig.reason || "Video generation is not configured.";
          setVideoStatus("failed");
          setVideoStatusMessage(message);
          setVideoReviewMessage(`${reviewMessage} New video was not queued: ${message}`);
          return;
        }

        const nextModel =
          videoModels.find((model) => model.mode === "video-to-video" && model.id === selectedVideoModel)?.id ||
          videoModels.find((model) => model.mode === "video-to-video")?.id ||
          "";
        if (!nextModel) {
          const message = "No video-to-video model is available for a new iteration.";
          setVideoStatus("failed");
          setVideoStatusMessage(message);
          setVideoReviewMessage(`${reviewMessage} New video was not queued: ${message}`);
          return;
        }

        const savedPrompt = videoPromptText(reviewTarget);
        const rawCorrectionPrompt = [
          savedPrompt || videoPrompt.trim() || "Create a corrected hardware product video iteration.",
          summary ? `Correction guidance: ${summary}` : "",
        ].filter(Boolean).join("\n");
        const correctionPrompt = fitVideoPromptForProvider(rawCorrectionPrompt);
        const correctionPromptTrimmed = videoPromptWasTrimmed(rawCorrectionPrompt, correctionPrompt);

        setVideoMode("video-to-video");
        setVideoSourceVideoUrl(videoUrl);
        setSelectedVideoModel(nextModel);
        if (correctionPrompt) setVideoPrompt(correctionPrompt);
        setVideoRequestId(null);
        setStoredVideo(null);
        setVideoStatus("loading");
        setVideoStatusMessage(correctionPromptTrimmed ? "Starting corrected video with a trimmed prompt." : "Starting corrected video.");

        try {
          const videoRes = await fetch(`${API_URL}/video/video-to-video`, {
            method: "POST",
            headers: await generationRequestHeaders(),
            body: JSON.stringify({
              projectId,
              video: videoUrl,
              prompt: correctionPrompt,
              model: nextModel,
              duration: videoDuration,
              aspectRatio: videoAspectRatio,
              sound: "off",
            }),
          });

          if (!videoRes.ok) throw new Error(await readApiErrorMessage(videoRes));

          const videoData = await videoRes.json();
          const requestId = typeof videoData?.requestId === "string" ? videoData.requestId : null;
          setVideoRequestId(requestId);
          applyVideoStatusResponse(videoData);
          setVideoReviewMessage(`${reviewMessage} New video queued from the selected card.`);
          if (requestId && !videoData?.storedVideo) {
            window.setTimeout(() => {
              pollVideoStatus(requestId, {
                model: nextModel,
                mode: "video-to-video",
                prompt: correctionPrompt,
                sourceUrl: videoUrl,
                aspectRatio: videoAspectRatio,
              });
            }, 800);
          }
          fetchProjectVideos(projectId, { silent: true });
        } catch (videoError) {
          const message = videoError instanceof Error ? videoError.message : "New video request failed.";
          setVideoStatus("failed");
          setVideoStatusMessage(message);
          setVideoReviewMessage(`${reviewMessage} New video was not queued: ${message}`);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Video review failed.";
      setVideoReviewStatus("failed");
      setVideoReviewMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  const buildReactFlowGraph = (ir: any) => {
    if (!ir?.components) return;

    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];
    const electricalParts = ir.components.filter(
      (component: any) => !["mechanical", "3d print"].includes(component.category?.toLowerCase())
    );
    const electricalRefs = new Set(electricalParts.map((component: any) => component.ref_des));
    const componentByRef = new Map<string, any>(electricalParts.map((component: any) => [component.ref_des, component]));
    const pinMapByRef = new Map<string, Map<string, SchematicPin>>();
    const netTypesByPin = new Map<string, Set<string>>();

    electricalParts.forEach((component: any) => {
      const pinMap = new Map<string, SchematicPin>();
      (component.pins || []).forEach((pin: any) => {
        if (!pin?.pin_id) return;
        pinMap.set(pin.pin_id, {
          pin_id: pin.pin_id,
          name: pin.name,
          pin_type: pin.pin_type,
          voltage: pin.voltage,
        });
      });
      pinMapByRef.set(component.ref_des, pinMap);
    });

    (ir.nets || []).forEach((net: any) => {
      (net.pins || []).forEach((pinRef: any) => {
        if (!electricalRefs.has(pinRef.ref_des)) return;
        const key = schematicHandleId(pinRef.ref_des, pinRef.pin_id);
        if (!netTypesByPin.has(key)) netTypesByPin.set(key, new Set());
        netTypesByPin.get(key)?.add(net.net_type || "default");
        const pinMap = pinMapByRef.get(pinRef.ref_des);
        if (!pinMap) return;
        const existing = pinMap.get(pinRef.pin_id);
        if (existing) {
          pinMap.set(pinRef.pin_id, {
            ...existing,
            connected: true,
            netTypes: Array.from(netTypesByPin.get(key) || []),
            pin_type: existing.pin_type || net.net_type,
            voltage: existing.voltage ?? net.voltage,
          });
          return;
        }
        pinMap.set(pinRef.pin_id, {
          pin_id: pinRef.pin_id,
          name: pinRef.pin_id,
          pin_type: net.net_type,
          voltage: net.voltage,
          connected: true,
          netTypes: Array.from(netTypesByPin.get(key) || []),
        });
      });
    });

    const schematicMeta = ir.assembly_metadata?.schematic || {};
    const explicitPlacements = schematicMeta.placements || {};
    const controller =
      electricalParts.find((component: any) => isControllerComponent(component)) ||
      electricalParts.find((component: any) => String(component.ref_des || "").toUpperCase() === "U1") ||
      electricalParts[0];
    const sideCounts = { left: 0, right: 0 };
    const leftParts: any[] = [];
    const rightParts: any[] = [];

    electricalParts
      .filter((component: any) => component.ref_des !== controller?.ref_des)
      .forEach((component: any, index: number) => {
        const side = schematicSideForComponent(component, index, sideCounts);
        if (side === "left") {
          leftParts.push(component);
          sideCounts.left += 1;
        } else {
          rightParts.push(component);
          sideCounts.right += 1;
        }
      });

    const positionedParts = [
      ...leftParts.map((component, index) => ({ component, side: "left" as const, index })),
      ...(controller ? [{ component: controller, side: "both" as const, index: 0 }] : []),
      ...rightParts.map((component, index) => ({ component, side: "right" as const, index })),
    ];
    const sideRows = Math.min(
      6,
      Math.max(3, Math.ceil(Math.max(leftParts.length, rightParts.length, 1) / 2))
    );
    const controllerY = 118 + Math.max(0, sideRows - 4) * 42;

    positionedParts.forEach(({ component, side, index }) => {
      const category = normalizeSchematicCategory(component.category || "default");
      const placement = normalizePlacement(explicitPlacements[component.ref_des]);
      const isController = component.ref_des === controller?.ref_des;
      const allPins = sortSchematicPins(Array.from(pinMapByRef.get(component.ref_des)?.values() || []));
      const connectedPins = allPins.filter((pin) => pin.connected);
      const visiblePins = connectedPins.length ? connectedPins : allPins.slice(0, isController ? 18 : 4);
      const splitPins = isController
        ? splitControllerPins(visiblePins)
        : side === "left"
          ? { leftPins: [], rightPins: visiblePins }
          : { leftPins: visiblePins, rightPins: [] };
      const position =
        placement ||
        (isController
          ? { x: 596, y: controllerY }
          : schematicGridPosition(side === "left" ? "left" : "right", index, sideRows));

      newNodes.push({
        id: component.ref_des,
        type: "schematicPart",
        position,
        draggable: true,
        data: {
          component,
          leftPins: splitPins.leftPins,
          rightPins: splitPins.rightPins,
          tone: schematicToneForCategory(category),
          roleLabel: schematicRoleLabel(component),
          connectionSide: side,
          isController,
        },
        style: { background: "transparent", border: "none", width: isController ? 300 : 240 },
      });
    });

    const netStyles: Record<string, { color: string; dash?: string; width: number }> = {
      ground: { color: "#64748b", width: 1.8 },
      power: { color: "#ef4444", width: 2.2 },
      i2c: { color: "#0ea5e9", width: 2 },
      spi: { color: "#22c55e", width: 2 },
      uart: { color: "#ec4899", width: 2 },
      digital: { color: "#8b5cf6", width: 2 },
      analog: { color: "#eab308", width: 2 },
      pwm: { color: "#f97316", width: 2 },
      default: { color: "#14b8a6", width: 2 },
    };

    const pinTypeForRef = (pinRef: any) =>
      pinMapByRef.get(pinRef.ref_des)?.get(pinRef.pin_id)?.pin_type?.toLowerCase() || "";

    const chooseSourcePin = (net: any, usablePins: any[]) => {
      const netType = net.net_type?.toLowerCase() || "default";
      if (netType === "power" || netType === "ground") {
        return (
          usablePins.find((pinRef: any) => componentByRef.get(pinRef.ref_des)?.category?.toLowerCase() === "power") ||
          usablePins.find((pinRef: any) => pinTypeForRef(pinRef) === netType) ||
          usablePins[0]
        );
      }
      return (
        usablePins.find((pinRef: any) => componentByRef.get(pinRef.ref_des)?.category?.toLowerCase() === "microcontroller") ||
        usablePins[0]
      );
    };

    const edgeLabel = (net: any, sourcePin: any, targetPin: any) => {
      const voltage = typeof net.voltage === "number" ? `${net.voltage}V` : net.net_type || "net";
      return `${net.name || net.net_id} / ${voltage} / ${sourcePin.pin_id}->${targetPin.pin_id}`;
    };

    (ir.nets || []).forEach((net: any) => {
      const netType = net.net_type?.toLowerCase() || "default";
      const style = netStyles[netType] || netStyles.default;
      const usablePins = (net.pins || []).filter((pinRef: any) => electricalRefs.has(pinRef.ref_des));

      if (usablePins.length < 2) return;

      const sourcePin = chooseSourcePin(net, usablePins);
      usablePins
        .filter((targetPin: any) => targetPin !== sourcePin)
        .forEach((targetPin: any, index: number) => {
          const id = `edge_${net.net_id}_${sourcePin.ref_des}_${sourcePin.pin_id}_to_${targetPin.ref_des}_${targetPin.pin_id}_${index}`;

          newEdges.push({
            id,
            source: sourcePin.ref_des,
            sourceHandle: schematicHandleId(sourcePin.ref_des, sourcePin.pin_id),
            target: targetPin.ref_des,
            targetHandle: schematicHandleId(targetPin.ref_des, targetPin.pin_id),
            type: "smoothstep",
            animated: false,
            label: undefined,
            data: { label: edgeLabel(net, sourcePin, targetPin), net },
            style: {
              stroke: style.color,
              strokeWidth: style.width,
              opacity: 0.82,
              strokeDasharray: style.dash || "none",
            },
          });
        });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  };

  const handleGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!(await requireSignedInForGeneration())) return;
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

    if (!contextCheckpoint) {
      setIsLoading(true);
      setGenerationInputNotice(null);
      try {
        const clarification = await requestHumanContextQuestions(validationSubject.trim(), generationWorkflow, Boolean(imageData));
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
          return;
        }
      } finally {
        setIsLoading(false);
      }
    }

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

    setGenerationInputNotice(null);
    setPendingHumanContext(null);
    setPrompt("");
    setIsLoading(true);
    checkServerStatus();
    progressPollId = window.setInterval(() => {
      void syncProgressFromJob();
    }, ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS);
    void syncProgressFromJob();

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: await generationRequestHeaders(),
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
          console.error("Blueprint API debug trace", apiError);
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
          if (apiError.code === "alpha_generation_unavailable") {
            setAlphaGateConfig({ gateActive: true });
          }
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
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);
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
        creator_image_url: user?.imageUrl || null,
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
      if (alphaGateActive) {
        setAlphaSignupMessage("Generation is not available in this alpha deployment yet. Leave your information and we will follow up when it opens.");
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
        setMermaidCode(mockRes.mermaid_code);
        setSvgSchematic(mockRes.svg_schematic);
        buildReactFlowGraph(mockRes.project_ir);
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
          creator_image_url: user?.imageUrl || null,
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
      setIsLoading(false);
    }
  };

  const handleProjectChatGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
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
    let progressPollId: number | null = null;
    const syncProgressFromJob = async () => {
      const job = await fetchA2aJob(frontendJobId);
      if (!job) return;
      applyThreadPipelineProgressFromJob(sourceChatId, assistantMessageId, job, pipelineProgress, generateProductImage);
    };

    setProjectChatInput("");
    setGenerationInputNotice(null);
    setIsLoading(true);
    checkServerStatus();
    progressPollId = window.setInterval(() => {
      void syncProgressFromJob();
    }, ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS);
    void syncProgressFromJob();

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: await generationRequestHeaders(),
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
          console.error("Blueprint API debug trace", apiError);
        }
        if (res.status === 503 && apiError.code === "alpha_generation_unavailable") {
          setAlphaGateConfig({ gateActive: true });
        }
        throw new Error(compactDiagnosticText(apiError.message) || apiError.message);
      }

      const data = await res.json();
      if (data.job) {
        applyThreadPipelineProgressFromJob(sourceChatId, assistantMessageId, data.job, pipelineProgress, generateProductImage);
      }
      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);
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
        creator_image_url: user?.imageUrl || null,
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
      const message = error instanceof Error ? error.message : "Project chat generation failed.";
      updateThreadMessage(sourceChatId, assistantMessageId, {
        content: message,
        status: "error",
      });
    } finally {
      if (progressPollId !== null) window.clearInterval(progressPollId);
      setIsLoading(false);
    }
  };

  const handleAlphaSignup = async (event: React.FormEvent) => {
    event.preventDefault();
    setAlphaSignupStatus("submitting");
    setAlphaSignupMessage(null);

    try {
      const res = await fetch(`${API_URL}/alpha-signups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: alphaSignupForm.name,
          email: alphaSignupForm.email,
          organization: alphaSignupForm.organization || null,
          additional_info: alphaSignupForm.additionalInfo || null,
        }),
      });

      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      setAlphaSignupStatus("success");
      setAlphaSignupMessage(data.message || "Thanks. We will follow up when generation opens.");
      setAlphaSignupForm({
        name: "",
        email: "",
        organization: "",
        additionalInfo: "",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Signup failed. Please try again.";
      setAlphaSignupStatus("error");
      setAlphaSignupMessage(message);
    }
  };

  const loadExample = async (filename: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`/examples/${filename}`);
      if (!res.ok) return;

      const ir = await res.json();
      setProjectIR(ir);
      setMermaidCode(pipelineMermaidCode);
      setSvgSchematic(generateMockSvg(ir));
      buildReactFlowGraph(ir);
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

  const generateMockSvg = (ir: any): string => {
    const components = ir.components || [];
    const controller =
      components.find((component: any) => component.category?.toLowerCase() === "microcontroller") || components[0];
    const inputs = components
      .filter((component: any) => ["sensor", "power"].includes(component.category?.toLowerCase()))
      .slice(0, 2);
    const outputs = components
      .filter((component: any) => ["actuator", "display", "passives"].includes(component.category?.toLowerCase()))
      .slice(0, 3);

    return `<svg viewBox="0 0 880 420" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <rect width="880" height="420" fill="#141519"/>
      <g stroke="#2a2d35" stroke-width="1">
        <path d="M40 80 H840"/><path d="M40 180 H840"/><path d="M40 280 H840"/>
        <path d="M180 40 V380"/><path d="M440 40 V380"/><path d="M700 40 V380"/>
      </g>
      <text x="44" y="42" font-family="monospace" font-size="14" font-weight="700" fill="#ffffff">BLUEPRINT WIRING DIAGRAM</text>
      <text x="44" y="64" font-family="monospace" font-size="11" fill="#8b8e99">Generated from validated Hardware IR</text>
      <rect x="330" y="116" width="220" height="188" fill="#111216" stroke="#22d3ee" stroke-width="2"/>
      <text x="440" y="154" font-family="monospace" font-size="15" font-weight="700" fill="#ffffff" text-anchor="middle">MAIN CONTROLLER</text>
      <text x="440" y="177" font-family="monospace" font-size="12" fill="#22d3ee" text-anchor="middle">${controller?.part_number || "Controller"}</text>
      <rect x="60" y="92" width="170" height="86" fill="#111216" stroke="#34d399" stroke-width="1.5"/>
      <text x="145" y="127" font-family="monospace" font-size="12" font-weight="700" fill="#ffffff" text-anchor="middle">INPUT</text>
      <text x="145" y="149" font-family="monospace" font-size="11" fill="#34d399" text-anchor="middle">${(inputs[0]?.name || "Sensor input").slice(0, 23)}</text>
      <path d="M230 135 C270 135 286 162 330 164" fill="none" stroke="#34d399" stroke-width="2"/>
      <rect x="60" y="228" width="170" height="86" fill="#111216" stroke="#facc15" stroke-width="1.5"/>
      <text x="145" y="263" font-family="monospace" font-size="12" font-weight="700" fill="#ffffff" text-anchor="middle">POWER</text>
      <text x="145" y="285" font-family="monospace" font-size="11" fill="#facc15" text-anchor="middle">${(inputs[1]?.name || "Power rail").slice(0, 23)}</text>
      <path d="M230 271 H330" fill="none" stroke="#facc15" stroke-width="2" stroke-dasharray="7 7"/>
      <rect x="650" y="76" width="170" height="86" fill="#111216" stroke="#a78bfa" stroke-width="1.5"/>
      <text x="735" y="111" font-family="monospace" font-size="12" font-weight="700" fill="#ffffff" text-anchor="middle">OUTPUT</text>
      <text x="735" y="133" font-family="monospace" font-size="11" fill="#a78bfa" text-anchor="middle">${(outputs[0]?.name || "Output module").slice(0, 23)}</text>
      <path d="M550 166 C596 150 605 120 650 119" fill="none" stroke="#a78bfa" stroke-width="2"/>
      <rect x="650" y="196" width="170" height="86" fill="#111216" stroke="#ec4899" stroke-width="1.5"/>
      <text x="735" y="231" font-family="monospace" font-size="12" font-weight="700" fill="#ffffff" text-anchor="middle">MODULE</text>
      <text x="735" y="253" font-family="monospace" font-size="11" fill="#ec4899" text-anchor="middle">${(outputs[1]?.name || "Display").slice(0, 23)}</text>
      <path d="M550 231 H650" fill="none" stroke="#ec4899" stroke-width="2"/>
    </svg>`;
  };

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
      mermaid_code: pipelineMermaidCode,
      svg_schematic: generateMockSvg(ir),
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
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);
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

  useEffect(() => {
    if (!routeProjectId) {
      setRouteProjectError(null);
      return;
    }

    const controller = new AbortController();
    const projectId = safeDecodeProjectId(routeProjectId);
    const tab = normalizeTab(new URLSearchParams(window.location.search).get("tab"));
    setChatRouteTransition(null);
    setProjectIR(null);
    setMermaidCode("");
    setSvgSchematic("");
    setRouteProjectError(null);

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
  }, [routeProjectId]);

  useEffect(() => {
    if (!routeChatId || routeProjectId) return;
    if (authRequired && !isSignedIn) return;

    const controller = new AbortController();
    const chatId = safeDecodeChatId(routeChatId);
    const storedMessages = readStoredChatThread(chatId);
    const chatItem = chatListItems.find((item) => item.chatId === chatId);
    const chatSourcesReady = chatIndexLoaded && chatHistoryLoaded;
    setActiveChatId(chatId);
    setActiveTab("chat");
    setRouteProjectError(null);
    if (storedMessages.length) {
      setChatThreads((current) => ({ ...current, [chatId]: storedMessages }));
      setChatMessages(storedMessages);
    } else {
      setChatMessages(initialChatMessages());
    }

    if (!chatSourcesReady && !chatItem) {
      setChatRouteTransition({ chatId, title: "Opening chat", projectId: "", error: null });
      return () => {
        controller.abort();
      };
    }

    if (!chatItem && chatSourcesReady) {
      rememberChatItem({
        chatId,
        title: NEW_PROJECT_TITLE,
        projectId: "",
        createdAt: chatTimestamp(),
        projectCount: 0,
      });
    }

    if (!chatItem?.projectId) {
      setChatRouteTransition(null);
      setProjectIR(null);
      setMermaidCode("");
      setSvgSchematic("");
      return () => {
        controller.abort();
      };
    }

    setChatRouteTransition({
      chatId,
      title: chatItem.title || "Opening chat",
      projectId: chatItem.projectId,
      error: null,
    });
    loadOldProject(chatItem.projectId, { syncRoute: false, signal: controller.signal, tab: "chat" }).then((loaded) => {
      if (controller.signal.aborted) return;
      if (loaded) {
        setChatRouteTransition(null);
        return;
      }
      setProjectIR(null);
      setMermaidCode("");
      setSvgSchematic("");
      setActiveTab("chat");
      const nextMessages = messagesWithoutMissingProject(
        storedMessages.length ? storedMessages : initialChatMessages(),
        chatItem.projectId
      );
      setChatThreads((current) => ({
        ...current,
        [chatId]: nextMessages,
      }));
      setChatMessages(nextMessages);
      writeStoredChatThread(chatId, nextMessages);
      persistChatThread(chatId, nextMessages, chatItem.title);
      detachMissingProjectFromChat(chatId, chatItem.projectId, chatItem.title);
      setChatRouteTransition(null);
    });

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeChatId, routeProjectId, chatListItems, chatIndexLoaded, chatHistoryLoaded, authRequired, isSignedIn]);

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
    const jsonStr = JSON.stringify(projectIR, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const title = projectIR.overview?.title || "blueprint_project";
    link.href = url;
    link.download = `${title.toLowerCase().replace(/\s+/g, "_")}_blueprint.json`;
    link.click();
    URL.revokeObjectURL(url);
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
  const videoImageOptionSources = useMemo(
    () => videoImageOptions.map((candidate) => candidate.src),
    [videoImageOptions]
  );
  const defaultVideoImage = projectImageCandidates[0]?.src || "";
  const currentProjectId = projectIR?.assembly_metadata?.project_id || null;
  const currentProjectCanChat = Boolean(projectIR && canChatWithProjectIR(projectIR) && (!authRequired || isSignedIn));
  const currentProjectCanDownloadAssets = currentProjectCanChat;
  const reviewableVideos = useMemo(
    () => videoGallery.filter((video) => Boolean(videoSourceUrl(video))),
    [videoGallery]
  );
  const selectedReviewVideo = useMemo(() => {
    const selected = selectedVideoReviewKey
      ? reviewableVideos.find((video, index) => videoIdentity(video, `video-${index}`) === selectedVideoReviewKey)
      : null;
    return selected || (videoSourceUrl(storedVideo) ? storedVideo : null) || reviewableVideos[0] || null;
  }, [selectedVideoReviewKey, storedVideo, reviewableVideos]);
  const reviewableVideoUrl = useMemo(() => {
    const selectedUrl = videoSourceUrl(selectedReviewVideo);
    if (selectedUrl) return selectedUrl;
    return "";
  }, [selectedReviewVideo]);
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
        return (
          <div className="flex h-full min-h-[620px] flex-col bg-[#111216]">
            <div className="flex min-h-[60px] flex-wrap items-center gap-3 border-b border-[#2a2c33] bg-[#17181d] px-4 py-3">
              <div className="mr-2 text-sm font-black text-white">Wiring diagram</div>
              <div className="inline-flex h-10 items-center gap-2 border border-[#3a3d46] bg-[#101116] px-3 text-xs font-black text-white">
                <Cpu className="h-4 w-4 text-slate-400" />
                <span>{primaryControllerLabel(projectIR)}</span>
              </div>
              <div className="ml-auto inline-flex overflow-hidden border border-[#2d3038]">
                <button type="button" className="inline-flex h-10 items-center gap-2 bg-[#ff6b3d] px-4 text-xs font-black text-white">
                  <ArrowRight className="h-4 w-4" />
                  Diagram
                </button>
                <button type="button" className="inline-flex h-10 items-center gap-2 bg-[#141519] px-4 text-xs font-bold text-slate-400">
                  <Database className="h-4 w-4" />
                  Breadboard
                </button>
              </div>
            </div>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={schematicNodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              fitView
              fitViewOptions={{ padding: 0.16 }}
              minZoom={0.28}
              maxZoom={1.6}
              proOptions={{ hideAttribution: true }}
              className="schematic-flow flex-1 bg-[#0f1014]"
            >
              <Background color="#262b33" gap={28} size={1.1} />
              <Controls position="bottom-right" className="!border !border-[#2f333c] !bg-[#15161b] !text-white" />
              <SchematicLegend />
            </ReactFlow>
          </div>
        );
      case "assembly":
        return <AssemblyPanel assembly={assembly} issues={issues} onDownload={downloadJSONIR} canDownloadAssets={currentProjectCanDownloadAssets} />;
      case "video":
        return (
          <VideoPanel
            projectId={currentProjectId}
            readOnly={!currentProjectCanChat}
            models={videoModels}
            modelsLoading={videoModelsLoading}
            modelsError={videoModelsError}
            selectedModel={selectedVideoModel}
            setSelectedModel={setSelectedVideoModel}
            mode={videoMode}
            setMode={setVideoMode}
            imageInput={videoImageInput}
            setImageInput={(value) => {
              setVideoImageTouched(true);
              setVideoImageInput(value);
            }}
            imageOptions={videoImageOptions}
            selectedImageSources={selectedVideoImageSources}
            setSelectedImageSources={setSelectedVideoImageSources}
            defaultImage={defaultVideoImage}
            sourceVideoUrl={videoSourceVideoUrl}
            setSourceVideoUrl={setVideoSourceVideoUrl}
            prompt={videoPrompt}
            setPrompt={setVideoPrompt}
            duration={videoDuration}
            setDuration={setVideoDuration}
            aspectRatio={videoAspectRatio}
            setAspectRatio={setVideoAspectRatio}
            aspectRatios={videoAspectRatios}
            status={videoStatus}
            statusMessage={videoStatusMessage}
            requestId={videoRequestId}
            storedVideo={storedVideo}
            gallery={videoGallery}
            galleryLoading={videoGalleryLoading}
            galleryError={videoGalleryError}
            generationAvailable={videoGenerationConfig.configured !== false}
            generationUnavailableReason={videoGenerationConfig.reason}
            reviewStatus={videoReviewStatus}
            reviewMessage={videoReviewMessage}
            reviewAvailable={videoSelfCorrectionConfig.configured !== false}
            reviewUnavailableReason={videoSelfCorrectionConfig.reason}
            selectedReviewVideoKey={selectedVideoReviewKey}
            setSelectedReviewVideoKey={setSelectedVideoReviewKey}
            makeNewVideo={videoReviewMakeNewVideo}
            setMakeNewVideo={setVideoReviewMakeNewVideo}
            promptGenerating={videoPromptGenerating}
            promptMessage={videoPromptMessage}
            onGenerate={handleGenerateVideo}
            onGeneratePrompt={handleGenerateVideoPrompt}
            onReview={handleVideoSelfCorrect}
            onReviewVideo={(video) => handleVideoSelfCorrect(video)}
            onUploadImage={() => fileInputRefVideo.current?.click()}
            onUseProjectImage={() => {
              setVideoImageTouched(false);
              const nextSource = videoImageOptions[0]?.src || defaultVideoImage;
              setVideoImageInput(nextSource);
              setSelectedVideoImageSources(nextSource ? [nextSource] : []);
            }}
            onRefreshGallery={() => {
              if (currentProjectId && currentProjectCanDownloadAssets) fetchProjectVideos(currentProjectId);
            }}
            canGenerate={Boolean(
              currentProjectCanChat &&
              videoGenerationConfig.configured !== false &&
                currentProjectId &&
                videoPrompt.trim() &&
                selectedVideoModel &&
                (videoMode === "video-to-video"
                  ? videoSourceVideoUrl.trim()
                  : selectedVideoImageSources.length > 0 || videoImageInput.trim())
            )}
            canReview={Boolean(
              currentProjectCanChat &&
              videoSelfCorrectionConfig.configured !== false &&
                currentProjectId &&
                selectedReviewVideo &&
                reviewableVideoUrl &&
                videoReviewStatus !== "loading" &&
                !isLoading
            )}
            canMakeNewVideo={currentProjectCanChat && videoGenerationConfig.configured !== false}
            canGeneratePrompt={Boolean(currentProjectCanChat && (currentProjectId || projectIdFromIR(projectIR)) && !videoPromptGenerating)}
          />
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

  useEffect(() => {
    setVideoImageTouched(false);
    setVideoRequestId(null);
    setStoredVideo(null);
    setVideoGallery([]);
    setVideoGalleryError(null);
    setSelectedVideoReviewKey(null);
    setVideoSourceVideoUrl("");
    setSelectedVideoImageSources([]);
    setVideoMode("image-to-video");
    setVideoPromptMessage(null);
    setVideoPromptGenerating(false);
    setVideoStatus("idle");
    setVideoStatusMessage(null);
    setVideoReviewStatus("idle");
    setVideoReviewMessage(null);
    setVideoReviewMakeNewVideo(false);
    if (fileInputRefVideo.current) fileInputRefVideo.current.value = "";
    if (currentProjectId && currentProjectCanDownloadAssets) fetchProjectVideos(currentProjectId);
  }, [currentProjectCanDownloadAssets, currentProjectId, fetchProjectVideos]);

  useEffect(() => {
    const keys = reviewableVideos
      .map((video, index) => videoIdentity(video, `video-${index}`))
      .filter(Boolean);
    setSelectedVideoReviewKey((current) => (current && keys.includes(current) ? current : keys[0] || null));
  }, [reviewableVideos]);

  useEffect(() => {
    setSelectedVideoImageSources((current) => {
      const retained = current.filter((source) => videoImageOptionSources.includes(source));
      if (retained.length) return retained;
      return videoImageOptionSources[0] ? [videoImageOptionSources[0]] : [];
    });
    if (!videoImageTouched) setVideoImageInput(videoImageOptionSources[0] || defaultVideoImage);
  }, [defaultVideoImage, videoImageOptionSources, videoImageTouched]);

  useEffect(() => {
    const modeModels = videoModels.filter((model) => model.mode === videoMode);
    if (modeModels.some((model) => model.id === selectedVideoModel)) return;
    setSelectedVideoModel(modeModels[0]?.id || "");
  }, [selectedVideoModel, videoMode, videoModels]);

  useEffect(() => {
    const sourceVideos = videoGallery.map(videoSourceUrl).filter(Boolean);
    if (!sourceVideos.length) {
      setVideoSourceVideoUrl("");
      if (videoMode === "video-to-video") setVideoMode("image-to-video");
      return;
    }
    setVideoSourceVideoUrl((current) => (current && sourceVideos.includes(current) ? current : sourceVideos[0]));
  }, [videoGallery, videoMode]);

  useEffect(() => {
    if (!videoRequestId || storedVideo || isFinalVideoStatus(videoStatus)) return;

    const intervalId = window.setInterval(() => {
      pollVideoStatus(videoRequestId);
    }, VIDEO_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [pollVideoStatus, storedVideo, videoRequestId, videoStatus]);

  const chatTransitionProjectId = chatRouteTransition?.projectId || "";
  const loadedProjectId = projectIdFromIR(projectIR);
  const showChatRouteFallback = Boolean(
    !routeProjectId &&
      chatRouteTransition &&
      (chatRouteTransition.error || !chatTransitionProjectId || loadedProjectId !== chatTransitionProjectId)
  );
  const privateChatRouteRequested = Boolean(authRequired && routeChatId && !routeProjectId);
  const privateChatRouteLoading = privateChatRouteRequested && !authLoaded;
  const privateChatRouteDenied = privateChatRouteRequested && authLoaded && !isSignedIn;

  if (privateChatRouteLoading || privateChatRouteDenied) {
    return (
      <AuthRequiredRouteScreen
        loading={privateChatRouteLoading}
        title="Private chat"
        message="Sign in to open this chat."
        onHome={goHome}
      />
    );
  }

  if (showChatRouteFallback && chatRouteTransition) {
    return (
      <ChatRouteFallback
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((value) => !value)}
        chats={chatListItems}
        activeChatId={chatRouteTransition.chatId}
        onNewChat={startNewProjectChat}
        newChatDisabled={!activeSidebarChatStarted}
        onOpenChat={openChatItem}
        waitingChatIds={waitingChatIds}
        showJobs={canViewJobs}
        showDeveloperTools={showDeveloperTools}
        authRequired={authRequired}
        serverStatus={serverStatus}
        transition={chatRouteTransition}
        onHome={goHome}
      />
    );
  }

  if (routeProjectId && !projectIR) {
    return (
      <ProjectRouteFallback
        projectId={safeDecodeProjectId(routeProjectId)}
        error={routeProjectError}
        onHome={goHome}
      />
    );
  }

	  if (!projectIR) {
	    return (
	      <div className="h-[100dvh] w-full overflow-hidden bg-[#141519] font-sans text-slate-100">
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
		          showJobs={canViewJobs}
		          showDeveloperTools={showDeveloperTools}
	          authRequired={authRequired}
	          serverStatus={serverStatus}
	        />
	        <div className={`grid h-full min-h-0 min-w-0 overflow-hidden ${sidebarCollapsed ? "md:grid-cols-[72px_minmax(0,1fr)]" : "md:grid-cols-[320px_minmax(0,1fr)]"}`}>
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
	            showJobs={canViewJobs}
	            showDeveloperTools={showDeveloperTools}
            authRequired={authRequired}
	            serverStatus={serverStatus}
	          />
	          <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden pt-12 md:pt-0">
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
                onOpenChat={(chatId) => router.push(chatRoute(chatId))}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
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
                items={authRequired ? myProjectGalleryItems : projectGalleryItems}
                onOpenChat={(chatId) => router.push(chatRoute(chatId))}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
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
            <>
            <section
              className={`${
                !activeSidebarChatStarted && !alphaGateActive
                  ? "fixed bottom-[276px] left-0 right-0 top-[3.75rem] z-10 max-w-none md:static md:inset-auto md:z-auto md:w-full md:max-w-none"
                  : "w-full max-w-none"
              } flex min-h-0 flex-1 flex-col text-center`}
            >
            {!activeSidebarChatStarted && (
              <div className="shrink-0">
                <h1 className="text-2xl font-semibold leading-tight text-white sm:mt-1 sm:text-4xl sm:leading-tight">
                  Turn an idea into a hardware plan.
                </h1>
                <p className="mx-auto mt-2 max-w-2xl text-xs leading-5 text-slate-400 sm:mt-3 sm:text-sm sm:leading-6">
                  Upload a photo, sketch, or short description. Get parts, wiring, cost, and build steps.
                </p>
              </div>
            )}

            {alphaGateActive ? (
              <div className="mt-8 grid gap-3 text-left md:grid-cols-[0.95fr_1.05fr]">
                <div className="border border-[#2c2f37] bg-[#17181d] p-5 shadow-2xl shadow-black/30">
                  <div className="inline-flex items-center gap-2 border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-xs font-black uppercase text-cyan-200">
                    <Sparkles className="h-4 w-4" />
                    Alpha
                  </div>
                  <h2 className="mt-5 text-2xl font-semibold leading-tight text-white">Generation is opening soon.</h2>
                  <p className="mt-4 text-sm leading-6 text-slate-400">
                    We are currently in alpha right now. Please view our generated projects below. To learn more about this project and when generation will be available, leave your information.
                  </p>
                  <div className="mt-5 border-t border-[#2c2f37] pt-4 text-xs leading-5 text-slate-500">
                    Live generation is paused for this deployment while the model backend is being configured.
                  </div>
                </div>

                <form onSubmit={handleAlphaSignup} className="border border-[#2c2f37] bg-[#17181d] p-5 shadow-2xl shadow-black/30">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-xs font-semibold uppercase text-slate-500">
                      Name
                      <input
                        required
                        value={alphaSignupForm.name}
                        onChange={(event) => setAlphaSignupForm((form) => ({ ...form, name: event.target.value }))}
                        className="mt-2 h-11 w-full border border-[#2c2f37] bg-black px-3 text-sm normal-case text-white outline-none focus:border-cyan-300"
                      />
                    </label>
                    <label className="block text-xs font-semibold uppercase text-slate-500">
                      Email
                      <input
                        required
                        type="email"
                        value={alphaSignupForm.email}
                        onChange={(event) => setAlphaSignupForm((form) => ({ ...form, email: event.target.value }))}
                        className="mt-2 h-11 w-full border border-[#2c2f37] bg-black px-3 text-sm normal-case text-white outline-none focus:border-cyan-300"
                      />
                    </label>
                  </div>
                  <label className="mt-3 block text-xs font-semibold uppercase text-slate-500">
                    Organization
                    <input
                      value={alphaSignupForm.organization}
                      onChange={(event) => setAlphaSignupForm((form) => ({ ...form, organization: event.target.value }))}
                      className="mt-2 h-11 w-full border border-[#2c2f37] bg-black px-3 text-sm normal-case text-white outline-none focus:border-cyan-300"
                    />
                  </label>
                  <label className="mt-3 block text-xs font-semibold uppercase text-slate-500">
                    Additional info
                    <textarea
                      value={alphaSignupForm.additionalInfo}
                      onChange={(event) => setAlphaSignupForm((form) => ({ ...form, additionalInfo: event.target.value }))}
                      className="mt-2 min-h-[96px] w-full resize-none border border-[#2c2f37] bg-black px-3 py-3 text-sm normal-case leading-6 text-white outline-none focus:border-cyan-300"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={alphaSignupStatus === "submitting"}
                    className="mt-4 inline-flex h-11 w-full items-center justify-center gap-2 bg-white px-4 text-sm font-semibold text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {alphaSignupStatus === "submitting" ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                    Join alpha updates
                  </button>
                  {alphaSignupMessage && (
                    <div
                      role="status"
                      className={`mt-3 flex items-start gap-2 border px-3 py-2 text-xs leading-5 ${
                        alphaSignupStatus === "success"
                          ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-100"
                          : "border-amber-300/30 bg-amber-300/10 text-amber-100"
                      }`}
                    >
                      {alphaSignupStatus === "success" ? <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
                      <span>{alphaSignupMessage}</span>
                    </div>
                  )}
                </form>
              </div>
            ) : (
              <div className={`${activeSidebarChatStarted ? "mt-0" : "mt-4 sm:mt-5"} flex min-h-0 flex-1 flex-col overflow-hidden border-y border-[#2c2f37] bg-[#111216] text-left shadow-2xl shadow-black/30`}>
                {activeSidebarChatStarted && (
                  <div className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-3 py-4 sm:px-4 sm:py-5">
                    {chatMessages.map((message) => {
                      const isUser = message.role === "user";
                      const statusTone =
                        message.status === "error"
                          ? "border-rose-400/40 bg-rose-950/30 text-rose-100"
                          : message.status === "success"
                            ? "border-emerald-400/35 bg-emerald-950/25 text-emerald-50"
                            : isUser
                              ? "border-cyan-300/45 bg-cyan-300/10 text-white"
                              : "border-[#30333d] bg-[#17181d] text-slate-100";
                      return (
                        <div key={message.id} className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
                          <div className={`min-w-0 max-w-[92%] overflow-hidden border px-3 py-2.5 sm:max-w-[86%] sm:px-4 sm:py-3 ${statusTone}`}>
                            <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                              {message.status === "loading" ? (
                                <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-300" />
                              ) : message.status === "success" ? (
                                <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
                              ) : message.status === "error" ? (
                                <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />
                              ) : isUser ? (
                                <ArrowRight className="h-3.5 w-3.5 text-cyan-300" />
                              ) : (
                                <Cpu className="h-3.5 w-3.5 text-slate-400" />
                              )}
                              <span>{isUser ? "You" : "Blueprint"}</span>
                              <span className="text-slate-700">/</span>
                              <span suppressHydrationWarning>{formatChatTimestamp(message.timestamp)}</span>
                            </div>
                            <p className="break-anywhere whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                            <AgentPipelineProgressView progress={message.pipelineProgress} status={message.status} compact />
                            {message.projectId && (
                              <button
                                type="button"
                                onClick={() => {
                                  if (message.projectId) loadOldProject(message.projectId, { syncRoute: false, tab: "chat" });
                                  syncChatRoute(activeChatId);
                                }}
                                className="mt-3 inline-flex h-9 items-center gap-2 border border-emerald-300/40 px-3 text-xs font-black uppercase text-emerald-100 hover:bg-emerald-300 hover:text-black"
                              >
                                <Eye className="h-4 w-4" />
                                Open project
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    <div ref={chatEndRef} />
                  </div>
                )}

                {!activeSidebarChatStarted && (
                  <div className="mt-auto shrink-0 bg-[#111216] px-3 py-3 sm:border-t sm:border-[#2c2f37] sm:px-4">
                    <div className="flex snap-x gap-2 overflow-x-auto pb-1 sm:flex-wrap sm:overflow-visible sm:pb-0">
                      {samplePrompts.map((example) => (
                        <button
                          key={example}
                          type="button"
                          onClick={() => {
                            setGenerationInputNotice(null);
                            setPendingHumanContext(null);
                            setPrompt(example);
                          }}
                          className="min-w-[260px] snap-start border border-[#2c2f37] bg-[#17181d] px-3 py-2 text-left text-[11px] leading-5 text-slate-400 hover:border-slate-500 hover:text-white sm:min-w-0"
                        >
                          {example}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <form onSubmit={handleGenerate} className="fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain border-y border-[#2c2f37] bg-[#141519]/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:p-4 md:sticky md:bottom-0 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible md:border-b-0 md:pb-4">
                  {pendingHumanContext && (
                    <div className="mb-3 border border-cyan-300/25 bg-cyan-300/5 p-3 sm:p-4">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <div className="inline-flex h-8 items-center gap-2 border border-cyan-300/30 bg-cyan-300/10 px-3 text-[10px] font-black uppercase tracking-[0.18em] text-cyan-100">
                          <Info className="h-3.5 w-3.5" />
                          Human Context Checkpoint
                        </div>
                        <div className="min-w-0 break-anywhere text-xs leading-5 text-slate-500">Answer what matters. Blank answers are recorded as unspecified.</div>
                      </div>
                      <div className="break-anywhere mt-3 max-h-24 overflow-y-auto border border-[#2c2f37] bg-[#0f1014] px-3 py-2 text-xs leading-5 text-slate-400">
                        {pendingHumanContext.basePrompt}
                      </div>
                      <div className="mt-3 grid max-h-[42dvh] gap-3 overflow-y-auto pr-1 md:max-h-none md:grid-cols-3 md:overflow-visible md:pr-0">
                        {pendingHumanContext.questions.map((question) => (
                          <label key={question.id} className="block min-w-0 border border-[#2c2f37] bg-[#111216] p-3">
                            <span className="break-anywhere text-[10px] font-black uppercase tracking-[0.16em] text-cyan-200">{question.label}</span>
                            <span className="break-anywhere mt-2 block text-xs leading-5 text-slate-300">{question.question}</span>
                            <textarea
                              value={pendingHumanContext.answers[question.id] || ""}
                              onChange={(event) => updateHumanContextAnswer(question.id, event.target.value)}
                              placeholder={question.placeholder}
                              className="mt-3 min-h-[72px] w-full resize-none border border-[#2c2f37] bg-black px-3 py-2 text-xs leading-5 text-white outline-none placeholder:text-slate-700 focus:border-cyan-300 sm:min-h-[92px]"
                            />
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {question.suggestions.map((suggestion) => (
                                <button
                                  key={suggestion}
                                  type="button"
                                  onClick={() => updateHumanContextAnswer(question.id, suggestion)}
                                  className="break-anywhere max-w-full border border-[#2c2f37] px-2 py-1 text-left text-[10px] font-bold text-slate-500 hover:border-cyan-300 hover:text-cyan-100"
                                >
                                  {suggestion}
                                </button>
                              ))}
                            </div>
                          </label>
                        ))}
                      </div>
                      <div className="mt-3 grid gap-2 sm:flex sm:flex-wrap sm:items-center">
                        <button
                          type="submit"
                          disabled={isLoading}
                          className="inline-flex h-10 items-center justify-center gap-2 bg-white px-4 text-xs font-black uppercase text-black hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                          Build with context
                        </button>
                        <button
                          type="button"
                          disabled={isLoading}
                          onClick={clearHumanContextCheckpoint}
                          className="inline-flex h-10 items-center justify-center gap-2 border border-[#2c2f37] px-4 text-xs font-black uppercase text-slate-400 hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <ArrowLeft className="h-4 w-4" />
                          Edit request
                        </button>
                      </div>
                    </div>
                  )}

                  {selectedImage && (
                    <div className="mb-3 flex items-center gap-3 border border-[#2c2f37] bg-black/30 p-2">
                      <img src={selectedImage} alt="Attached reference" className="h-16 w-24 object-cover" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold text-white">Image attached</div>
                        <div className="mt-1 text-[11px] text-slate-500">Blueprint will use this image with your next message.</div>
                      </div>
                      <button type="button" onClick={removeSelectedImage} className="p-2 text-slate-500 hover:text-white" aria-label="Remove image">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  )}

                  {visibleGenerationInputNotice && (
                    <div
                      id="generation-input-notice"
                      role="status"
                      className="mb-3 flex items-start gap-2 border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100"
                    >
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
                      <span className="break-anywhere min-w-0">{visibleGenerationInputNotice}</span>
                    </div>
                  )}

                  <div className="relative">
                    <textarea
                      value={prompt}
                      onChange={(event) => {
                        setGenerationInputNotice(null);
                        setPrompt(event.target.value);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                      placeholder={
                        pendingHumanContext
                          ? "Optional: add final context notes before building..."
                          : "Ask Blueprint to build a lab-on-chip reader, self-assembling tent, sensor node, robot fixture..."
                      }
                      aria-invalid={Boolean(visibleGenerationInputNotice)}
                      aria-describedby={visibleGenerationInputNotice ? "generation-input-notice" : undefined}
                      className={`${pendingHumanContext ? "min-h-[72px] sm:min-h-[96px]" : "min-h-[98px] sm:min-h-[104px]"} w-full resize-none border border-[#2c2f37] bg-[#0f1014] p-3 pr-14 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300 sm:p-4 sm:pr-16 sm:leading-7`}
                    />
                    <button
                      type="submit"
                      disabled={isLoading || !hasGenerationInput}
                      className="absolute bottom-3 right-3 inline-flex h-9 w-9 items-center justify-center bg-white text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40 sm:bottom-4 sm:right-4 sm:h-10 sm:w-10"
                      aria-label={generationInputValidation.isValid ? "Send build request" : "Check hardware idea"}
                      title={generationInputValidation.isValid ? "Send build request" : "Check hardware idea"}
                    >
                      {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                    </button>
                  </div>

                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="grid w-full grid-cols-[2.5rem_minmax(0,1fr)] gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center">
                      <input ref={fileInputRefCenter} type="file" accept="image/*" onChange={handleImageChange} className="hidden" />
                      <button
                        type="button"
                        onClick={() => fileInputRefCenter.current?.click()}
                        className="inline-flex h-10 w-10 items-center justify-center border border-[#2c2f37] text-slate-400 hover:bg-white hover:text-black"
                        title="Attach image"
                      >
                        <Paperclip className="h-4 w-4" />
                      </button>
                      <label
                        className="inline-flex h-10 cursor-pointer items-center justify-between gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase text-slate-400 hover:border-slate-500 hover:text-white sm:justify-start"
                        title="Use Firecrawl web research"
                      >
                        <input
                          type="checkbox"
                          checked={webResearchEnabled}
                          onChange={(event) => setGenerationWorkflow(event.target.checked ? WEB_RESEARCH_WORKFLOW_ID : DEFAULT_WORKFLOW_ID)}
                          disabled={isLoading}
                          className="peer sr-only"
                        />
                        <Sparkles className={`h-4 w-4 shrink-0 ${webResearchEnabled ? "text-cyan-300" : "text-slate-500"}`} />
                        <span>Web Research</span>
                        <span className={`h-4 w-7 border transition ${webResearchEnabled ? "border-cyan-300 bg-cyan-300" : "border-[#3a3d46] bg-black"}`}>
                          <span className={`block h-full w-3.5 bg-white transition ${webResearchEnabled ? "translate-x-3" : "translate-x-0"}`} />
                        </span>
                      </label>
                      <label className="col-span-2 inline-flex h-10 max-w-full items-center gap-2 border border-[#2c2f37] bg-[#17181d] px-3 text-xs font-black uppercase text-slate-400 sm:col-span-1">
                        <Cpu className="h-4 w-4 shrink-0 text-cyan-300" />
                        <select
                          value={generationLlmKeyValue}
                          onChange={(event) => setGenerationLlmKeyValue(event.target.value)}
                          disabled={isLoading}
                          className="min-w-0 flex-1 bg-transparent text-xs font-black uppercase text-white outline-none disabled:cursor-not-allowed disabled:opacity-50 sm:max-w-[220px]"
                          aria-label="Generation LLM"
                          title="Generation LLM"
                        >
                          {generationLlms.map((option) => (
                            <option key={generationLlmKey(option)} value={generationLlmKey(option)} className="bg-[#17181d] text-white">
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="col-span-2 inline-flex h-10 cursor-pointer items-center justify-between gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase text-slate-400 hover:border-slate-500 hover:text-white sm:col-span-1 sm:justify-start">
                        <input
                          type="checkbox"
                          checked={generateProductImage}
                          onChange={(event) => setGenerateProductImage(event.target.checked)}
                          className="peer sr-only"
                        />
                        <Sparkles className={`h-4 w-4 ${generateProductImage ? "text-cyan-300" : "text-slate-500"}`} />
                        <span>Images</span>
                        <span className={`h-4 w-7 border transition ${generateProductImage ? "border-cyan-300 bg-cyan-300" : "border-[#3a3d46] bg-black"}`}>
                          <span className={`block h-full w-3.5 bg-white transition ${generateProductImage ? "translate-x-3" : "translate-x-0"}`} />
                        </span>
                      </label>
                    </div>
                  </div>
                </form>
                {activeSidebarChatStarted && <div className="h-[276px] shrink-0 md:hidden" aria-hidden="true" />}

              </div>
            )}
          </section>
            </>
          )}
        </main>
          </div>
        </div>
      </div>
    );
  }

	  return (
	    <div className="h-[100dvh] w-full overflow-hidden bg-[#141519] text-slate-200">
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
		        showJobs={canViewJobs}
		        showDeveloperTools={showDeveloperTools}
	        authRequired={authRequired}
	        serverStatus={serverStatus}
	      />
	      <div className={`grid h-full min-h-0 min-w-0 overflow-hidden ${sidebarCollapsed ? "md:grid-cols-[72px_minmax(0,1fr)]" : "md:grid-cols-[320px_minmax(0,1fr)]"}`}>
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
          showJobs={canViewJobs}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
	        <div className="grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden">
	        <main className="flex min-h-0 min-w-0 flex-col">
	          <header className="flex min-h-[78px] min-w-0 items-center gap-2 overflow-hidden border-b border-[#282a30] bg-[#17181d] px-3 sm:gap-3 sm:px-4">
	            <MobileSidebarButton onClick={() => setMobileSidebarOpen(true)} />
	            <input ref={fileInputRefVideo} type="file" accept="image/*" onChange={handleVideoImageChange} className="hidden" />

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
        </div>
      </div>
    </div>
  );
}

export default BlueprintWorkspace;

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
    merged.set(item.chatId, item);
  });

  return Array.from(merged.values())
    .sort((left, right) => {
      const leftTime = Date.parse(left.createdAt || "");
      const rightTime = Date.parse(right.createdAt || "");
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    });
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
    if (item.chatId) merged.set(item.chatId, item);
  });
  return Array.from(merged.values());
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

function formatSidebarDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatProjectAge(value: string | null) {
  if (!value) return "";
  const createdAt = new Date(value).getTime();
  if (Number.isNaN(createdAt)) return "";
  const elapsedMs = Math.max(0, Date.now() - createdAt);
  const hours = Math.floor(elapsedMs / (60 * 60 * 1000));
  if (hours < 24) return hours <= 0 ? "Today" : `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 31) return days === 1 ? "1 day" : `${days} days`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month" : `${months} months`;
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

function MobileWorkspaceBar({
  onOpenSidebar,
  serverStatus = "disconnected",
  authRequired,
}: {
  onOpenSidebar: () => void;
  serverStatus?: "connected" | "disconnected";
  authRequired: boolean;
}) {
  const ApiStatusIcon = serverStatus === "connected" ? Wifi : WifiOff;
  const apiStatusLabel = serverStatus === "connected" ? "API connected" : "API disconnected";
  const apiStatusTone =
    serverStatus === "connected"
      ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
      : "border-orange-500/30 bg-orange-950/20 text-orange-300";

  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-12 shrink-0 items-center gap-3 border-b border-[#292b31] bg-[#141519] px-3 md:hidden">
      <MobileSidebarButton onClick={onOpenSidebar} />
      <div className="min-w-0 flex flex-1 items-center gap-2">
        <span className="truncate text-sm font-black uppercase tracking-[0.22em] text-white">Blueprint</span>
        <span className="border border-cyan-300/30 bg-cyan-300/10 px-1.5 py-0.5 text-[9px] font-black uppercase text-cyan-100">OSS</span>
      </div>
      <span
        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center border ${apiStatusTone}`}
        title={apiStatusLabel}
        aria-label={apiStatusLabel}
      >
        <ApiStatusIcon className="h-4 w-4" />
      </span>
      <AuthStatusControl authRequired={authRequired} compact />
    </header>
  );
}

function AuthStatusControl({
  authRequired,
  compact = false,
}: {
  authRequired: boolean;
  compact?: boolean;
}) {
  const { isLoaded, isSignedIn } = useAuth();
  const { openSignIn } = useClerk();
  if (!authRequired) return null;
  if (isSignedIn) return <UserButton afterSignOutUrl="/" />;

  return (
    <button
      type="button"
      disabled={!isLoaded}
      onClick={() => openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" })}
      className={`inline-flex shrink-0 items-center justify-center border border-cyan-300/30 bg-cyan-300/10 font-black uppercase text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-wait disabled:border-slate-700 disabled:text-slate-600 disabled:hover:bg-transparent disabled:hover:text-slate-600 ${
        compact ? "h-8 w-8" : "h-7 gap-1.5 px-2 text-[10px]"
      }`}
      aria-label={isLoaded ? "Sign in" : "Checking sign-in status"}
      title={isLoaded ? "Sign in" : "Checking sign-in status"}
    >
      <KeyRound className={compact ? "h-4 w-4" : "h-3.5 w-3.5"} />
      {!compact && <span>Sign in</span>}
    </button>
  );
}

function MobileSidebarButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-[#2c2f37] bg-black text-slate-200 transition hover:bg-white hover:text-black md:hidden"
      aria-label="Open sidebar"
      title="Open sidebar"
    >
      <Menu className="h-4 w-4" />
    </button>
  );
}

function MobileSidebarDrawer({
  open,
  onClose,
  collapsed,
  onToggle,
  onHome,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  waitingChatIds,
  showJobs,
  showDeveloperTools,
  authRequired,
  serverStatus,
}: {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggle: () => void;
  onHome: () => void;
  chats: ChatListItem[];
  activeChatId: string | null;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  waitingChatIds: Set<string>;
  showJobs: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  serverStatus: "connected" | "disconnected";
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Sidebar">
      <button
        type="button"
        className="absolute inset-0 h-full w-full bg-black/65"
        onClick={onClose}
        aria-label="Close sidebar"
      />
      <div className="relative h-full">
        <ChatSidebar
          mode="drawer"
          collapsed={collapsed}
          onToggle={onToggle}
          onClose={onClose}
          onNavigate={onClose}
          onHome={onHome}
          chats={chats}
          activeChatId={activeChatId}
          onNewChat={onNewChat}
          newChatDisabled={newChatDisabled}
          onOpenChat={onOpenChat}
          waitingChatIds={waitingChatIds}
          showJobs={showJobs}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
      </div>
    </div>
  );
}

function ChatSidebar({
  collapsed,
  onToggle,
  onClose,
  onNavigate,
  onHome,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  waitingChatIds,
  showJobs,
  showDeveloperTools,
  authRequired,
  serverStatus = "disconnected",
  mode = "desktop",
}: {
  collapsed: boolean;
  onToggle: () => void;
  onClose?: () => void;
  onNavigate?: () => void;
  onHome: () => void;
  chats: ChatListItem[];
  activeChatId: string | null;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  waitingChatIds: Set<string>;
  showJobs: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  serverStatus?: "connected" | "disconnected";
  mode?: "desktop" | "drawer";
}) {
  const isDrawer = mode === "drawer";
  const compact = !isDrawer && collapsed;
  const ApiStatusIcon = serverStatus === "connected" ? Wifi : WifiOff;
  const apiStatusLabel = serverStatus === "connected" ? "API connected" : "API disconnected";
  const apiStatusTone =
    serverStatus === "connected"
      ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
      : "border-orange-500/30 bg-orange-950/20 text-orange-300";

  return (
    <aside
      className={
        isDrawer
          ? "flex h-full min-h-0 w-[min(320px,calc(100vw-2rem))] flex-col border-r border-[#292b31] bg-[#141519] text-slate-100 shadow-2xl shadow-black/50"
          : "hidden h-full min-h-0 flex-col border-r border-[#292b31] bg-[#141519] text-slate-100 md:flex"
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className={`flex shrink-0 items-center border-b border-[#292b31] ${compact ? "h-20 flex-col justify-center gap-2 px-0" : "h-16 gap-3 px-4"}`}>
          <button
            type="button"
            onClick={() => {
              onHome();
              onNavigate?.();
            }}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-[#2c2f37] bg-black text-slate-200 transition hover:bg-white hover:text-black"
            aria-label="Home"
            title="Home"
          >
            <Cpu className="h-4 w-4" />
          </button>
          {!compact && (
            <div className="min-w-0 flex items-center gap-2">
              <span className="truncate text-sm font-black uppercase tracking-[0.22em] text-white">Blueprint</span>
              <span className="border border-cyan-300/30 bg-cyan-300/10 px-1.5 py-0.5 text-[9px] font-black uppercase text-cyan-100">OSS</span>
              <span
                className={`inline-flex h-7 w-7 shrink-0 items-center justify-center border ${apiStatusTone}`}
                title={apiStatusLabel}
                aria-label={apiStatusLabel}
              >
                <ApiStatusIcon className="h-3.5 w-3.5" />
              </span>
              <AuthStatusControl authRequired={authRequired} />
            </div>
          )}
          <button
            type="button"
            onClick={isDrawer ? onClose : onToggle}
            className={`${compact ? "h-7 w-7" : "ml-auto h-8 w-8"} inline-flex shrink-0 items-center justify-center border border-transparent text-slate-500 transition hover:border-[#2c2f37] hover:text-cyan-100`}
            aria-label={isDrawer ? "Close sidebar" : compact ? "Expand chat sidebar" : "Collapse chat sidebar"}
            title={isDrawer ? "Close sidebar" : compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isDrawer ? <X className="h-4 w-4" /> : compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        <div className="px-4 pb-4">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              if (!newChatDisabled) onNavigate?.();
            }}
            disabled={newChatDisabled}
            className={`group flex h-11 w-full items-center border text-sm font-semibold ${
              newChatDisabled
                ? "cursor-not-allowed border-[#242832] bg-[#101116] text-slate-600"
                : "border-[#2c2f37] bg-[#17181d] text-white hover:bg-white hover:text-black"
            } ${
              compact ? "justify-center px-0" : "gap-3 px-3"
            }`}
            aria-label="New chat"
            title={newChatDisabled ? "Send a message before starting another chat" : "New chat"}
          >
            <Plus className={`h-5 w-5 shrink-0 ${newChatDisabled ? "text-slate-700" : "text-slate-500 group-hover:text-black"}`} />
            {!compact && <span className="truncate">New chat</span>}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {!compact && <div className="mb-3 text-sm text-slate-500">Chats</div>}
          <div className="space-y-1">
            {chats.length ? (
              chats.map((chat) => {
                const active = chat.chatId === activeChatId;
                const dateLabel = formatSidebarDate(chat.createdAt);
                const waiting = waitingChatIds.has(chat.chatId);
                return (
                  <button
                    key={chat.chatId}
                    type="button"
                    onClick={() => {
                      onOpenChat(chat);
                      onNavigate?.();
                    }}
                    className={`flex w-full min-w-0 items-center gap-3 px-2 py-2 text-left text-sm transition ${
                      active ? "border border-cyan-300/25 bg-cyan-300/10 text-cyan-100" : "border border-transparent text-slate-100 hover:bg-[#17181d]"
                    } ${compact ? "justify-center" : ""}`}
                    title={waiting ? `${chat.title} is waiting` : chat.title}
                    aria-label={`Open chat ${chat.title}${waiting ? " (waiting)" : ""}`}
                  >
                    {compact ? (
                      waiting ? (
                        <RefreshCw className={`h-5 w-5 animate-spin ${active ? "text-cyan-300" : "text-slate-500"}`} />
                      ) : (
                        <MessageSquare className={`h-5 w-5 ${active ? "text-cyan-300" : "text-slate-500"}`} />
                      )
                    ) : (
                      <>
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-semibold">{chat.title}</div>
                          {chat.projectCount > 1 && (
                            <div className="mt-0.5 text-[11px] text-slate-600">{chat.projectCount} projects</div>
                          )}
                        </div>
                        {waiting && (
                          <RefreshCw className={`h-4 w-4 shrink-0 animate-spin ${active ? "text-cyan-300" : "text-slate-500"}`} />
                        )}
                        {dateLabel && <div className="shrink-0 text-xs text-slate-500">{dateLabel}</div>}
                      </>
                    )}
                  </button>
                );
              })
            ) : (
              !compact && <div className="px-2 py-2 text-xs leading-5 text-slate-500">No saved chats yet.</div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-[#292b31] px-4 py-5">
        {!compact && <div className="mb-3 text-sm text-slate-500">Workspace</div>}
        <div className="space-y-1">
          <Link
            href="/my-projects"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="My projects"
          >
            <Database className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">My projects</span>}
          </Link>
          <Link
            href="/projects"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="Projects"
          >
            <Layers className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">Projects</span>}
          </Link>
          {showJobs && (
            <Link
              href="/jobs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Jobs"
            >
              <History className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Jobs</span>}
            </Link>
          )}
          {showDeveloperTools && (
            <Link
              href="/backend-logs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Backend logs"
            >
              <Terminal className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Backend logs</span>}
            </Link>
          )}
          {showDeveloperTools && (
            <Link
              href="/listening-jobs"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="Listening jobs"
            >
              <Terminal className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Listening jobs</span>}
            </Link>
          )}
          {showDeveloperTools && (
            <Link
              href="/user"
              onClick={onNavigate}
              className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
              title="User integrations"
            >
              <KeyRound className="h-5 w-5 text-slate-500" />
              {!compact && <span className="truncate">Keys</span>}
            </Link>
          )}
          <Link
            href="/about"
            onClick={onNavigate}
            className={`flex h-10 items-center gap-3 px-2 text-sm font-semibold text-slate-100 hover:bg-[#17181d] hover:text-white ${compact ? "justify-center" : ""}`}
            title="About us"
          >
            <Handshake className="h-5 w-5 text-slate-500" />
            {!compact && <span className="truncate">About us</span>}
          </Link>
        </div>
      </div>
    </aside>
  );
}

function buildProjectGalleryItems(
  projectHistory: any[],
  projectImages: Record<string, ProjectImageCandidate | null>
): ProjectGalleryItem[] {
  return projectHistory
    .filter((project: any) => project?.project_id)
    .map((project: any) => {
      const projectId = String(project.project_id);
      const chatId = String(project.chat_id || projectId);
      return {
        key: projectId,
        title: project.title || "Untitled project",
        projectId,
        chatId,
        canChat: Boolean(project.can_chat ?? project.canChat),
        creatorDisplay:
          typeof project.creator_username === "string" && project.creator_username.trim()
            ? project.creator_username.trim()
            : typeof project.creator_display === "string" && project.creator_display.trim()
              ? project.creator_display.trim()
              : "unknown",
        creatorImageUrl:
          typeof project.creator_image_url === "string" && project.creator_image_url.trim()
            ? project.creator_image_url.trim()
            : typeof project.creatorImageUrl === "string" && project.creatorImageUrl.trim()
              ? project.creatorImageUrl.trim()
              : null,
        createdAt: typeof project.created_at === "string" && project.created_at ? project.created_at : null,
        partsCount: Math.max(0, Number(project.parts_count || project.partsCount || 0)),
        starCount: Math.max(0, Number(project.star_count || project.starCount || 0)),
        image: projectImages[projectId] || null,
      };
    });
}

function ProjectGallery({
  sectionRef,
  items,
  onOpenChat,
  onOpenProjectPage,
  standalone = false,
}: {
  sectionRef: React.RefObject<HTMLElement>;
  items: ProjectGalleryItem[];
  onOpenChat: (chatId: string) => void;
  onOpenProjectPage: (projectId: string) => void;
  standalone?: boolean;
}) {
  const pageSize = useProjectGalleryPageSize();
  const [currentPage, setCurrentPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(currentPage, pageCount - 1);
  const firstVisibleItem = safePage * pageSize;
  const visibleItems = items.slice(firstVisibleItem, firstVisibleItem + pageSize);
  const showingStart = items.length ? firstVisibleItem + 1 : 0;
  const showingEnd = Math.min(items.length, firstVisibleItem + visibleItems.length);
  const pageMarkers = buildProjectGalleryPageMarkers(safePage, pageCount);

  useEffect(() => {
    setCurrentPage(0);
  }, [items.length, pageSize]);

  useEffect(() => {
    if (safePage !== currentPage) {
      setCurrentPage(safePage);
    }
  }, [currentPage, safePage]);

  const goToPage = (page: number) => {
    setCurrentPage(Math.min(Math.max(page, 0), pageCount - 1));
  };

  return (
    <section ref={sectionRef} id="all-projects" className={standalone ? "" : "mt-16 border-t border-[#292b31] pt-12"}>
      <div className="mb-6 flex flex-col gap-3">
        <div>
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center border border-[#2c2f37] bg-black text-white">
              <Cpu className="h-4 w-4" />
            </span>
            <h2 className="text-2xl font-black uppercase tracking-[0.22em] text-white">Projects</h2>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-500">{items.length} saved projects.</p>
        </div>
      </div>

      {items.length ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {visibleItems.map((item) => (
              <ProjectGalleryCard
                key={item.key}
                item={item}
                onOpenChat={item.canChat ? () => onOpenChat(item.chatId) : undefined}
                onOpenProjectPage={() => onOpenProjectPage(item.projectId)}
              />
            ))}
          </div>

          {pageCount > 1 && (
            <div className="mt-5 flex flex-col gap-3 border border-[#2c2f37] bg-[#17181d] p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">
                Showing {showingStart}-{showingEnd} of {items.length}
              </div>

              <div className="grid grid-cols-[44px_minmax(0,1fr)_44px] gap-2 sm:flex sm:items-center">
                <button
                  type="button"
                  onClick={() => goToPage(safePage - 1)}
                  disabled={safePage === 0}
                  className="inline-flex h-10 w-11 items-center justify-center border border-[#2a2c33] text-white transition hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-white"
                  aria-label="Previous projects page"
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>

                <div className="hidden items-center gap-2 sm:flex">
                  {pageMarkers.map((marker, index) => (
                    marker === "gap" ? (
                      <span
                        key={`gap-${index}`}
                        className="flex h-10 min-w-7 items-center justify-center text-xs font-black text-slate-600"
                      >
                        ...
                      </span>
                    ) : (
                      <button
                        key={marker}
                        type="button"
                        onClick={() => goToPage(marker)}
                        aria-current={marker === safePage ? "page" : undefined}
                        className={`h-10 min-w-10 border px-3 text-xs font-black uppercase transition ${
                          marker === safePage
                            ? "border-white bg-white text-black"
                            : "border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
                        }`}
                      >
                        {marker + 1}
                      </button>
                    )
                  ))}
                </div>

                <div className="flex h-10 items-center justify-center border border-[#2a2c33] text-xs font-black uppercase tracking-[0.14em] text-slate-400 sm:hidden">
                  Page {safePage + 1} / {pageCount}
                </div>

                <button
                  type="button"
                  onClick={() => goToPage(safePage + 1)}
                  disabled={safePage >= pageCount - 1}
                  className="inline-flex h-10 w-11 items-center justify-center border border-[#2a2c33] text-white transition hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-white"
                  aria-label="Next projects page"
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="border border-[#2c2f37] bg-[#17181d] p-8 text-sm leading-6 text-slate-500">
          No saved projects yet.
        </div>
      )}
    </section>
  );
}

function buildProjectGalleryPageMarkers(currentPage: number, pageCount: number): Array<number | "gap"> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => index);
  }

  const markers = new Set([0, pageCount - 1, currentPage]);

  if (currentPage > 0) {
    markers.add(currentPage - 1);
  }

  if (currentPage < pageCount - 1) {
    markers.add(currentPage + 1);
  }

  const sortedMarkers = Array.from(markers).sort((a, b) => a - b);
  return sortedMarkers.flatMap((marker, index) => {
    const previousMarker = sortedMarkers[index - 1];
    return index > 0 && marker - previousMarker > 1 ? ["gap", marker] : [marker];
  });
}

function useProjectGalleryPageSize() {
  const [pageSize, setPageSize] = useState<number>(PROJECT_GALLERY_PAGE_SIZES.mobile);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 1280px)");
    const tabletQuery = window.matchMedia("(min-width: 640px)");

    const updatePageSize = () => {
      if (desktopQuery.matches) {
        setPageSize(PROJECT_GALLERY_PAGE_SIZES.desktop);
      } else if (tabletQuery.matches) {
        setPageSize(PROJECT_GALLERY_PAGE_SIZES.tablet);
      } else {
        setPageSize(PROJECT_GALLERY_PAGE_SIZES.mobile);
      }
    };

    updatePageSize();
    desktopQuery.addEventListener("change", updatePageSize);
    tabletQuery.addEventListener("change", updatePageSize);

    return () => {
      desktopQuery.removeEventListener("change", updatePageSize);
      tabletQuery.removeEventListener("change", updatePageSize);
    };
  }, []);

  return pageSize;
}

function ProjectGalleryCard({
  item,
  onOpenChat,
  onOpenProjectPage,
}: {
  item: ProjectGalleryItem;
  onOpenChat?: () => void;
  onOpenProjectPage: () => void;
}) {
  const ageLabel = formatProjectAge(item.createdAt);
  return (
    <article
      role="link"
      tabIndex={0}
      onClick={onOpenProjectPage}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpenProjectPage();
        }
      }}
      className="group cursor-pointer overflow-hidden border border-[#2c2f37] bg-[#17181d] outline-none transition hover:border-cyan-300/35 focus-visible:border-cyan-300"
      aria-label={`Open project ${item.title}`}
    >
      <div className="aspect-square overflow-hidden border-b border-[#2c2f37] bg-[#0f1014] sm:aspect-[4/3]">
        {item.image ? (
          <img
            src={item.image.src}
            alt={`${item.title} preview`}
            className="h-full w-full object-contain p-2 transition duration-300 group-hover:scale-[1.015] sm:object-cover sm:p-0"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs font-black uppercase tracking-[0.18em] text-slate-600">
            No image
          </div>
        )}
      </div>

      <div className="flex min-h-[150px] flex-col justify-between gap-3 p-4">
        <h3 className="line-clamp-2 min-h-10 break-words text-sm font-black uppercase leading-5 tracking-[0.08em] text-white">
          {item.title}
        </h3>
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 text-sm font-bold text-slate-500">
          <span className="whitespace-nowrap">{item.partsCount} parts</span>
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-amber-300">
            <Star className="h-3.5 w-3.5 fill-current" />
            {item.starCount}
          </span>
          {ageLabel && (
            <span className="inline-flex items-center gap-1 whitespace-nowrap">
              <Clock3 className="h-3.5 w-3.5" />
              {ageLabel}
            </span>
          )}
        </div>
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-bold text-slate-500">
            {item.creatorImageUrl ? (
              <img
                src={item.creatorImageUrl}
                alt=""
                className="h-5 w-5 shrink-0 border border-[#2c2f37] object-cover"
              />
            ) : (
              <span className="h-3.5 w-3.5 shrink-0 border border-emerald-300 bg-emerald-400 shadow-[inset_6px_0_0_#f472b6]" />
            )}
            <span className="truncate">{item.creatorDisplay}</span>
          </div>
          {item.canChat && onOpenChat && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onOpenChat();
              }}
              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 border border-cyan-300/35 px-3 text-xs font-black uppercase text-cyan-100 transition hover:bg-cyan-300 hover:text-black"
            >
              <MessageSquare className="h-4 w-4 shrink-0" />
              <span className="truncate">Chat</span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

function ProjectRouteFallback({
  projectId,
  error,
  onHome,
}: {
  projectId: string;
  error: string | null;
  onHome: () => void;
}) {
  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-[#141519] font-sans text-slate-100">
      <header className="border-b border-[#292b31] bg-[#141519]/95">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-5 py-4">
          <button type="button" onClick={onHome} className="min-w-0 text-left">
            <span className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center border border-[#2c2f37] bg-black text-white">
                <Cpu className="h-4 w-4" />
              </span>
              <span className="hidden text-sm font-black uppercase tracking-[0.22em] text-white sm:block">Blueprint</span>
            </span>
          </button>
        </div>
      </header>

      <main className="mx-auto flex min-h-[calc(100vh-73px)] w-full max-w-6xl items-center justify-center px-5 py-12">
        <section className="w-full max-w-md border border-[#2c2f37] bg-[#17181d] p-6 text-center shadow-2xl shadow-black/30">
          <div className="mx-auto flex h-11 w-11 items-center justify-center border border-[#2c2f37] bg-black text-white">
            {error ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <RefreshCw className="h-5 w-5 animate-spin" />}
          </div>
          <h1 className="mt-5 text-lg font-black uppercase tracking-[0.18em] text-white">
            {error ? "Project unavailable" : "Opening project"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            {error || "Loading the saved hardware plan."}
          </p>
          <div className="mt-4 truncate border border-[#2c2f37] bg-[#141519] px-3 py-2 text-xs font-mono text-slate-500">
            {projectId}
          </div>
          {error && (
            <button
              type="button"
              onClick={onHome}
              className="mt-5 inline-flex h-10 items-center gap-2 border border-[#2a2c33] px-4 text-xs font-black uppercase text-white transition hover:bg-white hover:text-black"
            >
              <ArrowLeft className="h-4 w-4" />
              Back home
            </button>
          )}
        </section>
      </main>
    </div>
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
          <SignInButton mode="modal">
            <button
              type="button"
              disabled={loading}
              className="inline-flex h-10 items-center justify-center border border-cyan-300/35 px-3 text-xs font-black uppercase text-cyan-100 transition hover:bg-cyan-300 hover:text-black disabled:cursor-wait disabled:border-slate-700 disabled:text-slate-600 disabled:hover:bg-transparent disabled:hover:text-slate-600"
            >
              Sign in
            </button>
          </SignInButton>
        </div>
      </div>
    </div>
  );
}

function ChatRouteFallback({
  collapsed,
  onToggle,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  waitingChatIds,
  showJobs,
  showDeveloperTools,
  authRequired,
  serverStatus,
  transition,
  onHome,
}: {
  collapsed: boolean;
  onToggle: () => void;
  chats: ChatListItem[];
  activeChatId: string;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  waitingChatIds: Set<string>;
  showJobs: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  serverStatus: "connected" | "disconnected";
  transition: ChatRouteTransition;
  onHome: () => void;
}) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const hasProjectTarget = Boolean(transition.projectId);
  return (
    <div className="h-[100dvh] w-full overflow-hidden bg-[#141519] text-slate-200">
      <MobileSidebarDrawer
        open={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
        collapsed={collapsed}
        onToggle={onToggle}
        onHome={onHome}
        chats={chats}
        activeChatId={activeChatId}
        onNewChat={onNewChat}
        newChatDisabled={newChatDisabled}
        onOpenChat={onOpenChat}
        waitingChatIds={waitingChatIds}
        showJobs={showJobs}
        showDeveloperTools={showDeveloperTools}
        authRequired={authRequired}
        serverStatus={serverStatus}
      />
      <div className={`grid h-full min-h-0 min-w-0 overflow-hidden ${collapsed ? "md:grid-cols-[72px_minmax(0,1fr)]" : "md:grid-cols-[320px_minmax(0,1fr)]"}`}>
        <ChatSidebar
          collapsed={collapsed}
          onToggle={onToggle}
          onHome={onHome}
          chats={chats}
          activeChatId={activeChatId}
          onNewChat={onNewChat}
          newChatDisabled={newChatDisabled}
          onOpenChat={onOpenChat}
          waitingChatIds={waitingChatIds}
          showJobs={showJobs}
          showDeveloperTools={showDeveloperTools}
          authRequired={authRequired}
          serverStatus={serverStatus}
        />
        <main className="flex min-h-0 min-w-0 flex-col">
          <header className="flex min-h-[78px] min-w-0 items-center gap-2 overflow-hidden border-b border-[#282a30] bg-[#17181d] px-3 sm:gap-3 sm:px-4">
            <MobileSidebarButton onClick={() => setMobileSidebarOpen(true)} />
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
      </div>
    </div>
  );
}

function SchematicLegend() {
  const wireRows = [
    { label: "VCC", color: "#ef4444", dash: "none" },
    { label: "GND", color: "#64748b", dash: "none" },
    { label: "I2C", color: "#0ea5e9", dash: "none" },
    { label: "DATA", color: "#8b5cf6", dash: "none" },
    { label: "PWM", color: "#f97316", dash: "none" },
  ];

  return (
    <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-[calc(100%-2rem)] border border-[#30343d] bg-[#15161b]/90 px-3 py-2 shadow-[0_16px_36px_rgba(0,0,0,0.28)] backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <div className="mr-1 text-[9px] font-black uppercase tracking-[0.18em] text-slate-500">Wires</div>
        {wireRows.map((wire) => (
          <div key={wire.label} className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.08em]" style={{ color: wire.color }}>
            <svg width="24" height="8" viewBox="0 0 40 8" aria-hidden="true">
              <line x1="0" y1="4" x2="40" y2="4" stroke={wire.color} strokeWidth="3" strokeDasharray={wire.dash} />
            </svg>
            <span>{wire.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function OverviewPanel({
  title,
  description,
  imageCandidates,
  features,
  metrics,
  metadata,
}: {
  title: string;
  description: string;
  imageCandidates: ProjectImageCandidate[];
  features: string[];
  metrics: ReturnType<typeof emptyMetrics>;
  metadata: Record<string, any>;
}) {
  const imageKey = imageCandidates.map((candidate) => candidate.src).join("|");
  const [imageIndex, setImageIndex] = useState(0);

  useEffect(() => {
    setImageIndex(0);
  }, [imageKey]);

  const activeImage = imageCandidates[imageIndex] || null;
  const llmProvider = metadata.runtime_provider || metadata.llm_provider || metadata.requested_provider;
  const llmModel = metadata.runtime_model || metadata.actual_model || metadata.model_name || metadata.requested_model;

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] px-4 py-6 sm:px-5 sm:py-8">
      <div className="mx-auto min-w-0 max-w-[890px]">
        <div className="relative border border-[#2a2c33] bg-[#d5d5d3]">
          {activeImage ? (
            <img
              src={activeImage.src}
              alt={activeImage.label}
              onError={() => setImageIndex((current) => current + 1)}
              className="h-[320px] w-full object-contain sm:h-[440px]"
            />
          ) : (
            <ProductRender product={metadata.product_visual} />
          )}
          <button className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-blue-600 shadow-lg" title={activeImage ? activeImage.label : "Generated visual reference"}>
            <Eye className="h-5 w-5" />
          </button>
          {activeImage && (
            <div className="absolute left-4 top-4 max-w-[calc(100%-6.5rem)] border border-black/10 bg-white/90 px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#202127] shadow-lg">
              {activeImage.label}
            </div>
          )}
        </div>

        {imageCandidates.length > 1 && (
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {imageCandidates.slice(0, 3).map((candidate, index) => (
              <button
                key={`${candidate.src}-${index}`}
                type="button"
                onClick={() => setImageIndex(index)}
                className={`min-w-0 border p-2 text-left transition ${
                  imageIndex === index ? "border-white bg-white text-black" : "border-[#2a2c33] bg-[#17181d] text-slate-400 hover:border-slate-500 hover:text-white"
                }`}
              >
                <img src={candidate.src} alt={candidate.label} className="h-20 w-full bg-black object-cover" />
                <div className="mt-2 truncate text-[10px] font-black uppercase tracking-[0.14em]">{candidate.label}</div>
              </button>
            ))}
          </div>
        )}

        <div className="mt-6 min-w-0 border-t border-[#282a30] px-2 py-6 sm:px-8 sm:py-8">
          <h1 className="break-words text-xl font-black uppercase tracking-[0.12em] text-white sm:text-2xl sm:tracking-[0.18em]">{title}</h1>
          <div className="mt-5 flex flex-wrap gap-2">
            {metadata.workflow && (
              <span className="max-w-full break-words border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-cyan-200 sm:tracking-[0.16em]">
                {metadata.workflow}
              </span>
            )}
            {llmProvider && llmModel && (
              <span className="max-w-full break-words border border-violet-300/30 bg-violet-300/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-violet-100 sm:tracking-[0.16em]">
                {projectLlmDisplayLabel(llmProvider, llmModel)}
              </span>
            )}
            {features.slice(0, 12).map((feature, index) => (
              <span key={`${feature}-${index}`} className="max-w-full break-words border border-[#333640] px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-slate-400 sm:tracking-[0.16em]">
                {String(feature).split(":")[0]}
              </span>
            ))}
          </div>

          <div className="mt-7">
            <div className="text-[11px] font-black uppercase tracking-[0.22em] text-slate-500">Technical Description</div>
            <p className="mt-4 max-w-3xl break-words text-base leading-8 text-slate-300">{description}</p>
          </div>

          <div className="mt-7 max-w-2xl border border-[#2a2c33]">
            <div className="grid grid-cols-3 border-b border-[#2a2c33] px-4 py-3 text-[12px] font-black uppercase tracking-[0.18em] text-slate-500">
              <span>Category</span>
              <span className="text-center">Parts</span>
              <span className="text-right">Cost</span>
            </div>
            <SummaryRow label="Electrical" parts={metrics.electricalParts} cost={metrics.electricalCost} />
            <SummaryRow label="Mechanical" parts={metrics.mechanicalParts} cost={metrics.mechanicalCost} />
            <SummaryRow label="Total" parts={metrics.totalParts} cost={metrics.totalCost} strong />
          </div>
        </div>
      </div>
    </div>
  );
}

function BomPanel({
  components,
  metrics,
  cadSources = [],
  fabricationCost = 0,
  canDownloadAssets = false,
}: {
  components: any[];
  metrics: ReturnType<typeof emptyMetrics>;
  cadSources?: any[];
  fabricationCost?: number;
  canDownloadAssets?: boolean;
}) {
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-5">
      <div className="space-y-3 lg:hidden">
        {components.map((component) => {
          const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
          const Icon = iconForCategory(component.category);
          const subtotal = (component.unit_price || 0) * (component.quantity || 1);

          return (
            <article key={component.ref_des} className="border border-[#2a2c33] bg-[#17181d] p-4">
              <div className="flex min-w-0 items-start gap-3">
                <span className={`flex h-11 w-11 shrink-0 items-center justify-center border ${tone.border} ${tone.bg}`}>
                  <Icon className={`h-5 w-5 ${tone.text}`} />
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="break-words text-sm font-black text-white">{component.name}</h3>
                  <p className="mt-2 break-words text-xs leading-5 text-slate-500">{component.rationale}</p>
                  <CategoryBadge category={component.category} />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Qty</div>
                  <div className="mt-1 font-bold text-slate-200">{component.quantity}</div>
                </div>
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2 text-right">
                  <div className="font-black uppercase text-slate-600">Subtotal</div>
                  <div className="mt-1 font-black text-white">~${subtotal.toFixed(2)}</div>
                </div>
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Unit</div>
                  <div className="mt-1 font-bold text-slate-200">~${Number(component.unit_price || 0).toFixed(2)}</div>
                </div>
                <div className="min-w-0 border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Source</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {getSourcesForComponent(component).map((source) => (
                      <ComponentSourceAction
                        key={`${source.label}-${source.href}`}
                        source={source}
                        component={component}
                        canDownloadAssets={canDownloadAssets}
                        className="inline-flex justify-center px-2 py-1 text-[10px]"
                      />
                    ))}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto border border-[#2a2c33] lg:block">
        <div className="min-w-[980px]">
          <div className="grid grid-cols-[minmax(420px,1fr)_110px_110px_150px_140px] border-b border-[#f5f5f5] px-5 py-5 text-sm font-black uppercase tracking-widest text-white">
            <span>Part</span>
            <span className="text-center">Qty</span>
            <span>Unit</span>
            <span>Source</span>
            <span className="text-right">Subtotal</span>
          </div>
          <div className="divide-y divide-[#282a30]">
            {components.map((component) => (
              <div key={component.ref_des} className="grid grid-cols-[minmax(420px,1fr)_110px_110px_150px_140px] items-center px-5 py-6">
                <div className="flex items-start gap-4">
                  <PartThumb component={component} />
                  <div className="min-w-0">
                    <h3 className="text-lg font-black text-white">{component.name}</h3>
                    <div className="mt-2 text-sm text-slate-500">{component.category}</div>
                    <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">{component.rationale}</p>
                    <CategoryBadge category={component.category} />
                  </div>
                </div>
                <div className="text-center text-base text-slate-200">{component.quantity}</div>
                <div className="text-base text-slate-200">~${Number(component.unit_price || 0).toFixed(2)}</div>
                <div className="flex flex-col items-start gap-2">
                  {getSourcesForComponent(component).map((source) => (
                    <ComponentSourceAction
                      key={`${source.label}-${source.href}`}
                      source={source}
                      component={component}
                      canDownloadAssets={canDownloadAssets}
                      className="inline-flex min-w-[86px] justify-center px-3 py-2 text-xs"
                    />
                  ))}
                </div>
                <div className="text-right text-lg font-black text-white">~${((component.unit_price || 0) * (component.quantity || 1)).toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-2 border border-[#2a2c33] px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-6">
        <span className="text-sm font-black uppercase tracking-[0.16em] text-slate-400 sm:tracking-[0.22em]">Total Estimated Cost</span>
        <span className="text-2xl font-black text-white sm:text-3xl">~${metrics.totalCost.toFixed(2)}</span>
      </div>

      <div className="mt-5 border border-[#2a2c33] p-4">
        <div className="flex items-start justify-between gap-4 border-b border-[#333640] pb-3">
          <div>
            <h2 className="text-sm font-black uppercase tracking-widest text-white">CAD Sources</h2>
            <div className="mt-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">3D Printed</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Mech Cost</div>
            <div className="mt-1 text-lg font-black text-white">~${fabricationCost.toFixed(2)}</div>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {!canDownloadAssets ? (
            <div className="border border-[#2a2c33] bg-[#141519] p-3 text-xs leading-6 text-slate-500">
              Files are available only on projects you generated.
            </div>
          ) : cadSources.length ? cadSources.slice(0, 3).map((source: any) => (
            <a
              key={`${source.name}-${source.url}`}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="block border border-[#2a2c33] bg-[#141519] p-3 hover:border-cyan-400/60"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-words text-xs font-black uppercase tracking-[0.12em] text-white sm:tracking-[0.14em]">{source.name}</div>
                  <div className="mt-2 break-words text-[10px] font-black uppercase tracking-[0.12em] text-cyan-300 sm:tracking-[0.16em]">{source.source_type || "CAD"} / ${(Number(source.estimated_unit_price_usd || 0)).toFixed(2)}</div>
                </div>
                <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
              </div>
              {source.file_formats?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {source.file_formats.map((format: string) => (
                    <span key={format} className="border border-[#333640] px-2 py-1 text-[10px] font-black uppercase text-slate-500">{format}</span>
                  ))}
                </div>
              )}
            </a>
          )) : (
            <div className="border border-[#2a2c33] bg-[#141519] p-3 text-xs leading-6 text-slate-500">
              No CAD source records attached.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ComponentSourceAction({
  source,
  component,
  canDownloadAssets,
  className = "",
}: {
  source: { label: string; className: string; href: string; title: string };
  component: any;
  canDownloadAssets: boolean;
  className?: string;
}) {
  const isFabricationAsset = source.label.toLowerCase() === "fabricate";
  const baseClass = `${className} font-black italic transition focus:outline-none focus:ring-2 focus:ring-cyan-300`;
  if (isFabricationAsset && !canDownloadAssets) {
    return (
      <span
        title="Files are available only on projects you generated."
        className={`${baseClass} cursor-not-allowed border border-[#2a2c33] bg-[#111216] text-slate-600`}
      >
        {source.label}
      </span>
    );
  }

  return (
    <a
      href={source.href}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open ${source.label} source for ${component.name || component.part_number || "component"}`}
      title={source.title}
      className={`${baseClass} ${source.className} text-black hover:-translate-y-0.5 hover:brightness-110`}
    >
      {source.label}
    </a>
  );
}

function MechanicalPanel({
  toggles,
  setToggles,
  electricalActive,
  setElectricalActive,
  components,
  features,
  metadata,
  mechanical,
}: {
  toggles: Record<string, boolean>;
  setToggles: (value: any) => void;
  electricalActive: boolean;
  setElectricalActive: (value: boolean) => void;
  components: any[];
  features: string[];
  metadata: Record<string, any>;
  mechanical: Record<string, any>;
}) {
  const visualSpec = metadata.product_visual_spec || {};
  const dimensions = mechanical.render_dimensions || visualSpec.external_dimensions_mm || metadata.render_dimensions || { x_mm: 100, y_mm: 60, z_mm: 36 };
  const placements = mechanical.component_placements || metadata.component_placements || [];
  const relationships = mechanical.spatial_relationships || metadata.spatial_relationships || [];
  const cadSources = Array.isArray(mechanical.cad_sources) ? mechanical.cad_sources : [];
  const fabricationCost = Number(mechanical.fabrication_cost_estimate_usd || 0);

  return (
    <div className="relative h-full overflow-hidden bg-[#141519]">
      <div className="absolute left-6 top-1/2 z-20 w-36 -translate-y-1/2 border border-[#4b4d56] bg-[#17181d]/80 p-4">
        <h2 className="border-b border-slate-400 pb-3 text-sm font-black uppercase tracking-widest text-white">3D CAD</h2>
        <button
          type="button"
          onClick={() => setElectricalActive(!electricalActive)}
          className={`mt-3 flex w-full items-center gap-2 border-b border-slate-500 pb-3 text-left text-xs font-black uppercase ${
            electricalActive ? "text-cyan-400" : "text-slate-700"
          }`}
        >
          <Cpu className="h-3 w-3" />
          Electrical
        </button>
        <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-slate-500">Mechanical</div>
        <div className="mt-2 space-y-2">
          {Object.entries(toggles).map(([key, value]) => (
            <button
              key={key}
              type="button"
              onClick={() => setToggles({ ...toggles, [key]: !value })}
              aria-pressed={value}
              className={`flex items-center gap-2 text-xs font-black uppercase ${
                value ? layerColor(key) : "text-slate-700"
              }`}
            >
              {key === "bodyRotation" ? <RefreshCw className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              {mechanicalToggleLabel(key)}
            </button>
          ))}
        </div>
      </div>

      

      <div className="relative z-10 flex h-full items-center justify-center px-8">
        <div className="relative h-[610px] w-[900px] max-w-full">
          <MechanicalScene
            dimensions={dimensions}
            components={components}
            placements={placements}
            relationships={relationships}
            features={features}
            toggles={toggles}
            electricalActive={electricalActive}
          />
        </div>
      </div>
    </div>
  );
}

function AssemblyPanel({
  assembly,
  issues,
  onDownload,
  canDownloadAssets,
}: {
  assembly: any[];
  issues: any[];
  onDownload: () => void;
  canDownloadAssets: boolean;
}) {
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 border-b border-[#2a2c33] pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-black uppercase tracking-[0.12em] text-white sm:text-xl sm:tracking-[0.18em]">Build Instructions</h2>
          <p className="mt-2 text-xs text-slate-500">Sequential assembly from the generated hardware graph.</p>
        </div>
        <button
          onClick={onDownload}
          disabled={!canDownloadAssets}
          title={canDownloadAssets ? "Export project JSON" : "Files are available only on projects you generated."}
          className="flex shrink-0 items-center justify-center gap-2 border border-[#2a2c33] px-4 py-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-white"
        >
          <Download className="h-4 w-4" />
          Export
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          {assembly.map((step) => (
            <section key={step.step_num} className="border border-[#2a2c33] bg-[#17181d] p-5">
              <div className="flex gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center bg-white text-sm font-black text-black">
                  {step.step_num}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-black text-white">{step.title}</h3>
                  <p className="mt-3 break-words text-sm leading-7 text-slate-400">{step.description}</p>
                  {step.danger_flag && (
                    <div className="mt-4 flex gap-2 border border-rose-500/30 bg-rose-950/25 p-3 text-sm leading-6 text-rose-300">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="min-w-0 break-words">{step.danger_message || "Pay close attention to safety constraints during this stage."}</span>
                    </div>
                  )}
                  {step.affected_components?.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {step.affected_components.map((part: string) => (
                        <span key={part} className="border border-[#2a2c33] px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                          {part}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </section>
          ))}
        </div>

        <div className="min-w-0 border border-[#2a2c33] bg-[#17181d] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-black uppercase tracking-widest text-white">Safety Audit</h3>
          </div>
          {issues.length ? (
            <div className="space-y-3">
              {issues.map((issue, index) => (
                <div key={`${issue.description}-${index}`} className="border border-[#2a2c33] bg-[#141519] p-3">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">{issue.severity} / {issue.category}</div>
                  <p className="mt-2 break-words text-xs leading-6 text-slate-400">{issue.description}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="border border-emerald-500/30 bg-emerald-950/25 p-4 text-xs leading-6 text-emerald-300">
              All electrical nets validated safely.
            </div>
          )}
        </div>
      </div>
    </div>
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
                              : isSystem
                                ? "border-[#2a2c33] bg-black/25 text-slate-400"
                                : "border-[#2a2c33] bg-[#17181d] text-slate-200"
                        }`}
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                          <span>{isUser ? "You" : isSystem ? "Context" : "Blueprint"}</span>
                          <span className="text-slate-700">/</span>
                          <span suppressHydrationWarning>{formatChatTimestamp(message.timestamp)}</span>
                          {message.status === "loading" && <RefreshCw className="h-3 w-3 animate-spin text-cyan-300" />}
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
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={`Ask about ${activeNamespaceLabel.toLowerCase()}...`}
                  className="min-h-[92px] w-full resize-none border border-[#2c2f37] bg-[#0f1014] p-4 pr-16 text-sm leading-7 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300"
                />
                <button
                  type="submit"
                  disabled={isLoading || !projectId || !input.trim()}
                  className="absolute bottom-4 right-4 inline-flex h-10 w-10 items-center justify-center bg-white text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Generate project from chat"
                  title={`Generate project from ${activeNamespaceName}`}
                >
                  {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
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
  const hasFailedEvent = events.some((event) => isFailedPipelineStatus(event.status));
  const isError = status === "error" || hasFailedEvent;
  const waitingForFirstEvent = isLoading && !events.length && startedMs !== null && nowMs - startedMs >= PIPELINE_STALE_AFTER_MS;
  const backendQuiet = isLoading && quietMs !== null && quietMs >= PIPELINE_STALE_AFTER_MS;
  const completedCount = completedPipelineStepCount({ ...progress, steps });
  const progressPercent = Math.min(100, Math.max(6, Math.round((completedCount / Math.max(steps.length, 1)) * 100)));
  const visibleEvents = events.slice(compact ? -4 : -6);
  const signalLabel = isError
    ? "error"
    : progress.synced
    ? backendQuiet
      ? "backend quiet"
      : "backend synced"
    : waitingForFirstEvent
      ? "waiting for job event"
      : "estimated";
  const signalTone = isError
    ? "border-rose-400/35 bg-rose-950/25 text-rose-200"
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
              {isError ? <AlertTriangle className="h-3 w-3" /> : isLoading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
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
        <div className={`h-full ${isError ? "bg-rose-300" : backendQuiet || waitingForFirstEvent ? "bg-amber-300" : "bg-cyan-300"}`} style={{ width: `${progressPercent}%` }} />
      </div>

      <div className="mt-3 flex min-w-0 items-start gap-2 border border-[#25272e] bg-[#111216] p-3">
        {isError ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" /> : isLoading ? <RefreshCw className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-cyan-300" /> : <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0">
          <div className="truncate text-xs font-black uppercase text-white">{activeStep?.label || "Preparing job"}</div>
          <div className="mt-1 truncate text-[11px] font-bold text-cyan-200">{activeStep?.agent || "Blueprint runtime"}</div>
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

function ChatNamespaceSummaryPanel({
  projectId,
  title,
  description,
  namespace,
  totalGenerationTime,
  components,
  metrics,
  issues,
}: {
  projectId: string | null;
  title: string;
  description: string;
  namespace: string;
  totalGenerationTime: string;
  components: any[];
  metrics: ReturnType<typeof emptyMetrics>;
  issues: any[];
}) {
  const topComponents = components.slice(0, 8);
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <section className="border border-[#2a2c33] bg-[#17181d] p-4 sm:p-5">
        <div className="flex flex-col gap-3 border-b border-[#2a2c33] pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-cyan-300" />
              <h2 className="truncate text-sm font-black uppercase tracking-[0.16em] text-white">Info</h2>
            </div>
            <p className="mt-2 break-words text-sm leading-6 text-slate-400">{description}</p>
          </div>
          <div className="shrink-0 border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 font-mono text-[11px] text-cyan-100">
            {namespace}
          </div>
        </div>

        <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-2 xl:grid-cols-5">
          <JobMetric label="Project" value={projectId || "-"} />
          <JobMetric label="Title" value={title} />
          <JobMetric label="Parts" value={metrics.totalParts} />
          <JobMetric label="Total Generation Time" value={totalGenerationTime} />
          <JobMetric label="Validation" value={issues.length ? `${issues.length} issues` : "approved"} />
        </div>

        <div className="mt-5 border border-[#2a2c33] bg-[#141519] p-4">
          <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Project Components</div>
          {topComponents.length ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {topComponents.map((component, index) => {
                const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
                const Icon = iconForCategory(component.category);
                return (
                  <div key={`${component.ref_des || component.name}-${index}`} className="flex min-w-0 items-center gap-2 border border-[#25272e] bg-black/20 px-3 py-2">
                    <Icon className={`h-4 w-4 shrink-0 ${tone.text}`} />
                    <span className="truncate text-xs font-bold text-slate-300">{component.ref_des ? `${component.ref_des} ` : ""}{component.name || component.part_number || "Component"}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="mt-3 border border-[#25272e] bg-black/20 p-3 text-xs leading-5 text-slate-500">
              No components attached to this project yet.
            </div>
          )}
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Electrical</div>
            <div className="mt-2 text-xl font-black text-white">{metrics.electricalParts}</div>
            <div className="mt-1 text-xs text-slate-500">~${metrics.electricalCost.toFixed(2)}</div>
          </div>
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Mechanical</div>
            <div className="mt-2 text-xl font-black text-white">{metrics.mechanicalParts}</div>
            <div className="mt-1 text-xs text-slate-500">~${metrics.mechanicalCost.toFixed(2)}</div>
          </div>
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Total Cost</div>
            <div className="mt-2 text-xl font-black text-white">~${metrics.totalCost.toFixed(2)}</div>
            <div className="mt-1 text-xs text-slate-500">{metrics.totalParts} parts</div>
          </div>
        </div>
      </section>
    </div>
  );
}

function LogsPanel({
  logs,
  loading,
  error,
  lastUpdatedAt,
  onRefresh,
  pollIntervalMs = LOG_POLL_INTERVAL_MS,
  compact = false,
}: {
  logs: BackendLogs | null;
  loading: boolean;
  error: string | null;
  lastUpdatedAt: string | null;
  onRefresh: () => void;
  pollIntervalMs?: number;
  compact?: boolean;
}) {
  const lines = Array.isArray(logs?.lines) ? logs.lines : [];
  const visibleLines = compact ? lines.slice(-10) : lines;
  const enabled = logs?.enabled !== false;
  const message = logs?.message || (enabled ? null : "Backend logging is not enabled.");

  return (
    <div className={`min-w-0 overflow-x-hidden ${compact ? "border border-[#2c2f37] bg-[#17181d] p-4" : "h-full min-h-0 overflow-hidden bg-[#141519] p-4 sm:p-6"}`}>
      <div className={`${compact ? "mb-3 pb-3" : "mb-4 pb-4"} flex items-start justify-between gap-4 border-b border-[#2a2c33]`}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-black uppercase text-white">Backend Logs</h2>
          </div>
          {!compact && (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Showing recent backend and uvicorn log lines. Polling every {Math.round(pollIntervalMs / 1000)}s while this tab is open.
            </p>
          )}
          {lastUpdatedAt && (
            <p className="mt-1 text-[11px] leading-5 text-slate-600">Updated {formatJobTime(lastUpdatedAt)}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="flex h-10 w-10 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
          title="Refresh logs"
          aria-label="Refresh logs"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {!compact && (
        <div className="mb-3 grid gap-2 text-[11px] sm:grid-cols-4">
          <JobMetric label="File" value={logs?.path || "-"} />
          <JobMetric label="Size" value={formatBytes(Number(logs?.size_bytes || 0))} />
          <JobMetric label="Lines" value={logs?.line_count ?? visibleLines.length} />
          <JobMetric label="Truncated" value={logs?.truncated ? "yes" : "no"} />
        </div>
      )}

      {error && (
        <div className="mb-3 flex gap-2 border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="mb-3 flex gap-2 border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{message}</span>
        </div>
      )}

      <div className={`${compact ? "max-h-[260px]" : "h-[calc(100%-132px)] min-h-[360px]"} overflow-auto border border-[#25272e] bg-black p-3`}>
        {visibleLines.length ? (
          <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-slate-300">
            {visibleLines.join("\n")}
          </pre>
        ) : (
          <div className="flex h-full min-h-32 items-center justify-center text-center text-xs leading-5 text-slate-600">
            {loading ? "Loading logs..." : "No backend log lines available."}
          </div>
        )}
      </div>
    </div>
  );
}

function JobsPanel({
  jobs,
  loading,
  error,
  statusFilter,
  onStatusFilterChange,
  onRefresh,
  onOpenProject,
  findProjectForJob,
  lastUpdatedAt,
  pollIntervalMs,
  compact = false,
  title = "Jobs",
  description,
  emptyMessage = "No jobs recorded for this filter.",
  onViewAllProjects,
  compactActionLabel = "View jobs",
}: {
  jobs: A2AJob[];
  loading: boolean;
  error: string | null;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  onRefresh: () => void;
  onOpenProject: (job: A2AJob) => void;
  findProjectForJob: (job: A2AJob) => any;
  lastUpdatedAt: string | null;
  pollIntervalMs: number;
  compact?: boolean;
  title?: string;
  description?: string;
  emptyMessage?: string;
  onViewAllProjects?: () => void;
  compactActionLabel?: string;
}) {
  const visibleJobs = compact ? jobs.slice(0, 2) : jobs;
  const filters = ["all", "queued", "running", "succeeded", "failed"];
  const panelDescription = description || `Generation and example job metadata. Polling every ${Math.round(pollIntervalMs / 1000)}s.`;

  return (
    <div className={`min-w-0 overflow-x-hidden ${compact ? "border border-[#2c2f37] bg-[#17181d] p-4" : "h-full overflow-y-auto bg-[#141519] p-4 sm:p-6"}`}>
      <div className={`${compact ? "mb-3 pb-3" : "mb-5 pb-4"} flex items-start justify-between gap-4 border-b border-[#2a2c33]`}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-black uppercase text-white">{title}</h2>
          </div>
          {!compact && (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {panelDescription}
            </p>
          )}
          {lastUpdatedAt && !compact && (
            <p className="mt-1 text-[11px] leading-5 text-slate-600">Updated {formatJobTime(lastUpdatedAt)}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="flex h-10 w-10 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
          title="Refresh jobs"
          aria-label="Refresh jobs"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {!compact && (
        <div className="mb-4 flex flex-wrap gap-2">
          {filters.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => onStatusFilterChange(filter)}
              className={`border px-3 py-2 text-xs font-bold uppercase ${
                statusFilter === filter
                  ? "border-white bg-white text-black"
                  : "border-[#2a2c33] bg-[#141519] text-slate-500 hover:border-slate-500 hover:text-white"
              }`}
            >
              {filter}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="mb-4 flex gap-2 border border-amber-500/30 bg-amber-950/25 p-3 text-xs leading-5 text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !visibleJobs.length ? (
        <div className="border border-[#2a2c33] bg-[#141519] p-5 text-sm text-slate-500">Loading jobs...</div>
      ) : visibleJobs.length ? (
        <div className="space-y-3">
          {visibleJobs.map((job) => (
            <JobRow
              key={job.job_id}
              job={job}
              project={findProjectForJob(job)}
              onOpenProject={() => onOpenProject(job)}
              compact={compact}
            />
          ))}
        </div>
      ) : (
        <div className="border border-[#2a2c33] bg-[#141519] p-5 text-sm leading-6 text-slate-500">
          {emptyMessage}
        </div>
      )}

      {compact && jobs.length > visibleJobs.length && (
        <button
          type="button"
          onClick={onViewAllProjects || (() => onStatusFilterChange(statusFilter))}
          className="group mt-4 flex w-full items-center justify-center gap-2 border border-[#2a2c33] px-4 py-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black"
        >
          <Database className="h-4 w-4" />
          <span>{jobs.length} total jobs</span>
          {onViewAllProjects && <span className="text-slate-500 group-hover:text-black">{compactActionLabel}</span>}
        </button>
      )}
    </div>
  );
}

function JobRow({
  job,
  project,
  onOpenProject,
  compact,
}: {
  job: A2AJob;
  project: any;
  onOpenProject: () => void;
  compact?: boolean;
}) {
  const tone = statusTone(job.status);
  const summary = job.result_summary || {};
  const title = summary.title || job.payload?.prompt || job.action;
  const prompt = job.payload?.prompt || job.correlation_id || job.job_id;
  const sourceUsage = getJobSourceUsage(job);
  const sourceLabel = formatSourceUsageLabel(sourceUsage);
  const SourceIcon = sourceUsage.web_research || sourceUsage.firecrawl ? Sparkles : Database;
  const llmInfo = getJobLlmInfo(job);
  const hasChatTarget = Boolean(chatIdFromJob(job));
  const hasProjectTarget = Boolean(project?.project_id);
  const isOpenable = hasChatTarget || hasProjectTarget;
  const imageStatusLabel = formatJobImageStatus(summary);
  const operations = getJobOperations(summary);

  return (
    <article className={`border border-[#2a2c33] bg-[#141519] ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] font-black uppercase ${tone}`}>
              {job.status === "succeeded" ? <CheckCircle className="h-3.5 w-3.5" /> : job.status === "failed" ? <AlertTriangle className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {job.status}
            </span>
            {sourceLabel !== "-" && (
              <span className="inline-flex max-w-full items-center gap-1.5 truncate border border-cyan-300/25 bg-cyan-300/10 px-2 py-1 text-[11px] font-black uppercase text-cyan-200">
                <SourceIcon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{sourceLabel}</span>
              </span>
            )}
            {llmInfo.label !== "-" && (
              <span className="inline-flex max-w-full items-center gap-1.5 truncate border border-violet-300/25 bg-violet-300/10 px-2 py-1 text-[11px] font-black uppercase text-violet-100">
                <Cpu className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{llmInfo.label}</span>
              </span>
            )}
            <span className="min-w-0 max-w-full truncate text-[11px] font-bold text-slate-500">{job.sender} {"->"} {job.recipient}</span>
          </div>
          <h3 className="truncate text-sm font-black text-white">{title}</h3>
          <p className="mt-2 line-clamp-2 break-words text-xs leading-5 text-slate-500">{prompt}</p>
        </div>

        <button
          type="button"
          onClick={onOpenProject}
          disabled={!isOpenable}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 border border-[#2a2c33] px-3 text-xs font-black uppercase text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-35"
        >
          <Eye className="h-4 w-4" />
          {hasChatTarget ? "Open chat" : "Open"}
        </button>
      </div>

      {!compact && (
        <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <JobMetric label="Job" value={job.job_id} />
          <JobMetric label="Created" value={formatJobTime(job.created_at)} />
          <JobMetric label="Duration" value={formatJobDuration(job)} />
          <JobMetric label="Source" value={sourceLabel} />
          <JobMetric label="LLM" value={llmInfo.label} />
          <JobMetric label="Parts" value={summary.component_count ?? "-"} />
          <JobMetric label="Valid" value={summary.is_valid === undefined ? "-" : summary.is_valid ? "yes" : "no"} />
          <JobMetric label="Image" value={imageStatusLabel} />
        </div>
      )}

      <JobPipelineEventList events={job.progress_events || []} jobStatus={job.status} compact={compact} />

      <OperationStatusList operations={operations} compact={compact} />

      {summary.image_output_failed && summary.image_output_error && (
        <div className="break-anywhere mt-3 border border-amber-500/30 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
          Image generation failed: {summary.image_output_error}
        </div>
      )}

      {job.error && (
        <div className="break-anywhere mt-3 border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          {job.error}
        </div>
      )}

      {job.error_debug && (
        <details className="mt-3 border border-rose-500/30 bg-black/25 p-3 text-xs text-rose-100">
          <summary className="cursor-pointer font-black uppercase text-rose-300">
            Debug trace{job.error_debug.error_type ? `: ${job.error_debug.error_type}` : ""}
          </summary>
          {job.error_debug.error && (
            <div className="break-anywhere mt-3 text-rose-200">{String(job.error_debug.error)}</div>
          )}
          {job.error_debug.context && (
            <pre className="break-anywhere mt-3 max-h-48 overflow-auto whitespace-pre-wrap border border-white/10 bg-black/30 p-3 text-[11px] leading-4 text-slate-300">
              {JSON.stringify(job.error_debug.context, null, 2)}
            </pre>
          )}
          {job.error_debug.traceback && (
            <pre className="break-anywhere mt-3 max-h-64 overflow-auto whitespace-pre-wrap border border-white/10 bg-black/30 p-3 text-[11px] leading-4 text-slate-300">
              {String(job.error_debug.traceback)}
            </pre>
          )}
        </details>
      )}
    </article>
  );
}

function getJobOperations(summary: Record<string, any>) {
  return Array.isArray(summary.operation_statuses)
    ? summary.operation_statuses.filter((operation: any) => operation && typeof operation === "object")
    : [];
}

function firstString(...values: any[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function getJobLlmInfo(job: A2AJob) {
  const summary = job.result_summary || {};
  const operations = getJobOperations(summary);
  const generationOperation = operations.find((operation) => operation.provider || operation.model) || {};
  const eventDetails = normalizeAgentPipelineEvents(job.progress_events)
    .map((event) => event.details || {})
    .reverse();
  const eventProvider = firstString(...eventDetails.map((details) => details.runtime_provider || details.provider));
  const eventModel = firstString(...eventDetails.map((details) => details.runtime_model || details.actual_model || details.model));
  const provider = firstString(
    summary.runtime_provider,
    summary.llm_provider,
    summary.requested_provider,
    job.payload?.provider,
    generationOperation.provider,
    eventProvider
  );
  const model = firstString(
    summary.runtime_model,
    summary.actual_model,
    summary.model_name,
    summary.requested_model,
    job.payload?.model,
    generationOperation.model,
    eventModel
  );

  return {
    provider,
    model,
    label: provider && model ? generationLlmLabel(provider, model) : provider || model || "-",
  };
}

function pipelineEventTone(status: string) {
  if (isCompletedPipelineStatus(status)) return "border-emerald-500/25 bg-emerald-950/15 text-emerald-300";
  if (isFailedPipelineStatus(status)) return "border-rose-500/30 bg-rose-950/20 text-rose-300";
  if (status === "skipped") return "border-slate-500/20 bg-slate-950/20 text-slate-500";
  return "border-cyan-500/25 bg-cyan-950/15 text-cyan-300";
}

function JobPipelineEventList({
  events,
  jobStatus,
  compact = false,
}: {
  events: AgentPipelineEvent[];
  jobStatus: string;
  compact?: boolean;
}) {
  const normalizedEvents = normalizeAgentPipelineEvents(events);
  if (!normalizedEvents.length) return null;
  const visibleEvents = compact ? normalizedEvents.slice(-3) : normalizedEvents.slice(-12);
  const jobIsTerminal = isTerminalJobStatus(jobStatus);

  return (
    <div className={`${compact ? "mt-3" : "mt-4"} border border-[#25272e] bg-black/20 p-3`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">Core pipeline events</span>
        <span className="font-mono text-[10px] text-slate-600">{normalizedEvents.length}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {visibleEvents.map((event, index) => {
          const label = event.label || event.step_id;
          const time = event.observed_at ? formatJobTime(event.observed_at) : "";
          const isActiveStartedEvent = event.status === "started" && !jobIsTerminal;
          return (
            <span key={`${event.step_id}-${event.status}-${event.observed_at || index}`} className={`inline-flex max-w-full items-center gap-1.5 border px-2 py-1 text-[10px] font-black uppercase ${pipelineEventTone(String(event.status))}`}>
              {isCompletedPipelineStatus(event.status) ? <CheckCircle className="h-3 w-3 shrink-0" /> : isFailedPipelineStatus(event.status) ? <AlertTriangle className="h-3 w-3 shrink-0" /> : <RefreshCw className={`h-3 w-3 shrink-0 ${isActiveStartedEvent ? "animate-spin" : ""}`} />}
              <span className="truncate">{label}</span>
              <span className="text-slate-500">{String(event.status).replace(/_/g, " ")}</span>
              {time && !compact && <span className="text-slate-600">{time}</span>}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function operationStatusTone(status: string) {
  if (status === "succeeded") return "border-emerald-500/30 bg-emerald-950/25 text-emerald-300";
  if (status === "failed") return "border-rose-500/30 bg-rose-950/20 text-rose-300";
  if (status === "pending") return "border-cyan-500/30 bg-cyan-950/20 text-cyan-300";
  if (status === "not_requested") return "border-slate-500/20 bg-slate-950/20 text-slate-500";
  return "border-slate-500/25 bg-slate-950/25 text-slate-400";
}

function OperationStatusList({ operations, compact = false }: { operations: Record<string, any>[]; compact?: boolean }) {
  if (!operations.length) return null;
  const visibleOperations = compact
    ? operations.filter((operation) => operation.status === "failed").slice(0, 2)
    : operations;
  if (!visibleOperations.length) return null;

  return (
    <div className={`${compact ? "mt-3" : "mt-4"} grid gap-2 ${compact ? "" : "sm:grid-cols-2 xl:grid-cols-3"}`}>
      {visibleOperations.map((operation, index) => {
        const status = String(operation.status || "unknown");
        const providerModel = [operation.provider, operation.model].filter(Boolean).join("/");
        const error = operation.error || operation.reason;
        return (
          <div key={`${operation.id || operation.label || "operation"}-${index}`} className={`min-w-0 border p-3 ${operationStatusTone(status)}`}>
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="truncate text-[11px] font-black uppercase">{operation.label || operation.id || "Operation"}</span>
              <span className="shrink-0 text-[10px] font-black uppercase">{status.replace(/_/g, " ")}</span>
            </div>
            {providerModel && (
              <div className="mt-1 truncate font-mono text-[10px] opacity-80">{providerModel}</div>
            )}
            {error && (
              <div className="break-anywhere mt-2 line-clamp-3 text-[11px] leading-4 opacity-90">
                {String(error)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function getJobSourceUsage(job: A2AJob) {
  const summaryUsage = job.result_summary?.source_usage;
  const workflow = job.result_summary?.workflow || job.payload?.workflow;
  return normalizeJobSourceUsage(job.source_usage || summaryUsage || (workflow ? { workflow } : {}));
}

function normalizeJobSourceUsage(value: any) {
  const sourceUsage = value && typeof value === "object" ? value : {};
  const rawWorkflow = typeof sourceUsage.workflow === "string" ? sourceUsage.workflow : "";
  const workflow = rawWorkflow.trim().toLowerCase().replace(/-/g, "_");
  const catalog = Boolean(sourceUsage.catalog || sourceUsage.data_warehouse || sourceUsage.used_catalog || workflow === "default" || workflow === "catalog");
  const externalProvider = typeof sourceUsage.external_provider === "string" ? sourceUsage.external_provider.trim().toLowerCase() : "";
  const webResearch = Boolean(
    sourceUsage.web_research ||
    sourceUsage.external_sources ||
    sourceUsage.tavily ||
    sourceUsage.firecrawl ||
    sourceUsage.used_web_research ||
    workflow === "web_research" ||
    workflow === "web_search" ||
    workflow === "websearch" ||
    workflow === "research" ||
    workflow === "firecrawl"
  );
  const sourceLabels = Array.isArray(sourceUsage.source_labels)
    ? sourceUsage.source_labels.filter((label: any) => typeof label === "string" && label.trim())
    : [];
  const labels = sourceLabels.length ? sourceLabels : [
    ...(catalog ? ["Catalog"] : []),
    ...(webResearch ? [sourceUsage.tavily || externalProvider === "tavily" ? "Tavily" : sourceUsage.firecrawl || externalProvider === "firecrawl" ? "Firecrawl" : "Web Research"] : []),
  ];
  return {
    ...sourceUsage,
    workflow,
    catalog,
    web_research: webResearch,
    external_sources: webResearch,
    external_provider: externalProvider || (sourceUsage.tavily ? "tavily" : sourceUsage.firecrawl ? "firecrawl" : sourceUsage.external_provider),
    tavily: Boolean(sourceUsage.tavily || externalProvider === "tavily"),
    firecrawl: Boolean(sourceUsage.firecrawl || externalProvider === "firecrawl"),
    source_labels: labels,
  };
}

function formatSourceUsageLabel(sourceUsage: Record<string, any>) {
  const labels = Array.isArray(sourceUsage.source_labels) ? sourceUsage.source_labels : [];
  return labels.length ? labels.join(" + ") : "-";
}

function formatJobImageStatus(summary: Record<string, any>) {
  if (summary.image_output_failed || summary.image_output_status === "failed") return "failed";
  if (summary.has_product_image) return summary.product_image_model || "yes";
  if (summary.image_output_status === "succeeded") return summary.product_image_model || "done";
  if (summary.image_output_requested === true) return summary.image_output_status || "requested";
  if (typeof summary.image_output_status === "string" && summary.image_output_status) {
    return summary.image_output_status.replace(/_/g, " ");
  }
  return "-";
}

function JobMetric({ label, value }: { label: string; value: any }) {
  return (
    <div className="min-w-0 border border-[#25272e] bg-[#17181d] px-3 py-2">
      <div className="text-[10px] font-black uppercase text-slate-600">{label}</div>
      <div className="mt-1 truncate text-xs font-bold text-slate-300">{String(value ?? "-")}</div>
    </div>
  );
}

function statusTone(status: string) {
  if (status === "succeeded") return "border-emerald-500/30 bg-emerald-950/25 text-emerald-300";
  if (status === "failed") return "border-rose-500/30 bg-rose-950/25 text-rose-300";
  if (status === "running" || status === "loading" || status === "reviewing") return "border-cyan-500/30 bg-cyan-950/25 text-cyan-300";
  if (status === "queued") return "border-amber-500/30 bg-amber-950/25 text-amber-300";
  return "border-slate-500/30 bg-slate-900 text-slate-300";
}

function isTerminalJobStatus(status: string) {
  return ["succeeded", "success", "completed", "complete", "done", "failed", "failure", "error", "cancelled", "canceled"].includes(status);
}

function isFinalVideoStatus(status: string) {
  return ["succeeded", "success", "completed", "complete", "done", "failed", "failure", "error", "cancelled", "canceled"].includes(status);
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value < 1024) return `${value} B`;
  const kb = value / 1024;
  if (kb < 1024) return `${kb.toFixed(kb >= 10 ? 0 : 1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
}

function formatJobTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatJobDuration(job: A2AJob) {
  if (!job.started_at || !job.completed_at) return job.status === "running" ? "running" : "-";
  return formatDurationSeconds(durationSecondsBetween(job.started_at, job.completed_at));
}

function PartsSidebar({ components, issues, isValid }: { components: any[]; issues: any[]; isValid: boolean }) {
  return (
    <aside className="hidden min-h-0 border-l border-[#282a30] bg-[#17181d] xl:flex xl:flex-col">
      <div className="border-b border-[#282a30] p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Box className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-black uppercase tracking-[0.2em] text-slate-400">Parts List</h2>
          </div>
          <span className="border border-[#30323a] px-2 py-1 text-[10px] text-slate-500">{components.length}</span>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-4 py-4">
        {components.map((component, index) => {
          const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
          const Icon = iconForCategory(component.category);
          return (
            <div key={`${component.ref_des}-${index}`} className="flex min-w-0 items-center gap-3 py-1.5">
              <Icon className={`h-4 w-4 shrink-0 ${tone.text}`} />
              <span className="truncate text-sm font-bold text-slate-300">{component.name}</span>
            </div>
          );
        })}
      </div>
      <div className="border-t border-[#282a30] p-4">
        <div className={`flex items-center gap-2 border p-3 text-xs font-black uppercase tracking-widest ${
          isValid ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300" : "border-rose-500/30 bg-rose-950/20 text-rose-300"
        }`}>
          {isValid ? <CheckCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          {isValid ? "Circuit Approved" : `${issues.length} Issues`}
        </div>
      </div>
    </aside>
  );
}

function ProductRender({ product }: { product?: string }) {
  return (
    <div className="relative flex h-[440px] items-center justify-center overflow-hidden bg-[#d5d5d3]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_45%_38%,rgba(255,255,255,0.88),rgba(210,210,208,0.35)_48%,rgba(185,185,182,0.55))]" />
      <div className="relative h-64 w-[470px] rotate-[-16deg] skew-x-[-8deg] rounded-[34px] border border-black/20 bg-gradient-to-br from-[#6b6b68] via-[#3f403d] to-[#222321] shadow-2xl">
        <div className="absolute left-9 top-8 h-48 w-[400px] rounded-[28px] border border-white/10 bg-gradient-to-br from-[#888884] via-[#4f504d] to-[#262725]" />
        <div className="absolute right-14 top-10 h-28 w-44 rounded-xl border border-black/40 bg-[#0c0d10] shadow-inner">
          <div className="absolute left-5 top-10 h-px w-32 bg-cyan-300/70 shadow-[12px_-10px_0_rgba(103,232,249,0.45),30px_12px_0_rgba(103,232,249,0.6),58px_-2px_0_rgba(103,232,249,0.5)]" />
          <div className="absolute bottom-4 left-6 flex gap-5 text-white/60">
            <span className="h-3 w-3 border-l-4 border-y-4 border-y-transparent" />
            <span className="h-3 w-3 border-l-4 border-y-4 border-y-transparent" />
            <span className="h-3 w-3 bg-white/60" />
          </div>
        </div>
        <div className="absolute left-28 top-28 h-28 w-28 rounded-full border-[10px] border-[#222] bg-[#565653] shadow-inner">
          <div className="absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/40 bg-[#8a8a84]" />
          <div className="absolute left-[42px] top-[38px] h-0 w-0 border-y-[12px] border-l-[18px] border-y-transparent border-l-[#4a4a48]" />
        </div>
        <span className="absolute left-20 top-24 h-9 w-9 rounded-full border border-black/40 bg-[#777771]" />
        <span className="absolute left-[104px] top-42 h-8 w-8 rounded-full border border-black/40 bg-[#777771]" />
        <span className="absolute right-5 top-32 h-12 w-3 rounded bg-black/50" />
      </div>
      <div className="absolute bottom-6 right-8 text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">
        {product === "pocket_mp3_player" ? "Rendered from extracted MP3 player features" : "Generated visual reference"}
      </div>
    </div>
  );
}

function SummaryRow({ label, parts, cost, strong = false }: { label: string; parts: number; cost: number; strong?: boolean }) {
  return (
    <div className={`grid grid-cols-3 border-b border-[#2a2c33] px-4 py-3 text-base last:border-b-0 ${strong ? "font-black text-white" : "text-slate-300"}`}>
      <span>{label}</span>
      <span className="text-center">{parts}</span>
      <span className="text-right">${cost.toFixed(2)}</span>
    </div>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const tone = categoryTone[category?.toLowerCase()] || categoryTone.default;
  const Icon = iconForCategory(category);
  return (
    <span className={`mt-4 inline-flex items-center gap-1.5 border ${tone.border} ${tone.bg} px-3 py-2 text-[10px] font-black uppercase tracking-widest ${tone.text}`}>
      <Icon className="h-3 w-3" />
      {tone.label}
    </span>
  );
}

function PartThumb({ component }: { component: any }) {
  const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
  const Icon = iconForCategory(component.category);
  return (
    <div className="flex h-[104px] w-[104px] shrink-0 items-center justify-center bg-white">
      <div className={`flex h-16 w-16 items-center justify-center border ${tone.border} ${tone.bg}`}>
        <Icon className={`h-9 w-9 ${tone.text}`} />
      </div>
    </div>
  );
}

function getSourcesForComponent(component: any): Array<{ label: string; className: string; href: string; title: string }> {
  const category = component.category?.toLowerCase();
  const withHref = (source: { label: string; className: string }) => ({
    ...source,
    href: sourceHrefForComponent(component, source.label),
    title: sourceTitleForComponent(component, source.label),
  });

  if (category === "actuator") {
    return [
      { label: "AliExpress", className: "bg-orange-600" },
      { label: "amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
    ].map(withHref);
  }
  if (category === "power" && component.name?.toLowerCase().includes("charger")) {
    return [
      { label: "amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
    ].map(withHref);
  }
  return [
    {
      label: component.category?.toLowerCase() === "mechanical" || component.category?.toLowerCase() === "3d print" ? "fabricate" : "eBay",
      className: "bg-blue-600 text-white",
    },
  ].map(withHref);
}

function componentSearchText(component: any) {
  const values = [component.part_number, component.name, component.category].filter(Boolean);
  return values.join(" ").trim() || "electronic component";
}

function sourceHrefForComponent(component: any, label: string) {
  const normalizedLabel = label.toLowerCase();
  const query = encodeURIComponent(componentSearchText(component));

  if (normalizedLabel === "aliexpress") return `https://www.aliexpress.com/wholesale?SearchText=${query}`;
  if (normalizedLabel === "amazon") return `https://www.amazon.com/s?k=${query}`;
  if (normalizedLabel === "ebay") return `https://www.ebay.com/sch/i.html?_nkw=${query}`;
  if (normalizedLabel === "fabricate") {
    const explicitUrl = firstComponentSourceUrl(component);
    return explicitUrl || `https://www.printables.com/search/models?q=${query}`;
  }

  return firstComponentSourceUrl(component) || `https://www.google.com/search?q=${query}`;
}

function sourceTitleForComponent(component: any, label: string) {
  const part = component.part_number || component.name || "component";
  if (label.toLowerCase() === "fabricate") return `Find fabrication/CAD sources for ${part}`;
  return `Search ${label} for ${part}`;
}

function firstComponentSourceUrl(component: any) {
  const candidates = [
    component.sourcing_url,
    component.source_url,
    component.supplier_url,
    component.vendor_url,
    component.purchase_url,
    component.url,
  ];
  const match = candidates.find((candidate) => typeof candidate === "string" && /^https?:\/\//i.test(candidate));
  return match || "";
}

function iconForCategory(category = "") {
  const cat = category.toLowerCase();
  if (cat === "microcontroller") return Cpu;
  if (cat === "sensor") return Database;
  if (cat === "power") return Battery;
  if (cat === "display") return Monitor;
  if (cat === "actuator") return Volume2;
  if (cat === "passives") return Sliders;
  if (cat === "mechanical") return Wrench;
  if (cat === "3d print") return Printer;
  return Box;
}

function MechanicalLabel({ label, index }: { label: string; index: number }) {
  const positions = [
    "left-[36%] top-[19%]",
    "left-[56%] top-[27%]",
    "left-[51%] top-[31%]",
    "left-[42%] top-[48%]",
    "left-[34%] top-[52%]",
    "left-[46%] top-[58%]",
    "left-[48%] top-[63%]",
    "left-[45%] top-[74%]",
    "left-[27%] top-[82%]",
    "left-[24%] top-[86%]",
  ];
  const sizes = index === 4 ? "text-lg" : index > 7 ? "text-sm" : "text-xs";
  return (
    <div className={`absolute ${positions[index]} ${sizes} bg-black/88 px-3 py-1 font-black uppercase tracking-[0.12em] text-violet-300 shadow-lg`}>
      <span className="absolute -left-1 top-0 h-full w-px bg-violet-300" />
      <span>{label}</span>
      <span className="absolute left-1/2 top-full h-40 w-px bg-violet-200/25" />
    </div>
  );
}

function layerColor(key: string) {
  if (key === "structural") return "text-cyan-400";
  if (key === "enclosure") return "text-emerald-400";
  if (key === "mechanism") return "text-amber-400";
  if (key === "print") return "text-violet-300";
  if (key === "bodyRotation") return "text-rose-300";
  return "text-slate-400";
}

function mechanicalToggleLabel(key: string) {
  if (key === "print") return "3D Print";
  if (key === "bodyRotation") return "Body Rotate";
  return key;
}

function emptyMetrics() {
  return { electricalParts: 0, mechanicalParts: 0, totalParts: 0, electricalCost: 0, mechanicalCost: 0, totalCost: 0 };
}
