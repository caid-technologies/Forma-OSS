"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Handle,
  NodeProps,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import MechanicalScene from "../components/mechanical-scene";
import PartnerLogoMarquee from "../components/partner-logo-marquee";
import { partners } from "../lib/partners";
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
} from "lucide-react";

const DEFAULT_API_URL = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_API_URL);
const JOB_POLL_INTERVAL_MS = 5000;
const VIDEO_POLL_INTERVAL_MS = 4000;

type GenerationWorkflowOption = {
  id: string;
  label: string;
  description?: string;
  uses_catalog?: boolean;
  uses_web_research?: boolean;
  uses_firecrawl_mcp?: boolean;
};

const defaultGenerationWorkflows: GenerationWorkflowOption[] = [
  { id: "default", label: "Catalog", description: "Catalog workflow", uses_catalog: true },
  { id: "web_research", label: "Web Research", description: "Firecrawl MCP workflow", uses_web_research: true, uses_firecrawl_mcp: true },
];

function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

const samplePrompts = [
  "Compact handheld device with display, controls, USB-C power, and enclosure",
  "Environmental monitor with sensor feedback, display, and battery power",
  "Small controller for a low-voltage actuator or relay",
];

const hardwareIdeaTerms = new Set([
  "actuator",
  "alarm",
  "arduino",
  "audio",
  "battery",
  "bluetooth",
  "button",
  "camera",
  "charger",
  "controller",
  "cube",
  "display",
  "door",
  "enclosure",
  "esp32",
  "fan",
  "gps",
  "haptic",
  "iot",
  "keyboard",
  "knob",
  "lamp",
  "led",
  "light",
  "lock",
  "logger",
  "meter",
  "monitor",
  "module",
  "moisture",
  "motor",
  "mp3",
  "music",
  "nfc",
  "oled",
  "plant",
  "player",
  "printer",
  "pump",
  "reader",
  "relay",
  "remote",
  "rfid",
  "robot",
  "screen",
  "sensor",
  "servo",
  "speaker",
  "station",
  "switch",
  "tag",
  "temperature",
  "thermostat",
  "timer",
  "tracker",
  "usb",
  "wearable",
  "wifi",
  "wristband",
]);

const hardwareActionTerms = new Set([
  "alert",
  "alerts",
  "blink",
  "blinks",
  "charge",
  "charges",
  "control",
  "controls",
  "detect",
  "detects",
  "display",
  "displays",
  "heat",
  "lights",
  "log",
  "logs",
  "measure",
  "measures",
  "monitor",
  "monitors",
  "move",
  "moves",
  "notify",
  "notifies",
  "open",
  "opens",
  "play",
  "plays",
  "pump",
  "pumps",
  "rotate",
  "rotates",
  "sense",
  "senses",
  "track",
  "tracks",
  "unlock",
  "unlocks",
  "vibrate",
  "vibrates",
  "water",
  "watering",
  "waters",
]);

const vaguePromptTerms = new Set([
  "a",
  "an",
  "and",
  "app",
  "build",
  "cool",
  "create",
  "device",
  "for",
  "hardware",
  "idea",
  "make",
  "me",
  "plan",
  "project",
  "prototype",
  "something",
  "stuff",
  "that",
  "the",
  "thing",
  "to",
  "with",
]);

function tokenizePrompt(value: string) {
  return value.toLowerCase().match(/[a-z0-9]+/g) || [];
}

function promptLooksLikeGibberish(value: string, tokens: string[]) {
  const letters = value.toLowerCase().replace(/[^a-z]/g, "");
  if (letters.length < 5) return false;

  const hasKnownHardwareLanguage = tokens.some((token) => hardwareIdeaTerms.has(token) || hardwareActionTerms.has(token));
  if (hasKnownHardwareLanguage) return false;

  const vowelCount = letters.match(/[aeiou]/g)?.length || 0;
  const vowelRatio = vowelCount / letters.length;
  const longConsonantRun = /[bcdfghjklmnpqrstvwxyz]{5,}/.test(letters);
  const lowVarietyPlaceholder = tokens.length <= 2 && new Set(letters).size <= 3 && letters.length >= 5;

  return vowelRatio < 0.16 || longConsonantRun || lowVarietyPlaceholder;
}

function validateGenerationInput(value: string, hasImage: boolean) {
  const promptText = value.trim();
  if (!promptText) {
    return {
      isValid: hasImage,
      message: hasImage ? null : "Provide a prompt or reference image.",
    };
  }

  const tokens = tokenizePrompt(promptText);
  const hasHardwareTerm = tokens.some((token) => hardwareIdeaTerms.has(token));
  const hasActionTerm = tokens.some((token) => hardwareActionTerms.has(token));
  const specificTokens = tokens.filter((token) => token.length >= 3 && !vaguePromptTerms.has(token));

  if (!tokens.length) {
    return {
      isValid: false,
      message: "Add a buildable hardware idea before compiling.",
    };
  }

  if (promptLooksLikeGibberish(promptText, tokens)) {
    return {
      isValid: false,
      message: "I could not read that as a hardware idea yet. Name a device and what it should do, or clear the text and use an image.",
    };
  }

  if (tokens.length < 2 && !hasHardwareTerm) {
    return {
      isValid: false,
      message: "Add a little more detail before compiling, like a device plus what it should sense, control, display, or move.",
    };
  }

  if (!hasHardwareTerm && !hasActionTerm && specificTokens.length < 3) {
    return {
      isValid: false,
      message: "Add a concrete hardware idea before compiling, like a device plus what it should sense, control, display, or move.",
    };
  }

  if (!hasHardwareTerm && !hasActionTerm && tokens.length < 5) {
    return {
      isValid: false,
      message: "Add what the build should do before compiling.",
    };
  }

  return {
    isValid: true,
    message: null,
  };
}

async function readApiErrorMessage(response: Response) {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      const messages = body.detail
        .map((item: any) => item?.msg || item?.message || item?.detail)
        .filter(Boolean);
      if (messages.length) return messages.join("; ");
    }
    if (typeof body?.detail?.message === "string") return body.detail.message;
    if (typeof body?.message === "string") return body.message;
    if (typeof body?.error === "string") return body.error;
  } catch {
    // Fall through to a generic message.
  }

  return `Server returned ${response.status}`;
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
  image: ProjectImageCandidate | null;
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
  { id: "overview", label: "IMAGE", icon: Eye },
  { id: "bom", label: "BOM", icon: ShoppingBag },
  { id: "mechanical", label: "MECH", icon: Box },
  { id: "schematic", label: "WIRE", icon: Cpu },
  { id: "assembly", label: "DOCS", icon: Info },
  { id: "svg", label: "SVG", icon: Layers },
  { id: "video", label: "VIDEO", icon: Film },
  { id: "jobs", label: "JOBS", icon: History },
];

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
  error?: string | null;
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

function normalizeVideoGenerationMode(value: any): VideoGenerationMode {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (["video-to-video", "video_to_video", "video2video", "v2v", "video"].includes(normalized)) return "video-to-video";
  return "image-to-video";
}

function videoSourceUrl(video: StoredVideoInfo | null | undefined): string {
  return video?.url || video?.publicUrl || video?.signedUrl || "";
}

type SchematicNodeData = {
  component: any;
  pins: SchematicPin[];
  tone: {
    label: string;
    border: string;
    text: string;
    soft: string;
  };
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
  microcontroller: { label: "MCU", border: "#22c7dd", text: "#06b6d4", soft: "#ecfeff" },
  sensor: { label: "SENSOR", border: "#3b82f6", text: "#2563eb", soft: "#eff6ff" },
  actuator: { label: "ACTUATOR", border: "#ff6b21", text: "#ea580c", soft: "#fff7ed" },
  power: { label: "POWER", border: "#f5a400", text: "#d97706", soft: "#fffbeb" },
  passives: { label: "MODULE", border: "#8b5cf6", text: "#7c3aed", soft: "#f5f3ff" },
  communication: { label: "MODULE", border: "#8b5cf6", text: "#7c3aed", soft: "#f5f3ff" },
  display: { label: "DISPLAY", border: "#ec4899", text: "#db2777", soft: "#fdf2f8" },
  default: { label: "PART", border: "#94a3b8", text: "#64748b", soft: "#f8fafc" },
};

const schematicNodeTypes = {
  schematicPart: SchematicPartNode,
};

function SchematicPartNode({ data }: NodeProps<SchematicNodeData>) {
  const { component, pins, tone } = data;
  const Icon = iconForCategory(component.category);
  const visiblePins = pins.length ? pins : [{ pin_id: "NC", name: "No connected pins", pin_type: "Passive" }];

  return (
    <div className="schematic-node w-[190px] bg-white px-3 py-3 text-center shadow-sm" style={{ border: `2px solid ${tone.border}` }}>
      <div className="text-[8px] font-black uppercase leading-none tracking-[0.22em]" style={{ color: tone.text }}>
        {tone.label}
      </div>
      <div className="mt-1 truncate text-[11px] font-black leading-tight text-[#202127]">{component.name || component.ref_des}</div>
      <div className="mt-1 truncate text-[8px] font-bold leading-tight text-[#6f7280]">{component.part_number || component.ref_des}</div>

      <div className="mx-auto mt-2 flex h-[76px] w-[108px] items-center justify-center border border-[#d9dcec] bg-white" style={{ backgroundColor: tone.soft }}>
        <Icon className="h-10 w-10" style={{ color: tone.text }} />
      </div>

      <div className="mt-2 flex flex-wrap justify-center gap-1">
        {visiblePins.map((pin) => {
          const disabled = pin.pin_id === "NC";
          return (
            <div
              key={pin.pin_id}
              className="relative max-w-full rounded-[3px] border bg-white px-1.5 py-0.5 text-[7px] font-black leading-none text-[#6f7280]"
              style={{ borderColor: tone.border, color: disabled ? "#a8adba" : tone.text }}
              title={`${pin.pin_id}${pin.name ? ` - ${pin.name}` : ""}`}
            >
              {!disabled && (
                <>
                  <Handle
                    type="target"
                    id={schematicHandleId(component.ref_des, pin.pin_id)}
                    position={Position.Left}
                    className="schematic-pin-handle"
                    style={{ left: -7, top: "50%", ["--handle-border" as string]: tone.border, ["--handle-color" as string]: "#ffffff" }}
                  />
                  <Handle
                    type="source"
                    id={schematicHandleId(component.ref_des, pin.pin_id)}
                    position={Position.Right}
                    className="schematic-pin-handle"
                    style={{ right: -7, top: "50%", ["--handle-border" as string]: tone.border, ["--handle-color" as string]: "#ffffff" }}
                  />
                </>
              )}
              <span className="block max-w-[72px] truncate">{pin.pin_id}</span>
            </div>
          );
        })}
      </div>
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

function withProjectResponseMetadata(ir: any, response: any) {
  if (!ir) return ir;
  return {
    ...ir,
    assembly_metadata: {
      ...(ir.assembly_metadata || {}),
      project_id: ir.assembly_metadata?.project_id || response?.project_id,
      frontend_job_id: ir.assembly_metadata?.frontend_job_id || response?.job_id,
    },
  };
}

function projectIdFromIR(ir: any) {
  return ir?.assembly_metadata?.project_id || null;
}

function projectRoute(projectId: string) {
  return `/project/${encodeURIComponent(projectId)}`;
}

function safeDecodeProjectId(projectId: string) {
  try {
    return decodeURIComponent(projectId);
  } catch {
    return projectId;
  }
}

function normalizePlacement(value: any): PlacementPoint | null {
  if (!value || typeof value.x !== "number" || typeof value.y !== "number") return null;
  return { x: value.x, y: value.y };
}

type HomeProps = {
  routeProjectId?: string | null;
};

export function BlueprintWorkspace({ routeProjectId = null }: HomeProps = {}) {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [projectIR, setProjectIR] = useState<any>(null);
  const [mermaidCode, setMermaidCode] = useState<string>("");
  const [svgSchematic, setSvgSchematic] = useState<string>("");
  const [projectHistory, setProjectHistory] = useState<any[]>([]);
  const [a2aJobs, setA2aJobs] = useState<A2AJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobStatusFilter, setJobStatusFilter] = useState("all");
  const [jobsLastUpdatedAt, setJobsLastUpdatedAt] = useState<string | null>(null);
  const [videoModels, setVideoModels] = useState<VideoModelOption[]>([]);
  const [videoModelsLoading, setVideoModelsLoading] = useState(false);
  const [videoModelsError, setVideoModelsError] = useState<string | null>(null);
  const [selectedVideoModel, setSelectedVideoModel] = useState("");
  const [videoImageInput, setVideoImageInput] = useState("");
  const [selectedVideoImageSources, setSelectedVideoImageSources] = useState<string[]>([]);
  const [videoImageTouched, setVideoImageTouched] = useState(false);
  const [videoPrompt, setVideoPrompt] = useState("");
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
  const [projectGalleryImages, setProjectGalleryImages] = useState<Record<string, ProjectImageCandidate | null>>({});
  const [routeProjectError, setRouteProjectError] = useState<string | null>(null);
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
  const [alphaSignupForm, setAlphaSignupForm] = useState({
    name: "",
    email: "",
    organization: "",
    additionalInfo: "",
  });
  const [alphaSignupStatus, setAlphaSignupStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [alphaSignupMessage, setAlphaSignupMessage] = useState<string | null>(null);
  const [generateProductImage, setGenerateProductImage] = useState(false);
  const [generationWorkflow, setGenerationWorkflow] = useState("default");
  const [generationWorkflows, setGenerationWorkflows] = useState<GenerationWorkflowOption[]>(defaultGenerationWorkflows);
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
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const projectGalleryItems = useMemo(
    () => buildProjectGalleryItems(projectHistory, projectGalleryImages),
    [projectHistory, projectGalleryImages]
  );
  const generationInputValidation = useMemo(
    () => validateGenerationInput(prompt, Boolean(selectedImage)),
    [prompt, selectedImage]
  );
  const visibleGenerationInputNotice =
    generationInputNotice || (prompt.trim() && !generationInputValidation.isValid ? generationInputValidation.message : null);
  const hasGenerationInput = Boolean(prompt.trim() || selectedImage);
  const alphaGateActive = alphaGateConfig.gateActive;

  const scrollToProjects = () => {
    projectsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const goHome = () => {
    setProjectIR(null);
    setMermaidCode("");
    setSvgSchematic("");
    setActiveTab("overview");
    router.push("/");
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

  useEffect(() => {
    checkServerStatus();
    fetchRuntimeConfig();
    fetchGenerationWorkflows();
    fetchVideoModels();
    fetchCatalog();
    fetchProjectHistory();
  }, []);

  const checkServerStatus = async () => {
    try {
      const res = await fetch(API_URL);
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
      if (Array.isArray(config.workflows) && config.workflows.length > 0) {
        setGenerationWorkflows(config.workflows);
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
      const res = await fetch(`${API_URL}/video/projects/${encodeURIComponent(projectId)}`);
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
  }, []);

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
      const res = await fetch(`${API_URL}/projects`);
      if (res.ok) setProjectHistory(await res.json());
    } catch (e) {
      console.error("Error fetching project history", e);
    }
  };

  const fetchA2aJobs = useCallback(async (status: string, options: { silent?: boolean } = {}) => {
    if (!options.silent) setJobsLoading(true);
    setJobsError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (status !== "all") params.set("status", status);
      const res = await fetch(`${API_URL}/a2a/jobs?${params.toString()}`);
      if (!res.ok) throw new Error(`Jobs endpoint returned ${res.status}`);
      setA2aJobs(await res.json());
      setJobsLastUpdatedAt(new Date().toISOString());
    } catch (e) {
      console.error("Error fetching A2A jobs", e);
      setJobsError("Jobs are unavailable");
    } finally {
      if (!options.silent) setJobsLoading(false);
    }
  }, []);

  const changeJobStatusFilter = (status: string) => {
    setJobStatusFilter(status);
    fetchA2aJobs(status);
  };

  useEffect(() => {
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
  }, [fetchA2aJobs, jobStatusFilter]);

  useEffect(() => {
    if (routeProjectId || projectIR) return;

    const missingProjects = projectHistory.filter((project: any) => {
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
  }, [projectHistory, projectGalleryImages, projectIR, routeProjectId]);

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
      setVideoStatus("succeeded");
      setVideoStatusMessage("Video saved.");
      return;
    }

    setStoredVideo(null);
    setVideoStatus(statusValue);
    setVideoStatusMessage(statusValue === "queued" ? "Queued." : `Status: ${statusValue}.`);
  }, []);

  const pollVideoStatus = useCallback(async (requestId = videoRequestId) => {
    const projectId = projectIdFromIR(projectIR);
    if (!requestId || !projectId || !selectedVideoModel) return;

    const params = new URLSearchParams({
      projectId,
      model: selectedVideoModel,
      mode: videoMode,
    });

    try {
      const res = await fetch(`${API_URL}/video/image-to-video/status/${encodeURIComponent(requestId)}?${params.toString()}`);
      if (!res.ok) throw new Error(await readApiErrorMessage(res));

      const data = await res.json();
      applyVideoStatusResponse(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network request failed.";
      setVideoStatus("failed");
      setVideoStatusMessage(message);
    }
  }, [applyVideoStatusResponse, projectIR, selectedVideoModel, videoMode, videoRequestId]);

  const handleGenerateVideo = async () => {
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
    const promptText = videoPrompt.trim();
    const model = selectedVideoModel.trim();
    const isVideoToVideo = videoMode === "video-to-video";

    if (!projectId || !promptText || !model || (isVideoToVideo ? !sourceVideo : !images.length)) {
      setVideoStatus("failed");
      setVideoStatusMessage(`Project id, ${isVideoToVideo ? "source video" : "image"}, prompt, and model are required.`);
      return;
    }

    setVideoRequestId(null);
    setStoredVideo(null);
    setVideoStatus("loading");
    setVideoStatusMessage("Starting.");

    try {
      const sources = isVideoToVideo ? [sourceVideo] : images;
      for (let index = 0; index < sources.length; index += 1) {
        const source = sources[index];
        const selectedImage = !isVideoToVideo ? videoImageOptions.find((candidate) => candidate.src === source) : null;
        const viewPrompt = selectedImage?.label ? `${promptText}\nSource view: ${selectedImage.label}.` : promptText;
        setVideoStatusMessage(sources.length > 1 ? `Starting ${index + 1} of ${sources.length}.` : "Starting.");

        const res = await fetch(`${API_URL}/video/${isVideoToVideo ? "video-to-video" : "image-to-video"}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
          window.setTimeout(() => pollVideoStatus(requestId), 800 + index * 400);
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
        const pinMap = pinMapByRef.get(pinRef.ref_des);
        if (!pinMap || pinMap.has(pinRef.pin_id)) return;
        pinMap.set(pinRef.pin_id, {
          pin_id: pinRef.pin_id,
          name: pinRef.pin_id,
          pin_type: net.net_type,
          voltage: net.voltage,
        });
      });
    });

    const schematicMeta = ir.assembly_metadata?.schematic || {};
    const explicitPlacements = schematicMeta.placements || {};
    const defaultColumns: Record<string, { x: number; y: number }> = {
      power: { x: 360, y: 60 },
      sensor: { x: 620, y: 60 },
      microcontroller: { x: 620, y: 300 },
      passives: { x: 880, y: 120 },
      communication: { x: 880, y: 360 },
      actuator: { x: 1140, y: 120 },
      display: { x: 1140, y: 360 },
      default: { x: 880, y: 560 },
    };
    const categoryCounts: Record<string, number> = {};

    electricalParts.forEach((component: any) => {
      const category = component.category?.toLowerCase() || "default";
      const placement = normalizePlacement(explicitPlacements[component.ref_des]);
      const baseColumn = defaultColumns[category] || defaultColumns.default;
      const groupIndex = categoryCounts[category] || 0;
      categoryCounts[category] = groupIndex + 1;
      const position = placement || {
        x: baseColumn.x,
        y: baseColumn.y + groupIndex * 185,
      };
      const pins = Array.from(pinMapByRef.get(component.ref_des)?.values() || []).sort((a, b) =>
        pinKey(a).localeCompare(pinKey(b), undefined, { numeric: true })
      );

      newNodes.push({
        id: component.ref_des,
        type: "schematicPart",
        position,
        draggable: true,
        data: {
          component,
          pins,
          tone: schematicToneForCategory(category),
        },
        style: { background: "transparent", border: "none", width: 190 },
      });
    });

    const netStyles: Record<string, { color: string; dash?: string; width: number }> = {
      ground: { color: "#94a3b8", dash: "8 6", width: 2 },
      power: { color: "#f5a400", dash: "5 5", width: 2 },
      i2c: { color: "#22c55e", width: 2 },
      spi: { color: "#22c55e", width: 2 },
      digital: { color: "#22c55e", width: 2 },
      analog: { color: "#22c55e", width: 2 },
      pwm: { color: "#22c55e", width: 2 },
      default: { color: "#22c55e", width: 2 },
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
            label: edgeLabel(net, sourcePin, targetPin),
            labelBgPadding: [4, 2],
            labelBgBorderRadius: 2,
            labelBgStyle: { fill: "#ffffff", fillOpacity: 0.88 },
            labelStyle: { fill: style.color, fontWeight: 800, fontSize: 9, fontFamily: "monospace" },
            style: {
              stroke: style.color,
              strokeWidth: style.width,
              strokeDasharray: style.dash || "none",
            },
            markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: style.color },
          });
        });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  };

  const handleGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
    const validation = validateGenerationInput(prompt, Boolean(selectedImage));
    if (!validation.isValid) {
      setGenerationInputNotice(validation.message);
      return;
    }

    const promptText = prompt.trim() || "Infer a buildable hardware project from the uploaded reference image.";
    const imageData = selectedImage;
    let generatedProject = false;

    setGenerationInputNotice(null);
    setIsLoading(true);
    checkServerStatus();

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: promptText,
          workflow: generationWorkflow,
          image_data: imageData || null,
          generate_image: generateProductImage,
        }),
      });

      if (!res.ok) {
        const errorMessage = await readApiErrorMessage(res);
        if (res.status === 400) {
          setGenerationInputNotice(errorMessage);
          return;
        }
        if (res.status === 503) {
          setAlphaGateConfig({ gateActive: true });
          setGenerationInputNotice(errorMessage);
          return;
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();
      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);
      const projectId = projectIdFromIR(ir);
      if (projectId) syncProjectRoute(projectId);
      fetchProjectHistory();
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
        setProjectIR(mockRes.project_ir);
        setMermaidCode(mockRes.mermaid_code);
        setSvgSchematic(mockRes.svg_schematic);
        buildReactFlowGraph(mockRes.project_ir);
        generatedProject = true;
      } catch (fallbackError) {
        const message = fallbackError instanceof Error ? fallbackError.message : "Local example fallback failed.";
        setGenerationInputNotice(`Generation failed and local fallback was unavailable: ${message}`);
      }
    } finally {
      if (generatedProject) {
        setSelectedImage(null);
        setActiveTab("overview");
      }
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
    options: { syncRoute?: boolean; signal?: AbortSignal } = {}
  ): Promise<boolean> => {
    if (options.signal?.aborted) return false;

    const shouldSyncRoute = options.syncRoute ?? true;
    const signal = options.signal;
    setIsLoading(true);
    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, { signal });
      if (!res.ok) return false;

      const data = await res.json();
      if (signal?.aborted) return false;

      const ir = withProjectResponseMetadata(data.project_ir, data);
      setProjectIR(ir);
      setMermaidCode(data.mermaid_code);
      setSvgSchematic(data.svg_schematic);
      buildReactFlowGraph(ir);
      setActiveTab("overview");
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
    setProjectIR(null);
    setMermaidCode("");
    setSvgSchematic("");
    setRouteProjectError(null);

    loadOldProject(projectId, { syncRoute: false, signal: controller.signal }).then((loaded) => {
      if (controller.signal.aborted) return;
      if (!loaded) {
        setRouteProjectError("Could not load that saved project.");
        return;
      }
      if (tab) {
        setActiveTab(tab);
      }
    });

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeProjectId]);

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

  const loadProjectForJob = async (job: A2AJob) => {
    const project = findProjectForJob(job);
    if (!project?.project_id) return;
    await loadOldProject(project.project_id);
  };

  const downloadJSONIR = () => {
    if (!projectIR) return;
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
  const currentProjectJobId = projectIR?.assembly_metadata?.frontend_job_id || null;
  const projectJobs = a2aJobs.filter((job) => {
    if (currentProjectJobId && job.job_id === currentProjectJobId) return true;
    if (currentProjectId && job.result_summary?.project_id === currentProjectId) return true;
    return false;
  });

  useEffect(() => {
    setVideoImageTouched(false);
    setVideoRequestId(null);
    setStoredVideo(null);
    setVideoGallery([]);
    setVideoGalleryError(null);
    setVideoSourceVideoUrl("");
    setSelectedVideoImageSources([]);
    setVideoMode("image-to-video");
    setVideoStatus("idle");
    setVideoStatusMessage(null);
    if (fileInputRefVideo.current) fileInputRefVideo.current.value = "";
    if (currentProjectId) fetchProjectVideos(currentProjectId);
  }, [currentProjectId, fetchProjectVideos]);

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
      <div className="min-h-screen w-full overflow-x-hidden bg-[#141519] font-sans text-slate-100">
        <header className="border-b border-[#292b31] bg-[#141519]/95">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-5 py-4">
            <button type="button" onClick={goHome} className="min-w-0 text-left">
              <span className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center border border-[#2c2f37] bg-black text-white">
                  <Cpu className="h-4 w-4" />
                </span>
                <span className="hidden text-sm font-black uppercase tracking-[0.22em] text-white sm:block">Blueprint</span>
              </span>
            </button>
            <div className="flex shrink-0 items-center gap-2">
              <span className={`hidden border px-3 py-1.5 text-xs font-semibold sm:block ${
                serverStatus === "connected"
                  ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-400"
                  : "border-amber-500/30 bg-amber-950/30 text-amber-400"
              }`}>
                {serverStatus === "connected" ? "API connected" : "Demo mode"}
              </span>
              <Link
                href="/partners"
                className="inline-flex h-10 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-semibold text-slate-300 hover:bg-white hover:text-black"
                aria-label="Partners"
                title="Partners"
              >
                <Handshake className="h-4 w-4 text-slate-300" />
                <span className="hidden sm:inline">Partners</span>
              </Link>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl px-5 py-12">
            <section className="mx-auto max-w-3xl text-center">
            <p className="text-sm font-medium text-slate-500">Shack 15</p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-6xl">
              Turn an idea into a hardware plan.
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-400">
              Upload a photo, sketch, or short description. Get parts, wiring, cost, and build steps.
            </p>

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
              <>
                <form onSubmit={handleGenerate} className="mt-8 border border-[#2c2f37] bg-[#17181d] p-3 text-left shadow-2xl shadow-black/30">
                  <div className="relative">
                    <textarea
                      value={prompt}
                      onChange={(event) => {
                        setGenerationInputNotice(null);
                        setPrompt(event.target.value);
                      }}
                      placeholder="Describe what you want to build, or upload an image."
                      aria-invalid={Boolean(visibleGenerationInputNotice)}
                      aria-describedby={visibleGenerationInputNotice ? "generation-input-notice" : undefined}
                      className="min-h-[138px] w-full resize-none bg-transparent p-4 pr-16 pb-16 text-sm leading-7 text-slate-100 outline-none placeholder:text-slate-600"
                    />
                    <button
                      type="submit"
                      disabled={isLoading || !hasGenerationInput}
                      className="absolute bottom-4 right-4 inline-flex h-10 w-10 items-center justify-center bg-white text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                      aria-label={generationInputValidation.isValid ? "Compile hardware" : "Check hardware idea"}
                      title={generationInputValidation.isValid ? "Compile hardware" : "Check hardware idea"}
                    >
                      {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                    </button>
                  </div>
                  {selectedImage && (
                    <div className="mb-3 flex items-center gap-3 border border-[#2c2f37] bg-black/30 p-2">
                      <img src={selectedImage} alt="Attached reference" className="h-16 w-24 object-cover" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold text-white">Image added</div>
                        <div className="mt-1 text-[11px] text-slate-500">Blueprint will use this image to understand the design.</div>
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
                      <span>{visibleGenerationInputNotice}</span>
                    </div>
                  )}
                  <div className="flex flex-col gap-3 border-t border-[#2c2f37] px-2 pt-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap items-center gap-2">
                      <input ref={fileInputRefCenter} type="file" accept="image/*" onChange={handleImageChange} className="hidden" />
                      <button
                        type="button"
                        onClick={() => fileInputRefCenter.current?.click()}
                        className="inline-flex h-10 w-10 items-center justify-center border border-[#2c2f37] text-slate-400 hover:bg-white hover:text-black"
                        title="Add image"
                      >
                        <Paperclip className="h-4 w-4" />
                      </button>
                      <div className="inline-flex h-10 max-w-full overflow-hidden border border-[#2c2f37]">
                        {generationWorkflows.map((workflow) => {
                          const selected = generationWorkflow === workflow.id;
                          const Icon = workflow.uses_firecrawl_mcp ? Sparkles : Database;
                          return (
                            <button
                              key={workflow.id}
                              type="button"
                              disabled={isLoading}
                              onClick={() => setGenerationWorkflow(workflow.id)}
                              className={`inline-flex min-w-0 items-center gap-2 border-r border-[#2c2f37] px-3 text-xs font-black uppercase last:border-r-0 ${
                                selected ? "bg-white text-black" : "bg-[#17181d] text-slate-400 hover:text-white"
                              } disabled:cursor-not-allowed disabled:opacity-50`}
                              title={workflow.description || workflow.label}
                              aria-pressed={selected}
                            >
                              <Icon className="h-4 w-4 shrink-0" />
                              <span className="truncate">{workflow.label}</span>
                            </button>
                          );
                        })}
                      </div>
                      <label className="inline-flex h-10 cursor-pointer items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase text-slate-400 hover:border-slate-500 hover:text-white">
                        <input
                          type="checkbox"
                          checked={generateProductImage}
                          onChange={(event) => setGenerateProductImage(event.target.checked)}
                          className="peer sr-only"
                        />
                        <Sparkles className={`h-4 w-4 ${generateProductImage ? "text-cyan-300" : "text-slate-500"}`} />
                        <span>Image model</span>
                        <span className={`h-4 w-7 border transition ${generateProductImage ? "border-cyan-300 bg-cyan-300" : "border-[#3a3d46] bg-black"}`}>
                          <span className={`block h-full w-3.5 bg-white transition ${generateProductImage ? "translate-x-3" : "translate-x-0"}`} />
                        </span>
                      </label>
                    </div>
                  </div>
                </form>

                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {samplePrompts.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => {
                        setGenerationInputNotice(null);
                        setPrompt(example);
                      }}
                      className="border border-[#2c2f37] bg-[#17181d] px-3 py-2 text-[11px] leading-5 text-slate-400 hover:border-slate-500 hover:text-white"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </>
            )}
          </section>

          <ProjectGallery
            sectionRef={projectsSectionRef}
            items={projectGalleryItems}
            onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
          />

          <section className="mt-8 grid gap-3 lg:grid-cols-[1.35fr_0.85fr]">

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
              compact
              onViewAllProjects={scrollToProjects}
            />
          </section>

          <section className="mx-auto mt-10 w-full max-w-6xl">
            <PartnerLogoMarquee partners={partners} hrefPrefix="/partners" />
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="h-[100dvh] w-full overflow-hidden bg-[#141519] text-slate-200">
      <div className="grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1fr)_280px]">
        <main className="flex min-h-0 min-w-0 flex-col">
          <header className="flex min-h-[78px] min-w-0 items-center gap-2 overflow-hidden border-b border-[#282a30] bg-[#17181d] px-3 sm:gap-3 sm:px-4">
            <button
              type="button"
              onClick={goHome}
              className="inline-flex h-11 shrink-0 items-center gap-2 border border-[#2a2c33] px-2 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black sm:px-3"
            >
              <ArrowLeft className="h-4 w-4" />
              <span className="hidden sm:inline">Home</span>
            </button>
            <input ref={fileInputRefVideo} type="file" accept="image/*" onChange={handleVideoImageChange} className="hidden" />

            <nav className="flex min-w-0 flex-1 overflow-x-auto border border-[#2a2c33]">
              {workspaceTabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`inline-flex h-11 min-w-12 items-center justify-center gap-2 border-r border-[#2a2c33] px-4 text-xs font-black uppercase tracking-widest transition last:border-r-0 ${
                      activeTab === tab.id ? "bg-white text-black" : "bg-[#17181d] text-slate-500 hover:text-white"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className={activeTab === tab.id ? "inline" : "hidden sm:inline"}>{tab.label}</span>
                  </button>
                );
              })}
            </nav>

          </header>

          <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
            {activeTab === "overview" && (
              <OverviewPanel
                title={projectTitle}
                description={projectDescription}
                imageCandidates={projectImageCandidates}
                features={imageFeatures}
                metrics={metrics}
                metadata={projectIR.assembly_metadata || {}}
              />
            )}

            {activeTab === "bom" && (
              <BomPanel
                components={components}
                metrics={metrics}
                cadSources={(projectIR.mechanical && Array.isArray(projectIR.mechanical.cad_sources)) ? projectIR.mechanical.cad_sources : []}
                fabricationCost={Number(projectIR.mechanical?.fabrication_cost_estimate_usd || 0)}
              />
            )}

            {activeTab === "mechanical" && (
              <MechanicalPanel
                toggles={mechToggles}
                setToggles={setMechToggles}
                electricalActive={mechElectricalActive}
                setElectricalActive={setMechElectricalActive}
                components={components}
                features={imageFeatures}
                metadata={projectIR.assembly_metadata || {}}
                mechanical={projectIR.mechanical || {}}
              />
            )}

            {activeTab === "schematic" && (
              <div className="h-full min-h-[560px] bg-[#f7f7f5]">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={schematicNodeTypes}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                  fitViewOptions={{ padding: 0.34 }}
                  className="bg-[#f7f7f5]"
                >
                  <Background color="#e7e9ef" gap={22} size={1} />
                  <Controls className="!border !border-[#d9dce3] !bg-white !text-[#202127]" />
                  <MiniMap className="!border !border-[#d9dce3] !bg-white" nodeStrokeColor="#94a3b8" nodeColor="#f8fafc" maskColor="rgba(255,255,255,0.62)" />
                  <SchematicLegend />
                </ReactFlow>
              </div>
            )}

            {activeTab === "assembly" && (
              <AssemblyPanel assembly={assembly} issues={issues} onDownload={downloadJSONIR} />
            )}

            {activeTab === "svg" && (
              <div className="h-full overflow-auto bg-[#141519] p-4 sm:p-6">
                <div className="schematic-svg-wrap mx-auto max-w-5xl border border-[#2a2c33] bg-[#17181d] p-3 sm:p-5" dangerouslySetInnerHTML={{ __html: svgSchematic }} />
              </div>
            )}

            {activeTab === "video" && (
              <VideoPanel
                projectId={currentProjectId}
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
                onGenerate={handleGenerateVideo}
                onUploadImage={() => fileInputRefVideo.current?.click()}
                onUseProjectImage={() => {
                  setVideoImageTouched(false);
                  const nextSource = videoImageOptions[0]?.src || defaultVideoImage;
                  setVideoImageInput(nextSource);
                  setSelectedVideoImageSources(nextSource ? [nextSource] : []);
                }}
                onRefreshGallery={() => {
                  if (currentProjectId) fetchProjectVideos(currentProjectId);
                }}
                canGenerate={Boolean(
                  videoGenerationConfig.configured !== false &&
                    currentProjectId &&
                    videoPrompt.trim() &&
                    selectedVideoModel &&
                    (videoMode === "video-to-video"
                      ? videoSourceVideoUrl.trim()
                      : selectedVideoImageSources.length > 0 || videoImageInput.trim())
                )}
              />
            )}

            {activeTab === "jobs" && (
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
            )}
          </section>
        </main>

        <PartsSidebar components={components} issues={issues} isValid={projectIR.is_valid} />
      </div>
    </div>
  );
}

export default BlueprintWorkspace;

function buildProjectGalleryItems(
  projectHistory: any[],
  projectImages: Record<string, ProjectImageCandidate | null>
): ProjectGalleryItem[] {
  return projectHistory
    .filter((project: any) => project?.project_id)
    .map((project: any) => {
      const projectId = String(project.project_id);
      return {
        key: projectId,
        title: project.title || "Untitled project",
        projectId,
        image: projectImages[projectId] || null,
      };
    });
}

function ProjectGallery({
  sectionRef,
  items,
  onOpenProjectPage,
}: {
  sectionRef: React.RefObject<HTMLElement>;
  items: ProjectGalleryItem[];
  onOpenProjectPage: (projectId: string) => void;
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
    <section ref={sectionRef} id="all-projects" className="mt-16 border-t border-[#292b31] pt-12">
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
  onOpenProjectPage,
}: {
  item: ProjectGalleryItem;
  onOpenProjectPage: () => void;
}) {
  return (
    <article className="group overflow-hidden border border-[#2c2f37] bg-[#17181d]">
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

      <div className="flex min-h-[112px] flex-col justify-between gap-4 p-4">
        <h3 className="line-clamp-2 min-h-10 break-words text-sm font-black uppercase leading-5 tracking-[0.08em] text-white">
          {item.title}
        </h3>
        <button
          type="button"
          onClick={onOpenProjectPage}
          className="inline-flex h-10 w-full items-center justify-between gap-2 border border-[#2a2c33] px-4 text-xs font-black uppercase text-white transition hover:bg-white hover:text-black sm:w-fit sm:justify-center"
        >
          Project page
          <ArrowRight className="h-4 w-4" />
        </button>
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

function SchematicLegend() {
  const nodeRows = [
    ["MCU", schematicTones.microcontroller],
    ["SENSOR", schematicTones.sensor],
    ["ACTUATOR", schematicTones.actuator],
    ["POWER", schematicTones.power],
    ["MODULE", schematicTones.passives],
    ["DISPLAY", schematicTones.display],
  ] as const;

  const wireRows = [
    { label: "DATA", color: "#22c55e", dash: "none" },
    { label: "POWER", color: "#f5a400", dash: "5 5" },
    { label: "GROUND", color: "#94a3b8", dash: "8 6" },
  ];

  return (
    <div className="pointer-events-none absolute bottom-5 left-5 z-10 w-[184px] border border-[#d9dce3] bg-white px-6 py-6 shadow-[0_18px_45px_rgba(15,23,42,0.14)]">
      <div className="text-[21px] font-black uppercase tracking-[0.2em] text-[#202127]">Schematic</div>
      <div className="mt-4 border-t border-[#d9dce3] pt-4 text-[12px] font-black uppercase tracking-[0.2em] text-[#777b86]">Node Types</div>
      <div className="mt-4 space-y-3">
        {nodeRows.map(([label, tone]) => (
          <div key={label} className="flex items-center gap-3 text-[18px] font-black uppercase tracking-[0.08em]" style={{ color: tone.text }}>
            <Eye className="h-4 w-4" />
            <span>{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 border-t border-[#d9dce3] pt-4 space-y-3">
        {wireRows.map((wire) => (
          <div key={wire.label} className="flex items-center gap-3 text-[18px] font-black uppercase tracking-[0.08em]" style={{ color: wire.color }}>
            <Eye className="h-4 w-4" />
            <svg width="40" height="8" viewBox="0 0 40 8" aria-hidden="true">
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

function BomPanel({ components, metrics, cadSources = [], fabricationCost = 0 }: { components: any[]; metrics: ReturnType<typeof emptyMetrics>; cadSources?: any[]; fabricationCost?: number }) {
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
                      <span key={source.label} className={`${source.className} inline-flex justify-center px-2 py-1 text-[10px] font-black italic text-black`}>
                        {source.label}
                      </span>
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
                    <span key={source.label} className={`${source.className} inline-flex min-w-[86px] justify-center px-3 py-2 text-xs font-black italic text-black`}>
                      {source.label}
                    </span>
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
          {cadSources.length ? cadSources.slice(0, 3).map((source: any) => (
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
      <div className="absolute inset-0 opacity-90" style={{
        backgroundImage:
          "linear-gradient(#252933 1px, transparent 1px), linear-gradient(90deg, #252933 1px, transparent 1px)",
        backgroundSize: "44px 44px",
        transform: "perspective(760px) rotateX(62deg) translateY(130px)",
        transformOrigin: "center 65%",
      }} />

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

function AssemblyPanel({ assembly, issues, onDownload }: { assembly: any[]; issues: any[]; onDownload: () => void }) {
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 border-b border-[#2a2c33] pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-black uppercase tracking-[0.12em] text-white sm:text-xl sm:tracking-[0.18em]">Build Instructions</h2>
          <p className="mt-2 text-xs text-slate-500">Sequential assembly from the generated hardware graph.</p>
        </div>
        <button onClick={onDownload} className="flex shrink-0 items-center justify-center gap-2 border border-[#2a2c33] px-4 py-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black">
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
  onGenerate,
  onUploadImage,
  onUseProjectImage,
  onRefreshGallery,
  canGenerate,
}: {
  projectId: string | null;
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
  onGenerate: () => void;
  onUploadImage: () => void;
  onUseProjectImage: () => void;
  onRefreshGallery: () => void;
  canGenerate: boolean;
}) {
  const modeModels = models.filter((model) => model.mode === mode);
  const sourceVideos = gallery
    .map((video, index) => ({
      video,
      url: videoSourceUrl(video),
      label: video.metadata?.requestId || video.key?.split("/").pop() || `Video ${index + 1}`,
    }))
    .filter((item) => item.url);
  const videoToVideoAvailable = sourceVideos.length > 0;
  const selectedImagePreviewSource = selectedImageSources[0] || imageInput;
  const imagePreview = mode === "image-to-video" ? previewableImageSrc(selectedImagePreviewSource) : null;
  const sourceVideoPreview = mode === "video-to-video" ? sourceVideoUrl : "";
  const isGenerating = status === "loading" || Boolean(requestId && !storedVideo && !isFinalVideoStatus(status));
  const generateDisabled = !canGenerate || isGenerating || !modeModels.length;
  const savedHref = storedVideo?.publicUrl || null;
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
            <div className="border-b border-[#2a2c33] pb-5">
              <div className="flex items-center gap-2">
                <Film className="h-4 w-4 text-cyan-400" />
                <h2 className="text-base font-black uppercase tracking-[0.16em] text-white">Video</h2>
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-slate-600">{projectId || "No project id"}</div>
            </div>

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

            <VideoGallery
              videos={gallery}
              loading={galleryLoading}
              error={galleryError}
              onRefresh={onRefreshGallery}
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
            <button
              type="button"
              onClick={onGenerate}
              disabled={generateDisabled}
              className="inline-flex h-11 shrink-0 items-center justify-center gap-2 bg-white px-4 text-xs font-black uppercase tracking-[0.12em] text-black transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isGenerating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
              Generate
            </button>
          </div>

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

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_170px_180px]">
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

          <label className="mt-5 block text-xs font-black uppercase tracking-[0.14em] text-slate-500">
            Prompt
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Slow orbit, reveal ports, show display glow."
              className="mt-2 min-h-[132px] w-full resize-none border border-[#2a2c33] bg-black px-3 py-3 text-sm normal-case leading-6 tracking-normal text-white outline-none placeholder:text-slate-700 focus:border-cyan-300"
            />
          </label>

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

function VideoGallery({
  videos,
  loading,
  error,
  onRefresh,
}: {
  videos: StoredVideoInfo[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
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
          className="flex h-9 w-9 shrink-0 items-center justify-center border border-[#2a2c33] text-slate-400 hover:bg-white hover:text-black"
          title="Refresh gallery"
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
          {videos.map((video) => (
            <VideoGalleryItem key={video.key || video.s3Uri || video.url || video.publicUrl || video.signedUrl} video={video} />
          ))}
        </div>
      ) : (
        <div className="border border-[#2a2c33] bg-black p-4 text-xs font-bold uppercase tracking-[0.12em] text-slate-600">
          Empty
        </div>
      )}
    </div>
  );
}

function VideoGalleryItem({ video }: { video: StoredVideoInfo }) {
  const playableUrl = video.url || video.publicUrl || video.signedUrl || null;
  const openUrl = playableUrl || null;
  const label = video.metadata?.requestId || video.key?.split("/").pop() || "video";

  return (
    <article className="min-w-0 overflow-hidden border border-[#2a2c33] bg-black">
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
        <div className="truncate font-mono text-[11px] text-slate-400">{label}</div>
        {video.key && <div className="mt-2 break-all font-mono text-[10px] leading-4 text-slate-600">{video.key}</div>}
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-600">{formatBytes(video.sizeBytes || 0)}</span>
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
    </article>
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
}) {
  const visibleJobs = compact ? jobs.slice(0, 2) : jobs;
  const filters = ["all", "queued", "running", "succeeded", "failed"];
  const panelDescription = description || `A2A job metadata from SQLite. Polling every ${Math.round(pollIntervalMs / 1000)}s.`;

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
          {onViewAllProjects && <span className="text-slate-500 group-hover:text-black">View projects</span>}
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
  const isOpenable = Boolean(project?.project_id);

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
          Open
        </button>
      </div>

      {!compact && (
        <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-7">
          <JobMetric label="Job" value={job.job_id} />
          <JobMetric label="Created" value={formatJobTime(job.created_at)} />
          <JobMetric label="Duration" value={formatJobDuration(job)} />
          <JobMetric label="Source" value={sourceLabel} />
          <JobMetric label="Parts" value={summary.component_count ?? "-"} />
          <JobMetric label="Valid" value={summary.is_valid === undefined ? "-" : summary.is_valid ? "yes" : "no"} />
          <JobMetric label="Image" value={summary.has_product_image ? summary.product_image_model || "yes" : "-"} />
        </div>
      )}

      {job.error && (
        <div className="mt-3 break-words border border-rose-500/30 bg-rose-950/20 p-3 text-xs leading-5 text-rose-300">
          {job.error}
        </div>
      )}
    </article>
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
  const webResearch = Boolean(sourceUsage.web_research || sourceUsage.firecrawl || sourceUsage.used_web_research || workflow === "web_research" || workflow === "firecrawl");
  const sourceLabels = Array.isArray(sourceUsage.source_labels)
    ? sourceUsage.source_labels.filter((label: any) => typeof label === "string" && label.trim())
    : [];
  const labels = sourceLabels.length ? sourceLabels : [
    ...(catalog ? ["Catalog"] : []),
    ...(webResearch ? ["Web Research"] : []),
  ];
  return {
    ...sourceUsage,
    workflow,
    catalog,
    web_research: webResearch,
    firecrawl: Boolean(sourceUsage.firecrawl || webResearch),
    source_labels: labels,
  };
}

function formatSourceUsageLabel(sourceUsage: Record<string, any>) {
  const labels = Array.isArray(sourceUsage.source_labels) ? sourceUsage.source_labels : [];
  return labels.length ? labels.join(" + ") : "-";
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
  if (status === "running") return "border-cyan-500/30 bg-cyan-950/25 text-cyan-300";
  if (status === "queued") return "border-amber-500/30 bg-amber-950/25 text-amber-300";
  return "border-slate-500/30 bg-slate-900 text-slate-300";
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
  const start = new Date(job.started_at).getTime();
  const end = new Date(job.completed_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "-";
  const seconds = Math.max(1, Math.round((end - start) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
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

function getSourcesForComponent(component: any) {
  const category = component.category?.toLowerCase();
  if (category === "actuator") {
    return [
      { label: "AliExpress", className: "bg-orange-600" },
      { label: "amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
    ];
  }
  if (category === "power" && component.name?.toLowerCase().includes("charger")) {
    return [
      { label: "amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
    ];
  }
  return [{ label: component.category?.toLowerCase() === "mechanical" || component.category?.toLowerCase() === "3d print" ? "fabricate" : "eBay", className: "bg-blue-600 text-white" }];
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
