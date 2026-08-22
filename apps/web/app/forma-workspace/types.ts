import type { A2AJob } from "./use-admin-data";

export type GenerationWorkflowOption = {
  id: string;
  label: string;
  description?: string;
  uses_catalog?: boolean;
  uses_web_research?: boolean;
  uses_firecrawl_mcp?: boolean;
  uses_external_sources?: boolean;
};

export type AgentPipelineStep = {
  id: string;
  agent: string;
  label: string;
  description: string;
  duration_ms?: number;
  optional?: boolean;
};

export type AgentPipelineEvent = {
  workflow?: string;
  step_id: string;
  status: "started" | "completed" | "failed" | "skipped" | string;
  agent?: string;
  label?: string;
  description?: string;
  observed_at?: string;
  details?: Record<string, any>;
};

export type AgentPipelineProgress = {
  startedAt: string;
  steps: AgentPipelineStep[];
  currentStepIndex: number;
  estimated: boolean;
  synced?: boolean;
  jobId?: string | null;
  events?: AgentPipelineEvent[];
  uiUpdatedAt?: string;
};

export type ChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  status?: "idle" | "loading" | "success" | "error" | "cancelled";
  timestamp: string;
  projectId?: string | null;
  pipelineProgress?: AgentPipelineProgress | null;
  imagePreview?: string | null;
  contextProjectId?: string | null;
  workflowState?: string | null;
  contextQuestions?: string[];
  contextSuggestions?: string[];
  buildPlanId?: string | null;
  buildJobId?: string | null;
  buildRequiresRequestBoundExecution?: boolean;
};

export type ActiveGenerationRun = {
  kind: "chat" | "project-chat" | "context-build";
  controller: AbortController;
  jobId: string | null;
  planId?: string | null;
  projectId?: string | null;
  chatId: string;
  assistantMessageId: string | null;
  cancelled: boolean;
};

export type ActiveGenerationState = Pick<ActiveGenerationRun, "kind" | "jobId">;

export type HumanContextQuestion = {
  id: string;
  label: string;
  question: string;
  placeholder: string;
  suggestions: string[];
};

export type PendingHumanContext = {
  basePrompt: string;
  questions: HumanContextQuestion[];
  answers: Record<string, string>;
};

export type PendingProjectDeletion = {
  projectId: string;
  title: string;
};

export type ApiErrorDetails = {
  message: string;
  code?: string;
  reason?: string;
  provider?: string;
  model?: string;
  job_id?: string;
  debug?: Record<string, any>;
};

export type ChatRouteTransition = {
  chatId: string;
  title: string;
  projectId: string;
  error?: string | null;
};

export type VideoGenerationConfig = {
  configured: boolean | null;
  reason: string | null;
};

export type ImageGenerationConfig = {
  configured: boolean | null;
  requestCapable: boolean | null;
  provider: string | null;
  reason: string | null;
};

export type ProviderSetupState = {
  llmRequired: boolean;
  imageRequired: boolean;
};

export type HomeProps = {
  routeProjectId?: string | null;
  routeChatId?: string | null;
  showDeveloperTools?: boolean;
  homeView?: "chat" | "projects" | "my-projects" | "jobs" | "logs" | "settings" | "about";
};
