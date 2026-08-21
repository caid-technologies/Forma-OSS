"use client";

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import {
  generationLlmImageSupport,
  generationLlmKey,
  type GenerationLlmOption,
  shouldShowProductImageSection,
} from "../lib/active-llms";
import { buildProjectDocsMarkdown, docsExportFilename } from "../lib/docs-export";
import { usableRuntimeLlmOptions, webConfig, type RuntimeConfigContract } from "../lib/config";
import { calculateProjectCostMetrics, resolveProjectComponentInstances } from "../lib/project-cost-metrics";
import { useFormaAuth } from "../lib/forma-auth";
import {
  isAuthOrSecurityHttpStatus,
  workspaceStatusBadge,
} from "../lib/connection-status";
import {
  useAdminSession,
  useBackendLogs,
  useJobs,
  type A2AJob,
} from "./forma-workspace/use-admin-data";
import { useDeferredTask } from "./forma-workspace/use-deferred-task";
import {
  useVideoModels,
  type VideoGenerationMode,
} from "./forma-workspace/use-video-models";
import {
  useProjectVideo,
} from "./forma-workspace/use-project-video";
import {
  JobsPanel,
  LogsPanel,
} from "./forma-workspace/admin-panels";
import HomeChatView from "./forma-workspace/home-chat-view";
import useChromeHeaderScroll from "./forma-workspace/use-chrome-header-scroll";
import {
  hardwareReferenceSrcFromChatMessages,
  isHardwareReferenceCandidate,
  resolveProjectImageCandidates,
  withHardwareReferenceMetadata,
  type ProjectImageCandidate,
} from "../lib/project-images";
import {
  ProjectGallery,
  PROJECT_GALLERY_PAGE_SIZE,
  buildProjectGalleryItems,
  type ProjectGalleryItem,
} from "./forma-workspace/project-gallery";
import {
  EditableWorkspaceTitle,
  MobileWorkspaceBar,
  type ChatListItem,
} from "./forma-workspace/sidebar";
import { WorkspaceSidebarShell } from "./forma-workspace/workspace-sidebar-shell";
import { ProjectTabContent } from "./forma-workspace/project-tab-content";
import { ChatWorkspace, ChatProjectArtifact, ProjectDetailWorkspace } from "./forma-workspace/project-workspace";
import { AgentPipelineProgressView } from "./forma-workspace/pipeline-progress-view";
import {
  AuthRequiredRouteScreen,
  ChatRouteFallbackPanel,
  ProjectDeletionDialog,
  ProjectRouteFallbackPanel,
  WorkspaceChromeIdentity,
  WorkspacePageHeading,
} from "./forma-workspace/route-shell-ui";
import { useContextBuildController } from "./forma-workspace/use-context-build-controller";
import type {
  ActiveGenerationRun,
  ActiveGenerationState,
  AgentPipelineProgress,
  AgentPipelineStep,
  ChatMessage,
  ChatRouteTransition,
  GenerationWorkflowOption,
  HomeProps,
  ImageGenerationConfig,
  PendingProjectDeletion,
  ProviderSetupState,
  VideoGenerationConfig,
} from "./forma-workspace/types";
import {
  ACTIVE_JOB_PROGRESS_POLL_INTERVAL_MS,
  DEFAULT_WORKFLOW_ID,
  defaultAgentPipelineSteps,
  defaultGenerationWorkflows,
  generationLlmLabel,
  JOB_POLL_INTERVAL_MS,
  LOG_POLL_INTERVAL_MS,
  MAX_CHAT_INDEX_ITEMS,
  MAX_PROJECT_CHAT_MESSAGES,
  NEW_PROJECT_TITLE,
  RECOVERY_JOB_BATCH_SIZE,
  RECOVERY_JOB_MAX_BACKOFF_MS,
  samplePrompts,
  WEB_RESEARCH_WORKFLOW_ID,
} from "./forma-workspace/workspace-constants";
import { API_URL, DEFAULT_SHOW_DEVELOPER_TOOLS, downloadBrowserFile } from "./forma-workspace/workspace-api";
import { readApiError, readApiErrorMessage } from "./forma-workspace/lib/api-errors";
import {
  createAgentPipelineProgress,
  isCompletedPipelineStatus,
  mergeMessagePipelineProgressFromJob,
  mergeMessagesWithJobs,
  normalizeAgentPipelineEvents,
  normalizeAgentPipelineSteps,
  patchChangesMessage,
  pipelineEventCursor,
  sameAgentPipelineProgress,
  terminalJobMessagePatch,
  compactDiagnosticText,
  advancePipelineMessages,
} from "./forma-workspace/lib/agent-pipeline";
import {
  chatHasStarted,
  chatIsWaiting,
  chatMessageIdentityKey,
  chatTitleFromMessages,
  initialProjectChatMessages,
  hydrateRoutedChatMessages,
  mergeFetchedChatMessages,
  messagesWithoutMissingProject,
  persistableChatMessages,
  normalizeChatMessage,
} from "./forma-workspace/lib/chat-normalize";
import {
  chatTimestamp,
  formatChatTimestamp,
  initialChatMessages,
  newBuildChatId,
  newChatMessageId,
} from "./forma-workspace/lib/chat-ids";
import {
  readPinnedChatIds,
  readStoredChatIndex,
  readStoredChatThread,
  removeStoredChatThread,
  writePinnedChatIds,
  writeStoredChatIndex,
  writeStoredChatThread,
  normalizeChatListItem,
} from "./forma-workspace/lib/chat-storage";
import {
  buildChatListItems,
  latestChatListItemDate,
  mergeChatListItems,
  mergeProjectRecords,
  normalizePrivateChatItems,
  normalizeProjectHistoryRecord,
  normalizeProjectListPage,
  projectRecordsFromChatItems,
  sameStringList,
  sortChatListItems,
  upsertChatListItem,
} from "./forma-workspace/lib/chat-list";
import { validateGenerationInput } from "./forma-workspace/lib/generation-input";
import {
  chatRoute,
  normalizeTab,
  projectRoute,
  safeDecodeChatId,
  safeDecodeProjectId,
  workspaceNamespaceForTab,
  workspaceTabMeta,
  workspaceTabs,
} from "./forma-workspace/lib/workspace-routes";
import {
  canChatWithProjectIR,
  chatIdFromIR,
  chatIdFromJob,
  formatDurationSeconds,
  projectIdFromIR,
  withProjectResponseMetadata,
} from "./forma-workspace/lib/project-metadata";
import {
  Database,
  Handshake,
  History,
  Layers,
  MessageSquare,
  Settings,
  Terminal,
} from "lucide-react";

const SchematicCanvas = dynamic(() => import("../components/schematic-canvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[620px] items-center justify-center bg-[var(--forma-page)] text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
      Loading wiring diagram...
    </div>
  ),
});

const UserIntegrationsPage = dynamic(() => import("./user/user-integrations-page"), {
  ssr: false,
  loading: () => (
    <div className="rounded-xl border border-white/5 bg-[#181b22] p-6 text-sm text-zinc-400">
      Loading settings...
    </div>
  ),
});

const AboutView = dynamic(() => import("./forma-workspace/about-view"), {
  loading: () => (
    <div className="rounded-xl border border-white/5 bg-[#181b22] p-6 text-sm text-zinc-400">
      Loading about...
    </div>
  ),
});

const VideoPanel = dynamic(
  () => import("./forma-workspace/video-panel").then((mod) => mod.VideoPanel),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[320px] items-center justify-center bg-[var(--forma-page)] text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
        Loading media...
      </div>
    ),
  },
);

let lastKnownServerStatus: "connected" | "disconnected" | null = null;

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
  const [chatThreads, setChatThreads] = useState<Record<string, ChatMessage[]>>({});
  const [projectChatInput, setProjectChatInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeGeneration, setActiveGeneration] = useState<ActiveGenerationState | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [projectIR, setProjectIR] = useState<any>(null);
  const [projectHistory, setProjectHistory] = useState<any[]>([]);
  const [myProjectHistory, setMyProjectHistory] = useState<any[]>([]);
  const [projectHistoryPage, setProjectHistoryPage] = useState(0);
  const [myProjectHistoryPage, setMyProjectHistoryPage] = useState(0);
  const [projectHistoryTotal, setProjectHistoryTotal] = useState(0);
  const [myProjectHistoryTotal, setMyProjectHistoryTotal] = useState(0);
  const [projectHistoryLoaded, setProjectHistoryLoaded] = useState(false);
  const [myProjectHistoryLoaded, setMyProjectHistoryLoaded] = useState(false);
  const [projectSearchInput, setProjectSearchInput] = useState("");
  const [projectSearchQuery, setProjectSearchQuery] = useState("");
  const [localChatItems, setLocalChatItems] = useState<ChatListItem[]>([]);
  const [privateChatItems, setPrivateChatItems] = useState<ChatListItem[]>([]);
  const [privateChatsLoaded, setPrivateChatsLoaded] = useState(false);
  const [chatIndexLoaded, setChatIndexLoaded] = useState(false);
  const [sessionChatItems, setSessionChatItems] = useState<ChatListItem[]>([]);
  const [pinnedChatIds, setPinnedChatIds] = useState<Set<string>>(new Set());
  const [projectGalleryImages, setProjectGalleryImages] = useState<Record<string, ProjectImageCandidate | null>>({});
  const [visibleProjectGalleryIds, setVisibleProjectGalleryIds] = useState<string[]>([]);
  const [routeProjectError, setRouteProjectError] = useState<string | null>(null);
  const [pendingProjectDeletion, setPendingProjectDeletion] = useState<PendingProjectDeletion | null>(null);
  const [deletionAcknowledged, setDeletionAcknowledged] = useState(false);
  const [contributeDeletedProject, setContributeDeletedProject] = useState(false);
  const [projectDeletionBusy, setProjectDeletionBusy] = useState(false);
  const [projectDeletionError, setProjectDeletionError] = useState<string | null>(null);
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
  const [authSecurityError, setAuthSecurityError] = useState(false);
  const [statusClockMs, setStatusClockMs] = useState(() => Date.now());
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [selectedImageSource, setSelectedImageSource] = useState<"upload" | "clipboard">("upload");
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
    requestCapable: null,
    provider: null,
    reason: null,
  });
  const [imageGenerationConfigLoaded, setImageGenerationConfigLoaded] = useState(false);
  const [providerSetup, setProviderSetup] = useState<ProviderSetupState>({
    llmRequired: false,
    imageRequired: false,
  });
  const [formaDevMode, setFormaDevMode] = useState(false);
  const [generateProductImage, setGenerateProductImage] = useState(false);
  const [generationWorkflow, setGenerationWorkflow] = useState(DEFAULT_WORKFLOW_ID);
  const [generationWorkflows, setGenerationWorkflows] = useState<GenerationWorkflowOption[]>(defaultGenerationWorkflows);
  const [agentPipelineSteps, setAgentPipelineSteps] = useState<AgentPipelineStep[]>(defaultAgentPipelineSteps);
  const [generationLlms, setGenerationLlms] = useState<GenerationLlmOption[]>([]);
  const [generationLlmKeyValue, setGenerationLlmKeyValue] = useState("");
  const [generationLlmsLoaded, setGenerationLlmsLoaded] = useState(false);
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
  const chatPersistenceTimersRef = useRef<Record<string, number>>({});
  const projectHistoryRequestIdRef = useRef(0);
  const projectHistoryAbortRef = useRef<AbortController | null>(null);
  const myProjectHistoryRequestIdRef = useRef(0);
  const myProjectHistoryAbortRef = useRef<AbortController | null>(null);
  const privateChatsAbortRef = useRef<AbortController | null>(null);
  const generationLlmRequestIdRef = useRef(0);
  const runtimeConfigAbortRef = useRef<AbortController | null>(null);
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
    () => sortChatListItems(
      buildChatListItems(visibleChatSourceProjects, visibleChatSourceItems).map((item) => ({
        ...item,
        pinned: pinnedChatIds.has(item.chatId),
      }))
    ),
    [pinnedChatIds, visibleChatSourceProjects, visibleChatSourceItems]
  );
  const projectGalleryItems = useMemo(
    () => buildProjectGalleryItems(
      projectHistory,
      projectGalleryImages,
      formaDevMode,
    ).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, formaDevMode, isSignedIn, projectHistory, projectGalleryImages]
  );
  const myProjectGalleryItems = useMemo(
    () => buildProjectGalleryItems(
      myProjectHistory,
      projectGalleryImages,
      formaDevMode,
    ).map((item) => ({
      ...item,
      canChat: item.canChat && (!authRequired || Boolean(isSignedIn)),
    })),
    [authRequired, formaDevMode, isSignedIn, myProjectHistory, projectGalleryImages]
  );
  const chatHistoryLoaded = myProjectHistoryLoaded && privateChatsLoaded;
  const projectsPageLoading = !projectHistoryLoaded;
  const myProjectsPageLoading = (authRequired && !authLoaded)
    || !myProjectHistoryLoaded;
  const handleVisibleProjectGalleryIdsChange = useCallback((projectIds: string[]) => {
    setVisibleProjectGalleryIds((current) => (
      sameStringList(current, projectIds) ? current : projectIds
    ));
  }, []);
  const handleProjectHistoryPageChange = useCallback((page: number) => {
    setProjectHistoryLoaded(false);
    setVisibleProjectGalleryIds([]);
    setProjectHistoryPage(page);
  }, []);
  const handleMyProjectHistoryPageChange = useCallback((page: number) => {
    setMyProjectHistoryLoaded(false);
    setVisibleProjectGalleryIds([]);
    setMyProjectHistoryPage(page);
  }, []);
  const inlineChatProjectId = useMemo(() => {
    const activeThread = activeChatId ? chatThreads[activeChatId] || [] : [];
    const messages = activeThread.length ? activeThread : chatMessages;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const projectId = messages[index]?.projectId;
      if (projectId) return projectId;
    }
    const completedWorkerBuild = messages.some((message) => (
      message.pipelineProgress?.jobId?.startsWith("generation-")
      && normalizeAgentPipelineEvents(message.pipelineProgress.events).some((event) => (
        event.step_id === "package_project" && isCompletedPipelineStatus(event.status)
      ))
    ));
    if (completedWorkerBuild && activeChatId) return activeChatId;
    return null;
  }, [activeChatId, chatMessages, chatThreads]);
  const generationInputValidation = useMemo(
    () => validateGenerationInput(prompt, Boolean(selectedImage)),
    [prompt, selectedImage]
  );
  const hasGenerationInput = Boolean(prompt.trim() || selectedImage);
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
  const needsGenerationProvider = generationLlmsLoaded && providerSetup.llmRequired && (!authRequired || authLoaded);
  const needsImageProvider = imageGenerationConfigLoaded && providerSetup.imageRequired && (!authRequired || authLoaded);
  const visibleContextInputNotice =
    generationInputNotice || ((prompt.trim() || selectedImage) && !generationInputValidation.isValid
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
      imagePreview: message.imagePreview || null,
      contextProjectId: message.contextProjectId || null,
      workflowState: message.workflowState || null,
      contextQuestions: message.contextQuestions || [],
      contextSuggestions: message.contextSuggestions || [],
      buildPlanId: message.buildPlanId || null,
      buildJobId: message.buildJobId || null,
      buildRequiresRequestBoundExecution: Boolean(message.buildRequiresRequestBoundExecution),
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
      imagePreview: message.imagePreview || null,
      contextProjectId: message.contextProjectId || null,
      workflowState: message.workflowState || null,
      contextQuestions: message.contextQuestions || [],
      contextSuggestions: message.contextSuggestions || [],
      buildPlanId: message.buildPlanId || null,
      buildJobId: message.buildJobId || null,
      buildRequiresRequestBoundExecution: Boolean(message.buildRequiresRequestBoundExecution),
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
      if (isSignedIn) setAuthSecurityError(true);
      throw new Error("Sign in to talk in chat and make projects.");
    }
    headers.Authorization = `Bearer ${token}`;
    return headers;
  }, [authRequired, getToken, isSignedIn, openSignIn]);

  const noteAuthResponseStatus = useCallback((status: number) => {
    if (isAuthOrSecurityHttpStatus(status)) setAuthSecurityError(true);
  }, []);

  const optionalAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (!isSignedIn) return {};
    try {
      const token = await getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, [getToken, isSignedIn]);

  const canInteractWithGallery = !authRequired || Boolean(isSignedIn);

  const patchProjectEngagement = useCallback((
    projectId: string,
    updates: { saved?: boolean; save_count?: number; remix_count?: number },
  ) => {
    const apply = (projects: any[]) => projects.map((project) => (
      project?.project_id === projectId ? { ...project, ...updates } : project
    ));
    setProjectHistory(apply);
    setMyProjectHistory(apply);
  }, []);

  const handleToggleProjectSave = useCallback(async (item: ProjectGalleryItem) => {
    if (!canInteractWithGallery) return;
    const nextSaved = !item.saved;
    const nextCount = Math.max(0, item.saveCount + (nextSaved ? 1 : -1));
    patchProjectEngagement(item.projectId, { saved: nextSaved, save_count: nextCount });
    try {
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(item.projectId)}/save`, {
        method: nextSaved ? "POST" : "DELETE",
        headers: await generationRequestHeaders(),
      });
      if (!response.ok) {
        noteAuthResponseStatus(response.status);
        throw new Error(await readApiErrorMessage(response));
      }
      const data = await response.json();
      patchProjectEngagement(item.projectId, {
        saved: Boolean(data.saved),
        save_count: Math.max(0, Number(data.save_count ?? nextCount)),
      });
    } catch (error) {
      patchProjectEngagement(item.projectId, { saved: item.saved, save_count: item.saveCount });
      console.error("Could not update project save", error);
    }
  }, [canInteractWithGallery, generationRequestHeaders, noteAuthResponseStatus, patchProjectEngagement]);

  const handleRemixProject = useCallback(async (item: ProjectGalleryItem) => {
    if (!canInteractWithGallery) return;
    try {
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(item.projectId)}/remix`, {
        method: "POST",
        headers: await generationRequestHeaders(),
      });
      if (!response.ok) {
        noteAuthResponseStatus(response.status);
        throw new Error(await readApiErrorMessage(response));
      }
      const data = await response.json();
      patchProjectEngagement(item.projectId, {
        remix_count: Math.max(0, Number(data.remix_count ?? item.remixCount + 1)),
      });
      if (data.project_id) {
        rememberProjectRecord({
          project_id: data.project_id,
          chat_id: data.chat_id || "",
          title: data.title || `${item.title} remix`,
          prompt: data.prompt || item.title,
          created_at: data.created_at || chatTimestamp(),
          can_chat: true,
          creator_display: "you",
          creator_image_url: userImageUrl,
          parts_count: item.partsCount,
          save_count: 0,
          remix_count: 0,
          saved: false,
        });
        router.push(projectRoute(String(data.project_id)));
      }
    } catch (error) {
      console.error("Could not remix project", error);
    }
  }, [canInteractWithGallery, generationRequestHeaders, noteAuthResponseStatus, patchProjectEngagement, router, userImageUrl]);

  const openProjectDeletion = useCallback((project: PendingProjectDeletion) => {
    setPendingProjectDeletion(project);
    setDeletionAcknowledged(false);
    setContributeDeletedProject(false);
    setProjectDeletionError(null);
  }, []);

  const closeProjectDeletion = useCallback(() => {
    if (projectDeletionBusy) return;
    setPendingProjectDeletion(null);
    setProjectDeletionError(null);
  }, [projectDeletionBusy]);

  const forgetChatRecords = (chatIds: string[]) => {
    if (!chatIds.length) return;
    const idSet = new Set(chatIds);
    chatIds.forEach((chatId) => {
      const existingTimer = chatPersistenceTimersRef.current[chatId];
      if (existingTimer) window.clearTimeout(existingTimer);
      delete chatPersistenceTimersRef.current[chatId];
      removeStoredChatThread(chatId, chatStorageScope);
    });
    setLocalChatItems((current) => {
      const nextItems = current.filter((item) => !idSet.has(item.chatId));
      writeStoredChatIndex(nextItems, chatStorageScope);
      return nextItems;
    });
    setPrivateChatItems((current) => current.filter((item) => !idSet.has(item.chatId)));
    setSessionChatItems((current) => current.filter((item) => !idSet.has(item.chatId)));
    setChatThreads((current) => {
      const next = { ...current };
      chatIds.forEach((chatId) => {
        delete next[chatId];
      });
      return next;
    });
    setPinnedChatIds((current) => {
      let changed = false;
      const next = new Set(current);
      chatIds.forEach((chatId) => {
        if (next.delete(chatId)) changed = true;
      });
      if (changed) writePinnedChatIds(next, chatStorageScope);
      return changed ? next : current;
    });
  };

  const confirmProjectDeletion = async () => {
    if (!pendingProjectDeletion || !deletionAcknowledged || projectDeletionBusy) return;
    setProjectDeletionBusy(true);
    setProjectDeletionError(null);
    const projectId = pendingProjectDeletion.projectId;
    try {
      const headers = await generationRequestHeaders();
      if (contributeDeletedProject) {
        const consentResponse = await fetch(
          `${API_URL}/projects/${encodeURIComponent(projectId)}/data-contribution-consent`,
          {
            method: "PUT",
            headers,
            body: JSON.stringify({
              granted: true,
              consent_version: "2026-07-31",
              permitted_purposes: ["product_research", "evaluation", "ai_system_improvement"],
            }),
          },
        );
        if (!consentResponse.ok) throw new Error(await readApiErrorMessage(consentResponse));
      }
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) throw new Error(await readApiErrorMessage(response));
      const relatedChatIds = chatListItems
        .filter((item) => item.projectId === projectId)
        .map((item) => item.chatId);
      setProjectHistory((projects) => projects.filter((project: any) => project?.project_id !== projectId));
      setMyProjectHistory((projects) => projects.filter((project: any) => project?.project_id !== projectId));
      setProjectGalleryImages((images) => {
        const next = { ...images };
        delete next[projectId];
        return next;
      });
      forgetChatRecords(relatedChatIds);
      relatedChatIds.forEach((chatId) => {
        void fetch(`${API_URL}/chats/${encodeURIComponent(chatId)}`, {
          method: "DELETE",
          headers,
        }).catch(() => {});
      });
      setPendingProjectDeletion(null);
      if (
        (currentRouteProjectId && safeDecodeProjectId(currentRouteProjectId) === projectId) ||
        (activeChatId && relatedChatIds.includes(activeChatId))
      ) {
        goHome();
      }
      void fetchProjectHistory();
      void fetchMyProjectHistory();
      void fetchPrivateChats();
    } catch (error) {
      setProjectDeletionError(error instanceof Error ? error.message : "Project deletion failed.");
    } finally {
      setProjectDeletionBusy(false);
    }
  };

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
    metrics: jobMetrics,
    metricsError: jobMetricsError,
    metricsWindow: jobMetricsWindow,
    setMetricsWindow: setJobMetricsWindow,
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
        const jobId = message.status === "loading" && !message.buildPlanId ? message.pipelineProgress?.jobId : null;
        if (jobId && !jobId.startsWith("generation-") && jobId !== activeGeneration?.jobId) jobIds.add(jobId);
      });
    };
    collect(chatMessages);
    Object.values(chatThreads).forEach(collect);
    return Array.from(jobIds).join("\n");
  }, [activeGeneration?.jobId, chatMessages, chatThreads]);

  const latestAgentOperation = useMemo(() => {
    return [...chatMessages].reverse().find((message) => (
      message.role === "assistant"
      && (message.status === "loading" || message.status === "success" || message.status === "error" || message.status === "cancelled")
    )) || null;
  }, [chatMessages]);

  useEffect(() => {
    if (latestAgentOperation?.status !== "loading") return;
    const intervalId = window.setInterval(() => setStatusClockMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [latestAgentOperation?.status]);

  const workspaceStatus = useMemo(() => {
    const progress = latestAgentOperation?.pipelineProgress;
    const events = progress?.events;
    const lastEvent = Array.isArray(events) && events.length ? events[events.length - 1] : null;
    return workspaceStatusBadge({
      connection: serverStatus,
      authError: authSecurityError,
      agent: latestAgentOperation
        ? {
            status: latestAgentOperation.status,
            content: latestAgentOperation.content,
            startedAt: progress?.startedAt || latestAgentOperation.timestamp,
            lastEventAt: lastEvent?.observed_at || progress?.uiUpdatedAt || null,
          }
        : null,
      nowMs: statusClockMs,
    });
  }, [authSecurityError, latestAgentOperation, serverStatus, statusClockMs]);


  const persistChatThread = (chatId: string | null, messages: ChatMessage[], explicitTitle?: string | null) => {
    if ((authRequired && !isSignedIn) || !chatId || typeof window === "undefined") return;
    const nextMessages = persistableChatMessages(messages);
    if (!chatHasStarted(nextMessages)) return;
    const listedTitle = chatListItems.find((item) => item.chatId === chatId)?.title?.trim() || "";
    const title = explicitTitle?.trim()
      || (listedTitle && listedTitle !== NEW_PROJECT_TITLE ? listedTitle : chatTitleFromMessages(nextMessages));
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

  const currentProjectChatHasStarted = () => {
    if (currentRouteProjectId) return true;
    const guardChatId = projectIR ? (chatIdFromIR(projectIR) || projectIdFromIR(projectIR) || activeChatId) : activeChatId;
    const guardMessages = projectIR && guardChatId ? chatThreads[guardChatId] || [] : chatMessages;
    const guardItem = chatListItems.find((item) => item.chatId === guardChatId);
    return Boolean(
      projectIR ||
      chatHasStarted(guardMessages) ||
      guardItem?.projectId ||
      guardItem?.projectCount
    );
  };

  const resetToNewProjectChat = () => {
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
    setGenerationInputNotice(null);
    setSelectedImage(null);
    setSelectedImageSource("upload");
    setChatRouteTransition(null);
    setProjectIR(null);
    setActiveTab("overview");
    return nextChatId;
  };

  const goHome = () => {
    if (currentProjectChatHasStarted()) {
      resetToNewProjectChat();
    } else {
      setChatRouteTransition(null);
      setProjectIR(null);
      setActiveTab("overview");
    }
    router.push("/");
  };

  const startNewProjectChat = () => {
    if (homeView === "chat" && !currentRouteProjectId && !currentProjectChatHasStarted()) return;
    const nextChatId = resetToNewProjectChat();
    router.push(chatRoute(nextChatId));
  };

  const openChatItem = (item: ChatListItem) => {
    if (authRequired && !isSignedIn) {
      openSignIn({ redirectUrl: typeof window !== "undefined" ? chatRoute(item.chatId) : "/" });
      return;
    }
    setActiveChatId(item.chatId);
    setActiveTab("overview");
    const storedMessages = readStoredChatThread(item.chatId, null, chatStorageScope);
    if (storedMessages.length) {
      setChatThreads((current) => ({ ...current, [item.chatId]: storedMessages }));
      setChatMessages(storedMessages);
    } else {
      setChatMessages(initialChatMessages());
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
    setActiveTab("overview");
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
    if (!chatId) return;
    const nextPath = chatRoute(chatId);
    if (typeof window !== "undefined" && window.location.pathname === nextPath) return;
    if (mode === "replace") {
      router.replace(nextPath);
    } else {
      router.push(nextPath);
    }
  };

  useLayoutEffect(() => {
    setLocalChatItems(authRequired ? [] : readStoredChatIndex(chatStorageScope));
    setPinnedChatIds(new Set(readPinnedChatIds(chatStorageScope)));
    setChatIndexLoaded(true);
    setChatMessages((current) => (
      current.length === 1 && current[0]?.id === "assistant-welcome"
        ? [{ ...current[0], timestamp: chatTimestamp() }]
        : current
    ));
  }, [authRequired, chatStorageScope]);

  useEffect(() => {
    return () => {
      privateChatsAbortRef.current?.abort();
      myProjectHistoryAbortRef.current?.abort();
      runtimeConfigAbortRef.current?.abort();
      projectHistoryAbortRef.current?.abort();
      pipelineStepsAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (homeView !== "projects") return;
    void fetchProjectHistory(projectHistoryPage, projectSearchQuery);
    // Public gallery data becomes critical only when its route is active.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeView, projectHistoryPage, projectSearchQuery]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const nextQuery = projectSearchInput.trim();
      if (nextQuery === projectSearchQuery) return;
      setProjectHistoryLoaded(false);
      setVisibleProjectGalleryIds([]);
      setProjectHistoryPage(0);
      setProjectSearchQuery(nextQuery);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [projectSearchInput, projectSearchQuery]);

  useDeferredTask(() => {
    if (!projectHistoryLoaded) void fetchProjectHistory(projectHistoryPage, projectSearchQuery);
  }, {
    delayMs: 1200,
    enabled: homeView !== "projects" && !projectHistoryLoaded,
    taskKey: `${homeView}:${projectHistoryPage}:${projectSearchQuery}`,
    timeoutMs: 1800,
  });

  useDeferredTask(() => {
    void checkServerStatus();
  }, { delayMs: 150, timeoutMs: 700 });

  useDeferredTask(() => {
    if (!authRequired) void fetchRuntimeConfig();
  }, { delayMs: 500, enabled: !authRequired, timeoutMs: 1100 });

  useEffect(() => {
    if (!authRequired || !authLoaded) return;
    generationLlmRequestIdRef.current += 1;
    setGenerationLlmsLoaded(false);
    setGenerationLlms([]);
    setGenerationLlmKeyValue("");
    setImageGenerationConfig({ configured: null, requestCapable: null, provider: null, reason: null });
    setImageGenerationConfigLoaded(false);
    setProviderSetup({ llmRequired: false, imageRequired: false });
    setAuthSecurityError(false);
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
      setPrivateChatsLoaded(false);
      return;
    }
    setMyProjectHistoryPage(0);
    setPrivateChatsLoaded(false);
    void fetchPrivateChats();
    return () => {
      privateChatsAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authIdentityKey, authLoaded, authRequired, isSignedIn]);

  useEffect(() => {
    if (authRequired && !authLoaded) {
      setMyProjectHistoryLoaded(false);
      return;
    }
    void fetchMyProjectHistory(myProjectHistoryPage);
    return () => {
      myProjectHistoryAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authIdentityKey, authLoaded, authRequired, isSignedIn, myProjectHistoryPage]);

  useDeferredTask(() => {
    void fetchAgentPipelineSteps(generationWorkflow);
  }, { delayMs: 1100, timeoutMs: 1400 });

  useEffect(() => {
    if (!pipelineStepsRequestStartedRef.current) return;
    if (pipelineStepsLastRequestedWorkflowRef.current === generationWorkflow) return;
    void fetchAgentPipelineSteps(generationWorkflow);
    // The first request is staged by useDeferredTask; later workflow changes
    // load immediately and cancel any response for the previous workflow.
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
    runtimeConfigAbortRef.current?.abort();
    const runtimeController = new AbortController();
    runtimeConfigAbortRef.current = runtimeController;
    try {
      const res = await fetch(`${API_URL}/runtime/config`, {
        cache: "no-store",
        signal: runtimeController.signal,
        headers: await optionalAuthHeaders(),
      });
      if (!res.ok) return;

      const config = (await res.json()) as RuntimeConfigContract;
      if (!requestIsCurrent()) return;
      setFormaDevMode(config.forma_dev_mode === true);
      const activeLlms = usableRuntimeLlmOptions(config);
      const selectedLlm = config.generation.selected_llm;
      const selectedLlmKey = selectedLlm ? generationLlmKey(selectedLlm) : "";
      setGenerationLlms(activeLlms);
      setGenerationLlmKeyValue(
        activeLlms.some((option) => generationLlmKey(option) === selectedLlmKey)
          ? selectedLlmKey
          : activeLlms[0]
            ? generationLlmKey(activeLlms[0])
            : "",
      );
      setProviderSetup({
        llmRequired: config.provider_setup.llm_required,
        imageRequired: config.provider_setup.image_required,
      });

      if (config.video?.generation) {
        setVideoGenerationConfig({
          configured: Boolean(config.video.generation.configured),
          reason: typeof config.video.generation.reason === "string" ? config.video.generation.reason : null,
        });
      }
      if (config.video?.self_correction) {
        setVideoSelfCorrectionConfig({
          configured: Boolean(config.video.self_correction.configured),
          reason: typeof config.video.self_correction.reason === "string" ? config.video.self_correction.reason : null,
        });
      }
      setImageGenerationConfig({
        configured: config.images.configured,
        requestCapable: config.images.request_capable,
        provider: config.images.provider,
        reason: config.images.reason,
      });
      setGenerateProductImage(config.images.generate_by_default);

      const workflows = Array.isArray(config.workflow.options) ? config.workflow.options : [];
      if (workflows.length > 0) {
        const nextWorkflow = workflows.some((workflow) => workflow.id === config.workflow.default_id)
          ? config.workflow.default_id
          : workflows[0].id;
        setGenerationWorkflows(workflows);
        setGenerationWorkflow(nextWorkflow);
      }
    } catch (e) {
      if (runtimeController.signal.aborted) return;
      if (requestIsCurrent()) console.error("Error fetching runtime config", e);
    } finally {
      if (requestIsCurrent()) {
        setGenerationLlmsLoaded(true);
        setImageGenerationConfigLoaded(true);
      }
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


  const fetchProjectHistory = async (
    page: number = projectHistoryPage,
    search: string = projectSearchQuery,
  ) => {
    const requestId = projectHistoryRequestIdRef.current + 1;
    projectHistoryRequestIdRef.current = requestId;
    projectHistoryAbortRef.current?.abort();
    const projectHistoryController = new AbortController();
    projectHistoryAbortRef.current = projectHistoryController;
    setProjectHistoryLoaded(false);
    try {
      const params = new URLSearchParams({
        limit: String(PROJECT_GALLERY_PAGE_SIZE),
        offset: String(Math.max(0, page) * PROJECT_GALLERY_PAGE_SIZE),
      });
      const normalizedSearch = search.trim();
      if (normalizedSearch) params.set("q", normalizedSearch);
      const res = await fetch(`${API_URL}/projects?${params.toString()}`, {
        signal: projectHistoryController.signal,
        headers: await optionalAuthHeaders(),
      });
      if (projectHistoryRequestIdRef.current !== requestId) return;
      if (res.ok) {
        const result = normalizeProjectListPage(await res.json());
        if (projectHistoryRequestIdRef.current !== requestId) return;
        setProjectHistory(result.items);
        setProjectHistoryTotal(result.total);
        if (!authRequired) {
          setLocalChatItems((current) => {
            const repairedItems = buildChatListItems(result.items, current);
            writeStoredChatIndex(repairedItems, chatStorageScope);
            return repairedItems;
          });
        }
      }
    } catch (e) {
      if (projectHistoryController.signal.aborted) return;
      console.error("Error fetching project history", e);
    } finally {
      if (projectHistoryRequestIdRef.current === requestId && !projectHistoryController.signal.aborted) {
        setProjectHistoryLoaded(true);
      }
    }
  };

  const fetchMyProjectHistory = async (page: number = myProjectHistoryPage) => {
    const requestId = myProjectHistoryRequestIdRef.current + 1;
    myProjectHistoryRequestIdRef.current = requestId;
    myProjectHistoryAbortRef.current?.abort();
    const myProjectHistoryController = new AbortController();
    myProjectHistoryAbortRef.current = myProjectHistoryController;
    if (authRequired && !authLoaded) {
      setMyProjectHistoryLoaded(false);
      return;
    }
    if (authRequired && !isSignedIn) {
      setMyProjectHistory([]);
      setMyProjectHistoryTotal(0);
      setMyProjectHistoryLoaded(true);
      return;
    }

    setMyProjectHistoryLoaded(false);
    try {
      const params = new URLSearchParams({
        limit: String(PROJECT_GALLERY_PAGE_SIZE),
        offset: String(Math.max(0, page) * PROJECT_GALLERY_PAGE_SIZE),
      });
      const res = await fetch(`${API_URL}/my/projects?${params.toString()}`, {
        signal: myProjectHistoryController.signal,
        headers: await generationRequestHeaders(),
      });
      if (myProjectHistoryRequestIdRef.current !== requestId) return;
      if (res.ok) {
        const result = normalizeProjectListPage(await res.json());
        if (myProjectHistoryRequestIdRef.current !== requestId) return;
        setMyProjectHistory(result.items);
        setMyProjectHistoryTotal(result.total);
        setAuthSecurityError(false);
      } else if (isAuthOrSecurityHttpStatus(res.status)) {
        if (isSignedIn) setAuthSecurityError(true);
        setMyProjectHistory([]);
        setMyProjectHistoryTotal(0);
      } else {
        throw new Error(await readApiErrorMessage(res));
      }
    } catch (e) {
      if (myProjectHistoryController.signal.aborted) return;
      console.error("Error fetching my project history", e);
    } finally {
      if (myProjectHistoryRequestIdRef.current === requestId && !myProjectHistoryController.signal.aborted) {
        setMyProjectHistoryLoaded(true);
      }
    }
  };

  const fetchPrivateChats = async () => {
    privateChatsAbortRef.current?.abort();
    const privateChatsController = new AbortController();
    privateChatsAbortRef.current = privateChatsController;
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
        signal: privateChatsController.signal,
        headers: await generationRequestHeaders(),
      });
      if (res.ok) {
        setAuthSecurityError(false);
        const chats = await res.json();
        setPrivateChatItems(normalizePrivateChatItems(chats));
        const threadUpdates: Record<string, ChatMessage[]> = {};
        if (Array.isArray(chats)) {
          chats.forEach((chat: any) => {
            const chatId = typeof chat?.chat_id === "string" ? chat.chat_id.trim() : "";
            const messages = persistableChatMessages(Array.isArray(chat?.messages) ? chat.messages : []);
            if (!chatId || !messages.length) return;
            threadUpdates[chatId] = messages;
          });
        }
        if (Object.keys(threadUpdates).length) {
          setChatThreads((current) => {
            const next = { ...current };
            Object.entries(threadUpdates).forEach(([chatId, remoteMessages]) => {
              const mergedMessages = mergeFetchedChatMessages(remoteMessages, current[chatId] || []);
              next[chatId] = mergedMessages;
              writeStoredChatThread(chatId, mergedMessages, chatStorageScope);
            });
            return next;
          });
          if (activeChatId && threadUpdates[activeChatId]) {
            setChatMessages((current) => mergeFetchedChatMessages(threadUpdates[activeChatId], current));
          }
        }
      } else if (isAuthOrSecurityHttpStatus(res.status)) {
        if (isSignedIn) setAuthSecurityError(true);
        setPrivateChatItems([]);
        setSessionChatItems([]);
      } else {
        throw new Error(await readApiErrorMessage(res));
      }
    } catch (e) {
      if (privateChatsController.signal.aborted) return;
      console.error("Error fetching private chats", e);
    } finally {
      if (!privateChatsController.signal.aborted) setPrivateChatsLoaded(true);
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
    if (!normalizeTab(activeTab)) setActiveTab("overview");
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
        }, formaDevMode)[0] || null;
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
          return [projectId, resolveProjectImageCandidates(data || {}, formaDevMode)[0] || null];
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
  }, [formaDevMode, chatListItems, currentRouteProjectId, myProjectHistory, optionalAuthHeaders, projectHistory, projectGalleryImages, projectIR, visibleProjectGalleryIds]);

  const attachImageFile = (file: File, source: "upload" | "clipboard" = "upload") => {
    if (!file.type.startsWith("image/")) {
      setGenerationInputNotice("Only image files can be attached as hardware references.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        setGenerationInputNotice("Forma could not read that image. Try another image format.");
        return;
      }
      setGenerationInputNotice(null);
      setSelectedImage(reader.result);
      setSelectedImageSource(source);
    };
    reader.onerror = () => {
      setGenerationInputNotice("Forma could not read that image. Try copying or uploading it again.");
    };
    reader.readAsDataURL(file);
  };

  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) attachImageFile(file, "upload");
  };

  const handleImagePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFile = Array.from(event.clipboardData.files).find((file) => file.type.startsWith("image/"))
      || Array.from(event.clipboardData.items)
        .find((item) => item.type.startsWith("image/"))
        ?.getAsFile();
    if (imageFile) attachImageFile(imageFile, "clipboard");
  };

  const removeSelectedImage = () => {
    setGenerationInputNotice(null);
    setSelectedImage(null);
    setSelectedImageSource("upload");
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

  const cancelContextBuildRef = useRef<(projectId: string, planId: string) => Promise<void> | void>(async () => {});

  const stopActiveGeneration = () => {
    const run = activeGenerationRef.current;
    if (!run) return;

    run.cancelled = true;
    run.controller.abort();
    if (run.assistantMessageId) {
      const patch: Partial<Omit<ChatMessage, "id">> = {
        content: run.kind === "context-build"
          ? "Build stopped by you. Your project brief is preserved."
          : "Generation stopped by you.",
        status: "cancelled",
      };
      if (run.kind !== "project-chat") updateChatMessage(run.assistantMessageId, patch);
      updateThreadMessage(run.chatId, run.assistantMessageId, patch);
    }
    setGenerationInputNotice(
      run.kind === "context-build"
        ? "Build stopped. Your project brief is preserved."
        : "Generation stopped. You can send another message whenever you're ready.",
    );
    if (run.kind === "context-build" && run.projectId && run.planId) {
      void cancelContextBuildRef.current(run.projectId, run.planId);
    } else if (run.jobId) {
      void cancelGenerationJob(run.jobId);
    }
    finishGenerationRun(run);
  };

  const contextBuild = useContextBuildController({
    activeChatId,
    setActiveChatId,
    chatMessages,
    chatThreads,
    prompt,
    setPrompt,
    selectedImage,
    setSelectedImage,
    selectedImageSource,
    setSelectedImageSource,
    generateProductImage,
    authRequired,
    isSignedIn,
    userImageUrl,
    generationRequestHeaders,
    optionalAuthHeaders,
    requireSignedInForGeneration,
    noteAuthResponseStatus,
    appendChatMessage,
    updateChatMessage,
    appendThreadMessage,
    updateThreadMessage,
    applyChatPipelineProgressFromJob,
    applyThreadPipelineProgressFromJob,
    rememberChatItem,
    rememberProjectRecord,
    setProjectIR,
    setGenerationInputNotice,
    setIsLoading,
    activeGenerationRef,
    beginGenerationRun,
    finishGenerationRun,
    setGenerationRunJob,
    stopActiveGeneration,
    syncChatRoute,
    fetchProjectHistory,
    fetchMyProjectHistory,
  });
  const {
    contextWorkflowStates,
    contextBuildStarting,
    contextSubmitting,
    resettingBuildMessageId,
    pendingContextBuildMessage,
    retryableContextBuildMessage,
    submitGatherContext,
    handleGatherContext,
    handleBuildNow,
    resetFailedContextBuild,
    stopContextBuildMessage,
  } = contextBuild;
  cancelContextBuildRef.current = contextBuild.cancelContextBuild;

  const handleProjectChatGenerate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (activeGenerationRef.current) return;
    if (!(await requireSignedInForGeneration())) return;
    if (!currentUserOwnsProject) {
      setGenerationInputNotice("You can only chat with projects you own.");
      return;
    }
    if (!selectedGenerationLlm) {
      setGenerationInputNotice("Turn on at least one model provider in Settings before changing this project.");
      return;
    }
    if (!currentProjectId || !projectIR) return;

    const userMessage = projectChatInput.trim();
    if (!userMessage) return;

    const sourceProjectId = currentProjectId;
    const sourceChatId = currentProjectChatId || activeChatId || newBuildChatId();
    const targetNamespace = activeTab === "overview" ? null : workspaceNamespaceForTab(activeTab);
    const generationRun = beginGenerationRun("project-chat", sourceChatId);
    setActiveChatId(sourceChatId);
    rememberChatItem({
      chatId: sourceChatId,
      title: projectTitle || userMessage,
      projectId: sourceProjectId,
      createdAt: chatTimestamp(),
      projectCount: 1,
    });
    appendThreadMessage(sourceChatId, {
      role: "user",
      content: userMessage,
      status: "idle",
      projectId: sourceProjectId,
    });
    const assistantMessageId = appendThreadMessage(sourceChatId, {
      role: "assistant",
      content: `Applying your change to ${projectTitle}.`,
      status: "loading",
      projectId: sourceProjectId,
    });
    generationRun.assistantMessageId = assistantMessageId;

    setProjectChatInput("");
    setGenerationInputNotice(null);
    checkServerStatus();

    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(sourceProjectId)}/iterate`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        signal: generationRun.controller.signal,
        body: JSON.stringify({
          instruction: userMessage,
          namespace: targetNamespace,
          provider: selectedGenerationLlm.provider,
          model: selectedGenerationLlm.model,
          save: true,
        }),
      });

      if (!res.ok) {
        noteAuthResponseStatus(res.status);
        const apiError = await readApiError(res);
        if (apiError.debug) {
          console.error("Forma API debug trace", apiError);
        }
        throw new Error(compactDiagnosticText(apiError.message) || apiError.message);
      }

      const data = await res.json();
      const ir = withProjectResponseMetadata(data.project_ir, {
        ...data,
        project_id: sourceProjectId,
        chat_id: sourceChatId,
        can_chat: true,
      });
      const responseProjectId = projectIdFromIR(ir);
      if (responseProjectId !== sourceProjectId) {
        throw new Error("Project iteration returned a different project ID.");
      }
      setProjectIR(ir);
      setActiveChatId(sourceChatId);
      rememberProjectRecord({
        project_id: sourceProjectId,
        chat_id: sourceChatId,
        title: ir?.overview?.title || projectTitle || userMessage,
        prompt: data.prompt || ir?.assembly_metadata?.source_prompt || projectTitle,
        created_at: data.created_at || chatTimestamp(),
        can_chat: true,
        creator_display: "you",
        creator_image_url: userImageUrl,
        parts_count: Array.isArray(ir?.components) ? ir.components.length : 0,
        save_count: 0,
        remix_count: 0,
        saved: false,
      });
      const revision = data?.iteration?.revision || ir?.assembly_metadata?.revision;
      const successMessage = `${ir?.overview?.title || "Project"} was updated${revision ? ` to revision ${revision}` : ""}.`;
      rememberChatItem({
        chatId: sourceChatId,
        title: ir?.overview?.title || projectTitle || userMessage,
        projectId: sourceProjectId,
        createdAt: chatTimestamp(),
        projectCount: 1,
      });

      updateThreadMessage(sourceChatId, assistantMessageId, {
        content: successMessage,
        status: "success",
        projectId: sourceProjectId,
      });

      refreshProjectAndChatLists();
    } catch (error) {
      if (generationRun.cancelled || (error instanceof Error && error.name === "AbortError")) {
        updateThreadMessage(sourceChatId, assistantMessageId, {
          content: "Project update stopped by you.",
          status: "cancelled",
        });
        return;
      }
      const message = error instanceof Error ? error.message : "Project update failed.";
      updateThreadMessage(sourceChatId, assistantMessageId, {
        content: message,
        status: "error",
      });
    } finally {
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

  const loadOldProject = async (
    projectId: string,
    options: { syncRoute?: boolean; signal?: AbortSignal; tab?: string | null; hydrateChat?: boolean } = {}
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
      if (options.hydrateChat && canChatWithProjectIR(ir)) {
        ensureChatThread(projectId, ir, data.prompt);
      }
      setActiveTab(normalizeTab(options.tab || "") || "overview");
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

  const loadedProjectId = projectIdFromIR(projectIR);

  useEffect(() => {
    if (currentRouteProjectId || homeView !== "chat" || !inlineChatProjectId || loadedProjectId === inlineChatProjectId) return;

    const controller = new AbortController();
    let retryTimer: number | null = null;
    let attempt = 0;
    const maxAttempts = 10;

    const hydrateInlineProject = async () => {
      attempt += 1;
      try {
        const res = await fetch(`${API_URL}/projects/${encodeURIComponent(inlineChatProjectId)}`, {
          signal: controller.signal,
          headers: await optionalAuthHeaders(),
        });
        if (!res.ok) throw new Error(`Project output is not available yet (${res.status}).`);

        const data = await res.json();
        if (controller.signal.aborted) return;
        const ir = withProjectResponseMetadata(data.project_ir, data);
        setProjectIR(ir);
        if (canChatWithProjectIR(ir)) {
          ensureChatThread(inlineChatProjectId, ir, data.prompt);
        }
        setActiveTab("overview");
      } catch (error) {
        if (controller.signal.aborted) return;
        if (attempt < maxAttempts) {
          const retryDelayMs = Math.min(500 * (2 ** (attempt - 1)), 5000);
          retryTimer = window.setTimeout(hydrateInlineProject, retryDelayMs);
          return;
        }
        console.error("Could not hydrate inline project output", error);
      }
    };

    void hydrateInlineProject();
    return () => {
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
    // The project id and loaded project identity fully define this hydration request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRouteChatId, currentRouteProjectId, homeView, inlineChatProjectId, loadedProjectId]);

  const routedProjectId = currentRouteProjectId ? safeDecodeProjectId(currentRouteProjectId) : "";

  useEffect(() => {
    if (!routedProjectId) {
      setRouteProjectError(null);
      return;
    }
    if (authRequired && !authLoaded) return;

    const controller = new AbortController();
    const projectId = routedProjectId;
    const tab = normalizeTab(new URLSearchParams(window.location.search).get("tab"));
    setChatRouteTransition(null);
    setRouteProjectError(null);

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
  }, [routedProjectId, authIdentityKey, authLoaded, authRequired, isSignedIn]);

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
    setActiveTab("overview");
    setRouteProjectError(null);
    const alreadyShowingThisChat = activeChatId === chatId;
    setChatThreads((current) => {
      const existing = current[chatId] || [];
      const merged = hydrateRoutedChatMessages(storedMessages, existing, { sameChat: true });
      if (!merged.length) return current;
      return { ...current, [chatId]: merged };
    });
    setChatMessages((current) => {
      const merged = hydrateRoutedChatMessages(storedMessages, current, { sameChat: alreadyShowingThisChat });
      return merged.length ? merged : initialChatMessages();
    });

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
      if (!inlineChatProjectId) setProjectIR(null);
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
    loadOldProject(routedChatProjectId, {
      syncRoute: false,
      signal: controller.signal,
      tab: "chat",
      hydrateChat: true,
    }).then((loaded) => {
      if (controller.signal.aborted) return;
      if (loaded) {
        setChatRouteTransition(null);
        return;
      }
      setProjectIR(null);
      setActiveTab("overview");
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
  }, [routedChatId, currentRouteProjectId, routedChatFound, routedChatProjectId, inlineChatProjectId, chatIndexLoaded, chatHistoryLoaded, authRequired, isSignedIn, chatStorageScope]);

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
    if (!currentUserOwnsProject) {
      if (authRequired && !isSignedIn) {
        openSignIn({ redirectUrl: typeof window !== "undefined" ? window.location.href : "/" });
      }
      return;
    }
    const title = projectIR.overview?.title || "forma_project";
    downloadBrowserFile(
      JSON.stringify(projectIR, null, 2),
      `${title.toLowerCase().replace(/\s+/g, "_")}_forma.json`,
      "application/json"
    );
  };

  const downloadMarkdownDocs = () => {
    if (!projectIR) return;
    if (!currentUserOwnsProject) {
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

  const metrics = useMemo(() => calculateProjectCostMetrics(projectIR), [projectIR]);
  const components = useMemo(() => resolveProjectComponentInstances(projectIR), [projectIR]);
  const bomLineItems = projectIR?.bom?.length ? projectIR.bom : components;
  const schematicProject = useMemo(
    () => projectIR ? { ...projectIR, components } : projectIR,
    [components, projectIR]
  );
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
  const currentProjectId = projectIR?.assembly_metadata?.project_id || null;
  const currentUserOwnsProject = Boolean(projectIR && canChatWithProjectIR(projectIR) && (!authRequired || isSignedIn));
  const currentProjectCanDownloadAssets = currentUserOwnsProject;
  const ownerProjectChatId = projectIR && currentUserOwnsProject
    ? (chatIdFromIR(projectIR) || currentProjectId)
    : null;
  const currentProjectChatId = projectIR
    ? routedProjectId ? null : (ownerProjectChatId || activeChatId)
    : activeChatId;
  const currentProjectChatMessages = useMemo(
    () => currentProjectChatId ? chatThreads[currentProjectChatId] || [] : [],
    [chatThreads, currentProjectChatId]
  );
  const projectImageCandidates = useMemo(() => {
    const chatReference =
      hardwareReferenceSrcFromChatMessages(currentProjectChatMessages) ||
      hardwareReferenceSrcFromChatMessages(chatMessages);
    return resolveProjectImageCandidates(
      withHardwareReferenceMetadata(projectIR?.assembly_metadata || {}, chatReference),
      formaDevMode,
    );
  }, [chatMessages, currentProjectChatMessages, formaDevMode, projectIR]);
  const showProductImageSection = shouldShowProductImageSection({
    imageCandidates: projectImageCandidates,
    llms: generationLlms,
    imageGeneration: imageGenerationConfigLoaded
      ? {
          configured: imageGenerationConfig.configured,
          requestCapable: imageGenerationConfig.requestCapable,
          provider: imageGenerationConfig.provider,
        }
      : null,
    metadata: projectIR?.assembly_metadata || {},
  });
  const videoImageOptions = useMemo(
    () => projectImageCandidates.filter((candidate) => !isHardwareReferenceCandidate(candidate)),
    [projectImageCandidates]
  );
  const defaultVideoImage = videoImageOptions[0]?.src || "";
  const projectVideo = useProjectVideo({
    apiUrl: API_URL,
    enabled: Boolean(projectIR && activeTab === "video"),
    projectId: currentProjectId,
    authIdentityKey,
    canManageProject: currentUserOwnsProject,
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
  const currentProjectJobId = projectIR?.assembly_metadata?.frontend_job_id || null;
  const activeSidebarChatId = routedProjectId ? null : (currentProjectChatId || activeChatId);
  const activeSidebarChatItem = chatListItems.find((item) => item.chatId === activeSidebarChatId);
  const displayedHomeChatMessages = activeChatId && chatThreads[activeChatId]?.length
    ? chatThreads[activeChatId]
    : chatMessages;
  const activeSidebarChatStarted = Boolean(
    projectIR ||
    chatHasStarted(projectIR ? currentProjectChatMessages : displayedHomeChatMessages) ||
    activeSidebarChatItem?.projectId ||
    activeSidebarChatItem?.projectCount
  );
  const commitOwnedWorkspaceTitle = async (nextTitle: string, options?: { chatId?: string | null; projectId?: string | null }) => {
    const title = nextTitle.trim() || "Untitled Hardware Project";
    const chatId = options && "chatId" in options
      ? options.chatId
      : (currentProjectChatId || chatIdFromIR(projectIR) || activeChatId);
    const projectId = ((options && "projectId" in options ? options.projectId : currentProjectId) || "");
    if (projectId && projectId === currentProjectId && !currentUserOwnsProject) return;
    if (projectIR && projectId && projectId === currentProjectId) {
      setProjectIR((current: any) => {
        if (!current) return current;
        return {
          ...current,
          overview: {
            ...(current.overview || {}),
            title,
          },
        };
      });
    }
    if (chatId) {
      rememberChatItem({
        chatId,
        title,
        ...(projectId ? { projectId } : {}),
      });
    }
    if (!projectId || (authRequired && !isSignedIn)) return;
    const existingProject = myProjectHistory.find((project: any) => project?.project_id === projectId)
      || projectHistory.find((project: any) => project?.project_id === projectId);
    if (existingProject) rememberProjectRecord({ ...existingProject, title });
    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
        method: "PATCH",
        headers: await generationRequestHeaders(),
        body: JSON.stringify({ title }),
      });
      if (!res.ok) throw new Error(await readApiErrorMessage(res));
    } catch (error) {
      console.error("Error renaming project", error);
    }
  };
  const renameSidebarChat = (item: ChatListItem, title: string) => {
    void commitOwnedWorkspaceTitle(title, { chatId: item.chatId, projectId: item.projectId || null });
  };
  const togglePinnedChat = (item: ChatListItem) => {
    setPinnedChatIds((current) => {
      const next = new Set(current);
      if (next.has(item.chatId)) next.delete(item.chatId);
      else next.add(item.chatId);
      writePinnedChatIds(next, chatStorageScope);
      return next;
    });
  };
  const deleteSidebarChat = (item: ChatListItem) => {
    if (item.projectId) {
      openProjectDeletion({ projectId: item.projectId, title: item.title });
      return;
    }
    forgetChatRecords([item.chatId]);
    void (async () => {
      try {
        const res = await fetch(`${API_URL}/chats/${encodeURIComponent(item.chatId)}`, {
          method: "DELETE",
          headers: await generationRequestHeaders(),
        });
        if (!res.ok && res.status !== 404) throw new Error(await readApiErrorMessage(res));
      } catch (error) {
        console.error("Error deleting chat", error);
      }
    })();
    if (activeChatId === item.chatId || (typeof window !== "undefined" && window.location.pathname === chatRoute(item.chatId))) {
      goHome();
    }
  };
  const newChatDisabled = homeView === "chat" && !routedProjectId && !activeSidebarChatStarted;
  const homeChromeRef = useRef<HTMLDivElement>(null);
  const { headerAway: homeHeaderAway, bindCapture: bindHomeChromeScroll } = useChromeHeaderScroll(
    `${homeView}:${activeChatId || ""}:${activeSidebarChatStarted ? "started" : "new"}`
  );
  useEffect(() => bindHomeChromeScroll(homeChromeRef.current), [bindHomeChromeScroll, homeView, projectIR]);
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
  const displayedWorkspaceNamespace = activeWorkspaceNamespace;
  const projectNamespaceContent = (
    <ProjectTabContent
      tabId={activeWorkspaceTab.id}
      title={projectTitle}
      description={projectDescription}
      imageCandidates={projectImageCandidates}
      features={imageFeatures}
      metrics={metrics}
      metadata={projectIR?.assembly_metadata || {}}
      systemArchitecture={projectIR?.system_architecture || null}
      showModelName={formaDevMode}
      showImageSection={showProductImageSection}
      components={components}
      bomComponents={bomLineItems}
      cadSources={(projectIR?.mechanical && Array.isArray(projectIR.mechanical.cad_sources)) ? projectIR.mechanical.cad_sources : []}
      fabricationCost={Number(projectIR?.mechanical?.fabrication_cost_estimate_usd || 0)}
      canDownloadAssets={currentProjectCanDownloadAssets}
      mechToggles={mechToggles}
      setMechToggles={setMechToggles}
      mechElectricalActive={mechElectricalActive}
      setMechElectricalActive={setMechElectricalActive}
      mechanical={projectIR?.mechanical || {}}
      schematic={<SchematicCanvas project={schematicProject} />}
      assembly={assembly}
      issues={issues}
      onDownloadJSON={downloadJSONIR}
      onDownloadMarkdown={downloadMarkdownDocs}
      videoContent={activeWorkspaceTab.id === "video" ? <VideoPanel {...projectVideo} /> : null}
      jobs={projectJobs}
      jobsLoading={jobsLoading}
      jobsError={jobsError}
      jobStatusFilter={jobStatusFilter}
      onStatusFilterChange={changeJobStatusFilter}
      onRefreshJobs={() => fetchA2aJobs(jobStatusFilter)}
      onOpenProject={loadProjectForJob}
      findProjectForJob={findProjectForJob}
      jobsLastUpdatedAt={jobsLastUpdatedAt}
      logs={backendLogs}
      logsLoading={logsLoading}
      logsError={logsError}
      onRefreshLogs={() => fetchBackendLogs()}
      logsLastUpdatedAt={logsLastUpdatedAt}
      canViewAdminTools={canViewAdminTools}
    />
  );

  useEffect(() => {
    if (routedProjectId) return;
    if (!currentUserOwnsProject) return;
    if (!currentProjectId || currentProjectChatMessages.length) return;
    ensureChatThread(currentProjectId, projectIR, projectIR?.assembly_metadata?.source_prompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routedProjectId, currentUserOwnsProject, currentProjectId, currentProjectChatMessages.length, projectIR]);

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


  const workspaceShell = (activeId: string | null, children: React.ReactNode, homeMobileTopPadding = false) => (
    <WorkspaceSidebarShell
      collapsed={sidebarCollapsed}
      mobileSidebarOpen={mobileSidebarOpen}
      onMobileSidebarClose={() => setMobileSidebarOpen(false)}
      onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
      onHome={goHome}
      chats={chatListItems}
      activeChatId={activeId}
      onNewChat={startNewProjectChat}
      newChatDisabled={newChatDisabled}
      onOpenChat={openChatItem}
      onRenameChat={renameSidebarChat}
      onPinChat={togglePinnedChat}
      onDeleteChat={deleteSidebarChat}
      waitingChatIds={waitingChatIds}
      chatsLoading={sidebarChatsLoading}
      showJobs={canViewJobs}
      jobsPending={sidebarJobsPending}
      showDeveloperTools={showDeveloperTools}
      authRequired={authRequired}
      workspaceStatus={workspaceStatus}
      homeMobileTopPadding={homeMobileTopPadding}
    >
      {children}
    </WorkspaceSidebarShell>
  );

  if (showChatRouteFallback && visibleChatRouteTransition) {
    return (
      workspaceShell(
        visibleChatRouteTransition.chatId,
        (
        <>
        <ChatRouteFallbackPanel
          transition={visibleChatRouteTransition}
          onHome={goHome}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
        />
        <ProjectDeletionDialog
          project={pendingProjectDeletion}
          acknowledged={deletionAcknowledged}
          contribute={contributeDeletedProject}
          busy={projectDeletionBusy}
          error={projectDeletionError}
          onAcknowledgedChange={setDeletionAcknowledged}
          onContributeChange={setContributeDeletedProject}
          onCancel={closeProjectDeletion}
          onConfirm={confirmProjectDeletion}
        />
        </>
        ),
        false,
      )
    );
  }

  if (routedProjectId && loadedProjectId !== routedProjectId) {
    return (
      workspaceShell(
        null,
        (
        <>
        <ProjectRouteFallbackPanel
          projectId={routedProjectId}
          error={routeProjectError}
          onHome={goHome}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
        />
        <ProjectDeletionDialog
          project={pendingProjectDeletion}
          acknowledged={deletionAcknowledged}
          contribute={contributeDeletedProject}
          busy={projectDeletionBusy}
          error={projectDeletionError}
          onAcknowledgedChange={setDeletionAcknowledged}
          onContributeChange={setContributeDeletedProject}
          onCancel={closeProjectDeletion}
          onConfirm={confirmProjectDeletion}
        />
        </>
        ),
        false,
      )
    );
  }

  if (homeView !== "chat" || !projectIR) {
    return (
      workspaceShell(
        activeChatId,
        (
        <>
        <div ref={homeChromeRef} className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <MobileWorkspaceBar onOpenSidebar={() => setMobileSidebarOpen(true)} headerAway={homeHeaderAway}>
          {homeView === "settings" ? (
            <WorkspaceChromeIdentity icon={Settings} badge="General" title="Settings" />
          ) : homeView === "about" ? (
            <WorkspaceChromeIdentity icon={Handshake} badge="General" title="About" />
          ) : homeView === "projects" ? (
            <WorkspaceChromeIdentity icon={Layers} badge="Workspace" title="Community" />
          ) : homeView === "my-projects" ? (
            <WorkspaceChromeIdentity icon={Database} badge="Workspace" title="My projects" />
          ) : homeView === "jobs" ? (
            <WorkspaceChromeIdentity icon={History} badge="Workspace" title="Jobs" />
          ) : homeView === "logs" ? (
            <WorkspaceChromeIdentity icon={Terminal} badge="Workspace" title="Backend logs" />
          ) : activeSidebarChatStarted ? (
            <WorkspaceChromeIdentity
              icon={MessageSquare}
              badge="Chat"
              title={(
                <EditableWorkspaceTitle
                  value={activeSidebarChatItem?.title || NEW_PROJECT_TITLE}
                  canEdit
                  label="Chat title"
                  onCommit={(title) => {
                    if (activeChatId) {
                      void commitOwnedWorkspaceTitle(title, {
                        chatId: activeChatId,
                        projectId: activeSidebarChatItem?.projectId || null,
                      });
                    }
                  }}
                />
              )}
            />
          ) : null}
        </MobileWorkspaceBar>
	        <main className={`mx-auto w-full ${homeView === "chat" || homeView === "settings" || homeView === "about" ? "max-w-none" : "max-w-6xl"} ${
	          homeView === "chat"
	            ? "flex min-h-0 flex-1 flex-col overflow-hidden px-0 pb-0 pt-0 md:pt-4"
            : "min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-16 sm:px-5 md:py-8"
        }`}>
          {homeView === "projects" ? (
              <ProjectGallery
                sectionRef={projectsSectionRef}
                items={projectGalleryItems}
                title="Community"
                loading={projectsPageLoading}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
                onToggleSave={canInteractWithGallery ? handleToggleProjectSave : undefined}
                onRemixProject={canInteractWithGallery ? handleRemixProject : undefined}
                onVisibleProjectIdsChange={handleVisibleProjectGalleryIdsChange}
                totalItems={projectHistoryTotal}
                currentPage={projectHistoryPage}
                onPageChange={handleProjectHistoryPageChange}
                searchValue={projectSearchInput}
                onSearchValueChange={setProjectSearchInput}
                standalone
              />
	          ) : homeView === "my-projects" ? (
              <ProjectGallery
                sectionRef={projectsSectionRef}
                items={myProjectGalleryItems}
                title="My projects"
                loading={myProjectsPageLoading}
                onOpenProjectPage={(projectId) => router.push(projectRoute(projectId))}
                onToggleSave={canInteractWithGallery ? handleToggleProjectSave : undefined}
                onRemixProject={canInteractWithGallery ? handleRemixProject : undefined}
                onVisibleProjectIdsChange={handleVisibleProjectGalleryIdsChange}
                totalItems={myProjectHistoryTotal}
                currentPage={myProjectHistoryPage}
                onPageChange={handleMyProjectHistoryPageChange}
                standalone
              />
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
                  metrics={jobMetrics}
                  metricsError={jobMetricsError}
                  metricsWindow={jobMetricsWindow}
                  onMetricsWindowChange={setJobMetricsWindow}
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
                <div className="rounded-xl border border-white/5 bg-[#181b22] p-6 text-sm leading-6 text-zinc-400">
                  {adminSessionLoaded ? "Admin access is required to view jobs." : "Checking admin access..."}
                </div>
              )}
            </>
          ) : homeView === "logs" ? (
            <>
              <WorkspacePageHeading
                icon={Terminal}
                title="Backend logs"
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
                <div className="rounded-xl border border-white/5 bg-[#181b22] p-6 text-sm leading-6 text-zinc-400">
                  {adminSessionLoaded ? "Admin access is required to view backend logs." : "Checking admin access..."}
                </div>
              )}
            </>
          ) : homeView === "settings" ? (
            <UserIntegrationsPage embedded />
          ) : homeView === "about" ? (
            <AboutView />
          ) : (
            <HomeChatView
              started={activeSidebarChatStarted}
              conversationKey={activeChatId || "new-chat"}
              workspaceTitle={
                activeSidebarChatStarted ? (
                  <EditableWorkspaceTitle
                    value={activeSidebarChatItem?.title || NEW_PROJECT_TITLE}
                    canEdit
                    label="Chat title"
                    onCommit={(title) => {
                      if (activeChatId) {
                        void commitOwnedWorkspaceTitle(title, {
                          chatId: activeChatId,
                          projectId: activeSidebarChatItem?.projectId || null,
                        });
                      }
                    }}
                  />
                ) : null
              }
              messages={displayedHomeChatMessages}
              renderPipelineProgress={(message) => (
                <AgentPipelineProgressView
                  progress={message.pipelineProgress as AgentPipelineProgress | null}
                  status={message.status}
                  compact
                  onStop={
                    message.status === "loading" && message.buildPlanId && message.contextProjectId
                      ? () => stopContextBuildMessage(message as ChatMessage)
                      : undefined
                  }
                  onReset={
                    message.status === "error"
                    && message.buildPlanId
                    && message.buildJobId
                    && message.contextProjectId
                    && !activeGeneration
                    && !pendingContextBuildMessage
                      ? () => void resetFailedContextBuild(message as ChatMessage)
                      : undefined
                  }
                  resetting={resettingBuildMessageId === message.id}
                />
              )}
              projectArtifact={
                projectIR && inlineChatProjectId && currentProjectId === inlineChatProjectId
                  ? (
                    <ChatProjectArtifact
                      projectId={currentProjectId}
                      projectTitle={projectTitle}
                      canEdit={currentUserOwnsProject}
                      onRenameTitle={currentUserOwnsProject ? (title) => { void commitOwnedWorkspaceTitle(title); } : undefined}
                      namespaceTabs={visibleWorkspaceTabs}
                      activeNamespace={activeWorkspaceTab.id}
                      onNamespaceChange={setActiveTab}
                      projectContent={projectNamespaceContent}
                    />
                  )
                  : null
              }
              examples={samplePrompts}
              onSelectExample={(example) => {
                setGenerationInputNotice(null);
                            setPrompt(example);
              }}
              onSubmit={handleGatherContext}
              canBuildNow={(() => {
                const messages = activeChatId ? chatThreads[activeChatId] || chatMessages : chatMessages;
                const contextMessage = [...messages].reverse().find((message) => Boolean(message.contextProjectId));
                const state = contextWorkflowStates[activeChatId]
                  || contextMessage?.workflowState
                  || (contextMessage?.contextProjectId ? "gathering_context" : "");
                return state === "gathering_context";
              })()}
              buildNowLoading={contextBuildStarting}
              onBuildNow={handleBuildNow}
              onSelectContextSuggestion={(suggestion) => {
                void submitGatherContext(suggestion);
              }}
              isLoading={contextSubmitting || Boolean(activeGeneration || pendingContextBuildMessage || resettingBuildMessageId)}
              generationReady
              needsGenerationProvider={false}
              needsImageProvider={false}
              selectedImage={selectedImage}
              onRemoveImage={removeSelectedImage}
              notice={visibleContextInputNotice}
              prompt={prompt}
              onPromptChange={(value) => {
                setGenerationInputNotice(null);
                setPrompt(value);
              }}
              generationActive={Boolean(activeGeneration || pendingContextBuildMessage)}
              onStop={() => {
                if (activeGenerationRef.current) stopActiveGeneration();
                else if (pendingContextBuildMessage) stopContextBuildMessage(pendingContextBuildMessage);
              }}
              canRetryFailedBuild={Boolean(retryableContextBuildMessage)}
              retryingFailedBuild={resettingBuildMessageId === retryableContextBuildMessage?.id}
              onRetryFailedBuild={() => {
                if (retryableContextBuildMessage) void resetFailedContextBuild(retryableContextBuildMessage);
              }}
              hasGenerationInput={hasGenerationInput}
              inputValid={generationInputValidation.isValid}
              imageInputRef={fileInputRefCenter}
              onImageChange={handleImageChange}
              onImagePaste={handleImagePaste}
            />
          )}
        </main>
        </div>
        <ProjectDeletionDialog
          project={pendingProjectDeletion}
          acknowledged={deletionAcknowledged}
          contribute={contributeDeletedProject}
          busy={projectDeletionBusy}
          error={projectDeletionError}
          onAcknowledgedChange={setDeletionAcknowledged}
          onContributeChange={setContributeDeletedProject}
          onCancel={closeProjectDeletion}
          onConfirm={confirmProjectDeletion}
        />
        </>
        ),
        true,
      )
    );
  }

  return workspaceShell(
    activeSidebarChatId,
    (
      <>
      <main className="flex min-h-0 min-w-0 flex-col">
        <input
          ref={projectVideo.fileInputRef}
          type="file"
          accept="image/*"
          onChange={projectVideo.onImageFileChange}
          className="hidden"
        />

          <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
            {routedProjectId ? (
              <ProjectDetailWorkspace
                onOpenSidebar={() => setMobileSidebarOpen(true)}
                projectId={currentProjectId}
                projectTitle={projectTitle}
                owned={currentUserOwnsProject}
                onRenameTitle={currentUserOwnsProject ? (title) => { void commitOwnedWorkspaceTitle(title); } : undefined}
                namespaceTabs={visibleWorkspaceTabs}
                activeNamespace={activeWorkspaceTab.id}
                onNamespaceChange={setActiveTab}
                projectContent={projectNamespaceContent}
              />
            ) : (
              <ChatWorkspace
                onOpenSidebar={() => setMobileSidebarOpen(true)}
                projectId={currentProjectId}
                chatId={currentProjectChatId}
                projectTitle={projectTitle}
                onRenameTitle={currentUserOwnsProject ? (title) => { void commitOwnedWorkspaceTitle(title); } : undefined}
                messages={currentProjectChatMessages}
                input={projectChatInput}
                setInput={setProjectChatInput}
                onSubmit={handleProjectChatGenerate}
                isLoading={isLoading}
                canStop={activeGeneration?.kind === "project-chat"}
                onStop={stopActiveGeneration}
                canChat={currentUserOwnsProject}
                namespaceTabs={visibleWorkspaceTabs}
                activeNamespace={activeWorkspaceTab.id}
                activeNamespaceLabel={activeWorkspaceTab.label}
                activeNamespaceName={activeWorkspaceNamespace}
                onNamespaceChange={setActiveTab}
                projectContent={projectNamespaceContent}
              />
            )}
          </section>
      </main>
      <ProjectDeletionDialog
        project={pendingProjectDeletion}
        acknowledged={deletionAcknowledged}
        contribute={contributeDeletedProject}
        busy={projectDeletionBusy}
        error={projectDeletionError}
        onAcknowledgedChange={setDeletionAcknowledged}
        onContributeChange={setContributeDeletedProject}
        onCancel={closeProjectDeletion}
        onConfirm={confirmProjectDeletion}
      />
      </>
    ),
  );
}

export default FormaWorkspace;
