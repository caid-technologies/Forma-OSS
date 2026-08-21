"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { normalizeContextSuggestions } from "../../lib/context-suggestions";
import type { A2AJob } from "./use-admin-data";
import {
  CONTEXT_BUILD_FIRST_POLL_MS,
  CONTEXT_BUILD_MAX_ATTEMPTS,
  CONTEXT_BUILD_POLL_MS,
  CONTEXT_BUILD_TIMEOUT_MESSAGE,
  contextBuildWatchKey,
} from "./lib/context-build";
import { chatMessageIdentityKey } from "./lib/chat-normalize";
import { chatTimestamp, newBuildChatId, newChatMessageId } from "./lib/chat-ids";
import { validateGenerationInput } from "./lib/generation-input";
import {
  createAgentPipelineProgress,
  pipelineEventsFromWorkerTask,
  progressFromJobEvents,
  progressIncludesImageStep,
} from "./lib/agent-pipeline";
import { readApiErrorMessage } from "./lib/api-errors";
import { withProjectResponseMetadata } from "./lib/project-metadata";
import type { ActiveGenerationRun, AgentPipelineProgress, ChatMessage } from "./types";
import { defaultAgentPipelineSteps } from "./workspace-constants";
import { API_URL } from "./workspace-api";

export type ContextBuildControllerOptions = {
  activeChatId: string;
  setActiveChatId: (chatId: string) => void;
  chatMessages: ChatMessage[];
  chatThreads: Record<string, ChatMessage[]>;
  prompt: string;
  setPrompt: (value: string) => void;
  selectedImage: string | null;
  setSelectedImage: (value: string | null) => void;
  selectedImageSource: "upload" | "clipboard";
  setSelectedImageSource: (value: "upload" | "clipboard") => void;
  generateProductImage: boolean;
  authRequired: boolean;
  isSignedIn: boolean | null | undefined;
  userImageUrl: string | null | undefined;
  generationRequestHeaders: () => Promise<HeadersInit> | HeadersInit;
  optionalAuthHeaders: () => Promise<HeadersInit> | HeadersInit;
  requireSignedInForGeneration: () => Promise<boolean>;
  noteAuthResponseStatus: (status: number) => void;
  appendChatMessage: (message: Omit<ChatMessage, "id" | "timestamp"> & { id?: string }) => void;
  updateChatMessage: (id: string, patch: Partial<Omit<ChatMessage, "id">>) => void;
  appendThreadMessage: (chatId: string, message: Omit<ChatMessage, "id" | "timestamp"> & { id?: string }) => void;
  updateThreadMessage: (chatId: string, id: string, patch: Partial<Omit<ChatMessage, "id">>) => void;
  applyChatPipelineProgressFromJob: (...args: any[]) => void;
  applyThreadPipelineProgressFromJob: (...args: any[]) => void;
  rememberChatItem: (item: any) => void;
  rememberProjectRecord: (record: any) => void;
  setProjectIR: (ir: any) => void;
  setGenerationInputNotice: (value: string | null) => void;
  setIsLoading: (value: boolean) => void;
  activeGenerationRef: { current: ActiveGenerationRun | null };
  beginGenerationRun: (kind: ActiveGenerationRun["kind"], chatId: string) => ActiveGenerationRun;
  finishGenerationRun: (run: ActiveGenerationRun) => void;
  setGenerationRunJob: (run: ActiveGenerationRun, jobId: string, assistantMessageId: string) => void;
  stopActiveGeneration: () => void;
  syncChatRoute: (chatId: string) => void;
  fetchProjectHistory: () => void;
  fetchMyProjectHistory: () => void;
};

export function useContextBuildController(options: ContextBuildControllerOptions) {
  const {
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
  } = options;

  const contextProjectIdsRef = useRef<Record<string, string>>({});
  const contextBuildWatchersRef = useRef(new Map<string, { stop: () => void }>());
  const [contextWorkflowStates, setContextWorkflowStates] = useState<Record<string, string>>({});
  const [contextBuildStarting, setContextBuildStarting] = useState(false);
  const [resettingBuildMessageId, setResettingBuildMessageId] = useState<string | null>(null);
  const [contextSubmitting, setContextSubmitting] = useState(false);

  const pendingContextBuildMessage = useMemo(
    () => [...chatMessages].reverse().find((message) => (
      message.status === "loading"
      && Boolean(message.buildPlanId)
      && Boolean(message.contextProjectId)
    )) || null,
    [chatMessages],
  );
  const retryableContextBuildMessage = useMemo(() => {
    const latestBuildMessage = [...chatMessages].reverse().find((message) => (
      Boolean(message.buildPlanId)
      && Boolean(message.buildJobId)
      && Boolean(message.contextProjectId)
    ));
    return latestBuildMessage?.status === "error" ? latestBuildMessage : null;
  }, [chatMessages]);

  const beginContextBuildRun = (
    projectId: string,
    planId: string,
    jobId: string,
    chatId: string,
    assistantMessageId: string,
  ) => {
    const active = activeGenerationRef.current;
    if (active?.kind === "context-build" && active.planId === planId) return active;
    const run = beginGenerationRun("context-build", chatId);
    run.projectId = projectId;
    run.planId = planId;
    setGenerationRunJob(run, jobId, assistantMessageId);
    return run;
  };

  const cancelContextBuild = async (projectId: string, planId: string) => {
    try {
      const response = await fetch(
        `${API_URL}/projects/${encodeURIComponent(projectId)}/build/plans/${encodeURIComponent(planId)}/cancel`,
        { method: "POST", headers: await generationRequestHeaders() },
      );
      if (!response.ok) throw new Error(await readApiErrorMessage(response));
    } catch (error) {
      console.warn("Could not notify the backend that the build was stopped.", error);
      setGenerationInputNotice(error instanceof Error ? error.message : "Could not stop the build.");
    }
  };

  const executeContextBuild = async (
    projectId: string,
    planId: string,
    run?: ActiveGenerationRun,
  ) => {
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      try {
        const response = await fetch(
          `${API_URL}/projects/${encodeURIComponent(projectId)}/build/plans/${encodeURIComponent(planId)}/execute`,
          {
            method: "POST",
            headers: await generationRequestHeaders(),
            signal: run?.controller.signal,
          },
        );
        if (!response.ok) throw new Error(await readApiErrorMessage(response));
        return;
      } catch (error) {
        if (run?.cancelled || run?.controller.signal.aborted) return;
        console.warn("The build execution request ended before the plan reached a terminal state.", error);
        if (attempt === 4) {
          setGenerationInputNotice(
            error instanceof Error ? error.message : "The build execution request ended unexpectedly.",
          );
          return;
        }
        setGenerationInputNotice("Build connection interrupted. Resuming from the latest saved stage…");
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
    }
  };

  const stopContextBuildMessage = (message: ChatMessage) => {
    const projectId = message.contextProjectId;
    const planId = message.buildPlanId;
    if (!projectId || !planId) return;
    const active = activeGenerationRef.current;
    if (active?.kind === "context-build" && active.planId === planId) {
      stopActiveGeneration();
      return;
    }
    const stoppedMessage = "Build stopped by you. Your project brief is preserved.";
    updateChatMessage(message.id, { content: stoppedMessage, status: "cancelled" });
    updateThreadMessage(activeChatId, message.id, { content: stoppedMessage, status: "cancelled" });
    setGenerationInputNotice("Build stopped. Your project brief is preserved.");
    setIsLoading(false);
    void cancelContextBuild(projectId, planId);
  };

  const resumeContextBuild = async (
    projectId: string,
    planId: string,
    run?: ActiveGenerationRun,
  ) => {
    try {
      const response = await fetch(
        `${API_URL}/projects/${encodeURIComponent(projectId)}/build/plans/${encodeURIComponent(planId)}/resume`,
        {
          method: "POST",
          headers: await generationRequestHeaders(),
          signal: run?.controller.signal,
        },
      );
      if (!response.ok) throw new Error(await readApiErrorMessage(response));
    } catch (error) {
      if (run?.cancelled || run?.controller.signal.aborted) return;
      console.warn("Could not resume the detached build.", error);
    }
  };

  const watchContextBuild = (
    projectId: string,
    planId: string,
    jobId: string,
    chatId: string,
    assistantMessageId: string,
    run?: ActiveGenerationRun,
    requestBoundExecution = true,
  ) => {
    const watcherKey = contextBuildWatchKey(projectId, planId);
    if (contextBuildWatchersRef.current.has(watcherKey)) return;
    let cancelled = false;
    let timeoutId: number | null = null;
    const stop = () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
      contextBuildWatchersRef.current.delete(watcherKey);
    };
    contextBuildWatchersRef.current.set(watcherKey, { stop });
    if (requestBoundExecution) {
      void executeContextBuild(projectId, planId, run);
    } else {
      void resumeContextBuild(projectId, planId, run);
    }
    let attempts = 0;
    let consecutiveErrors = 0;
    const poll = async () => {
      if (cancelled || run?.cancelled || run?.controller.signal.aborted) {
          stop();
        return;
      }
      attempts += 1;
      try {
        const response = await fetch(
          `${API_URL}/projects/${encodeURIComponent(projectId)}/build/plans/${encodeURIComponent(planId)}`,
          { headers: await generationRequestHeaders(), signal: run?.controller.signal },
        );
        if (!response.ok) throw new Error(await readApiErrorMessage(response));
        consecutiveErrors = 0;
        const plan = await response.json();
        const planStatus = typeof plan?.status === "string" ? plan.status : "";
        const task = plan?.jobs?.[jobId];
        const progressEvents = pipelineEventsFromWorkerTask(task);
        let synchronizedProgress: AgentPipelineProgress | null = null;
        if (progressEvents.length) {
          const seedProgress = createAgentPipelineProgress(
            defaultAgentPipelineSteps,
            false,
            typeof task?.started_at === "string" ? task.started_at : chatTimestamp(),
            jobId,
          );
          const progressJob: A2AJob = {
            job_id: jobId,
            action: "forma.generate_project",
            sender: "worker-orchestrator",
            recipient: "forma",
            status: "running",
            started_at: typeof task?.started_at === "string" ? task.started_at : null,
            progress_events: progressEvents,
          };
          synchronizedProgress = progressFromJobEvents(progressJob, seedProgress, false);
          applyChatPipelineProgressFromJob(assistantMessageId, progressJob, seedProgress, false);
          applyThreadPipelineProgressFromJob(chatId, assistantMessageId, progressJob, seedProgress, false);
        }
        if (planStatus === "succeeded") {
          const projectResponse = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
            headers: await optionalAuthHeaders(),
          });
          if (!projectResponse.ok) throw new Error(await readApiErrorMessage(projectResponse));
          const projectData = await projectResponse.json();
          const ir = withProjectResponseMetadata(projectData.project_ir, projectData);
          const title = ir?.overview?.title || "Project";
          setProjectIR(ir);
          setContextWorkflowStates((current) => ({ ...current, [chatId]: "awaiting_feedback" }));
          rememberProjectRecord({
            project_id: projectId,
            chat_id: chatId,
            title,
            prompt: projectData.prompt || title,
            created_at: projectData.created_at || chatTimestamp(),
            can_chat: true,
            creator_display: "you",
            creator_image_url: userImageUrl,
            parts_count: Array.isArray(ir?.components) ? ir.components.length : 0,
            save_count: 0,
            remix_count: 0,
            saved: false,
          });
          rememberChatItem({
            chatId,
            title,
            projectId,
            createdAt: chatTimestamp(),
            projectCount: 1,
          });
          const readyMessage = `${title} is ready. The first structured design revision is available for review.`;
          updateChatMessage(assistantMessageId, {
            content: readyMessage,
            status: "success",
            pipelineProgress: synchronizedProgress,
            projectId,
            contextProjectId: projectId,
            workflowState: "awaiting_feedback",
          });
          updateThreadMessage(chatId, assistantMessageId, {
            content: readyMessage,
            status: "success",
            pipelineProgress: synchronizedProgress,
            projectId,
            contextProjectId: projectId,
            workflowState: "awaiting_feedback",
          });
          setGenerationInputNotice("Design ready for review.");
          void fetchProjectHistory();
          if (!authRequired || isSignedIn) void fetchMyProjectHistory();
          stop();
          if (run) finishGenerationRun(run);
          return;
        }
        if (planStatus === "cancelled" || planStatus === "canceled") {
          const stoppedMessage = "Build stopped by you. Your project brief is preserved.";
          updateChatMessage(assistantMessageId, { content: stoppedMessage, status: "cancelled" });
          updateThreadMessage(chatId, assistantMessageId, { content: stoppedMessage, status: "cancelled" });
          setGenerationInputNotice("Build stopped. Your project brief is preserved.");
          stop();
          if (run) finishGenerationRun(run);
          return;
        }
        if (planStatus === "partial") {
          try {
            const projectResponse = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}`, {
              headers: await optionalAuthHeaders(),
            });
            if (projectResponse.ok) {
              const projectData = await projectResponse.json();
              setProjectIR(withProjectResponseMetadata(projectData.project_ir, projectData));
            }
          } catch (error) {
            console.warn("Could not load the preserved partial project.", error);
          }
          const failedStage = task?.result?.metadata?.generation_retry?.retry_stage;
          const partialMessage = typeof failedStage === "string" && failedStage
            ? `The ${failedStage.replaceAll("_", " ")} stage failed. Earlier and independent work was preserved.`
            : "One build stage failed. Earlier and independent work was preserved.";
          updateChatMessage(assistantMessageId, {
            content: partialMessage,
            status: "error",
            pipelineProgress: synchronizedProgress,
            projectId,
            workflowState: "awaiting_feedback",
          });
          updateThreadMessage(chatId, assistantMessageId, {
            content: partialMessage,
            status: "error",
            pipelineProgress: synchronizedProgress,
            projectId,
            workflowState: "awaiting_feedback",
          });
          setGenerationInputNotice("Partial design saved. Retry will resume from the failed stage.");
          stop();
          if (run) finishGenerationRun(run);
          return;
        }
        if (planStatus === "failed") {
          const failureMessage = typeof task?.error?.message === "string"
            ? task.error.message
            : "The design build stopped after an agent failure.";
          updateChatMessage(assistantMessageId, { content: failureMessage, status: "error", workflowState: "awaiting_feedback" });
          updateThreadMessage(chatId, assistantMessageId, { content: failureMessage, status: "error", workflowState: "awaiting_feedback" });
          setGenerationInputNotice(failureMessage);
          stop();
          if (run) finishGenerationRun(run);
          return;
        }
      } catch (error) {
        if (cancelled || run?.controller.signal.aborted) {
          stop();
          return;
        }
        consecutiveErrors += 1;
        if (consecutiveErrors % 3 === 0) {
          if (requestBoundExecution) void executeContextBuild(projectId, planId, run);
          else void resumeContextBuild(projectId, planId, run);
        }
        if (attempts >= CONTEXT_BUILD_MAX_ATTEMPTS) {
          const timeoutPatch: Partial<Omit<ChatMessage, "id">> = {
            content: CONTEXT_BUILD_TIMEOUT_MESSAGE,
            status: "error",
          };
          updateChatMessage(assistantMessageId, timeoutPatch);
          updateThreadMessage(chatId, assistantMessageId, timeoutPatch);
          setGenerationInputNotice(CONTEXT_BUILD_TIMEOUT_MESSAGE);
          stop();
          if (run) finishGenerationRun(run);
          return;
        }
      }
      if (cancelled) return;
      if (attempts < CONTEXT_BUILD_MAX_ATTEMPTS) {
        timeoutId = window.setTimeout(poll, CONTEXT_BUILD_POLL_MS);
        return;
      }
      const timeoutPatch: Partial<Omit<ChatMessage, "id">> = {
        content: CONTEXT_BUILD_TIMEOUT_MESSAGE,
        status: "error",
      };
      updateChatMessage(assistantMessageId, timeoutPatch);
      updateThreadMessage(chatId, assistantMessageId, timeoutPatch);
      setGenerationInputNotice(CONTEXT_BUILD_TIMEOUT_MESSAGE);
      stop();
      if (run) finishGenerationRun(run);
    };
    timeoutId = window.setTimeout(poll, CONTEXT_BUILD_FIRST_POLL_MS);
  };

  const resetFailedContextBuild = async (message: ChatMessage) => {
    const projectId = message.contextProjectId;
    const planId = message.buildPlanId;
    const jobId = message.buildJobId;
    const chatId = activeChatId;
    if (!projectId || !planId || !jobId || !chatId || activeGenerationRef.current) return;

    setResettingBuildMessageId(message.id);
    setGenerationInputNotice(null);
    try {
      const response = await fetch(
        `${API_URL}/projects/${encodeURIComponent(projectId)}/build/plans/${encodeURIComponent(planId)}/reset`,
        { method: "POST", headers: await generationRequestHeaders() },
      );
      if (!response.ok) throw new Error(await readApiErrorMessage(response));

      const resetPlan = await response.json();
      const resetJobId = typeof resetPlan?.jobs?.[jobId]?.request?.job_id === "string"
        ? resetPlan.jobs[jobId].request.job_id
        : jobId;
      const previousProgress = message.pipelineProgress;
      const resetTask = resetPlan?.jobs?.[jobId];
      const resetEvents = pipelineEventsFromWorkerTask(resetTask);
      const seedProgress = createAgentPipelineProgress(
        previousProgress?.steps || defaultAgentPipelineSteps,
        progressIncludesImageStep(previousProgress),
        chatTimestamp(),
        resetJobId,
      );
      const progress = resetEvents.length
        ? progressFromJobEvents({
            job_id: resetJobId,
            action: "forma.generate_project",
            sender: "worker-orchestrator",
            recipient: "forma",
            status: "running",
            progress_events: resetEvents,
          }, seedProgress, false)
        : seedProgress;
      const patch: Partial<Omit<ChatMessage, "id">> = {
        content: "Trying the design build again with the preserved project brief.",
        status: "loading",
        pipelineProgress: progress,
        workflowState: "building",
      };
      updateChatMessage(message.id, patch);
      updateThreadMessage(chatId, message.id, patch);
      setContextWorkflowStates((current) => ({ ...current, [chatId]: "building" }));
      setGenerationInputNotice("Job reset. The build agents are trying again.");

      const run = beginContextBuildRun(projectId, planId, resetJobId, chatId, message.id);
      watchContextBuild(
        projectId,
        planId,
        resetJobId,
        chatId,
        message.id,
        run,
        message.buildRequiresRequestBoundExecution !== false,
      );
    } catch (error) {
      setGenerationInputNotice(error instanceof Error ? error.message : "Could not reset the failed job.");
    } finally {
      setResettingBuildMessageId(null);
    }
  };

  useEffect(() => {
    const pending = [...chatMessages].reverse().find((message) => (
      message.status === "loading"
      && Boolean(message.buildPlanId)
      && Boolean(message.buildJobId)
      && Boolean(message.contextProjectId)
      && !message.projectId
    ));
    if (!pending?.buildPlanId || !pending.buildJobId || !pending.contextProjectId || !activeChatId) return;
    if (!pending.pipelineProgress) {
      const progress = createAgentPipelineProgress(
        defaultAgentPipelineSteps,
        generateProductImage,
        chatTimestamp(),
        pending.buildJobId,
      );
      updateChatMessage(pending.id, { pipelineProgress: progress, status: "loading" });
      updateThreadMessage(activeChatId, pending.id, { pipelineProgress: progress, status: "loading" });
    }
    const run = beginContextBuildRun(
      pending.contextProjectId,
      pending.buildPlanId,
      pending.buildJobId,
      activeChatId,
      pending.id,
    );
    watchContextBuild(
      pending.contextProjectId,
      pending.buildPlanId,
      pending.buildJobId,
      activeChatId,
      pending.id,
      run,
      pending.buildRequiresRequestBoundExecution !== false,
    );
    // The watcher registry makes this restart-safe without duplicating poll loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId, chatMessageIdentityKey(chatMessages)]);

  useEffect(() => () => {
    contextBuildWatchersRef.current.forEach((watcher) => watcher.stop());
    contextBuildWatchersRef.current.clear();
  }, []);

  const submitGatherContext = async (answer?: string) => {
    if (contextSubmitting || activeGenerationRef.current) return;
    if (!(await requireSignedInForGeneration())) return;

    const submittedPrompt = answer ?? prompt;
    const validation = validateGenerationInput(submittedPrompt, Boolean(selectedImage));
    if (!validation.isValid) {
      setGenerationInputNotice(validation.message);
      return;
    }

    const requestChatId = activeChatId || newBuildChatId();
    const requestProjectId = contextProjectIdsRef.current[requestChatId] || (
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestChatId)
        ? requestChatId
        : newBuildChatId()
    );
    contextProjectIdsRef.current[requestChatId] = requestProjectId;
    const text = submittedPrompt.trim();
    const imageData = selectedImage;
    const userMessageId = newChatMessageId();
    const assistantMessageId = newChatMessageId();
    const userContent = text || "Shared a hardware reference image.";

    setActiveChatId(requestChatId);
    rememberChatItem({
      chatId: requestChatId,
      title: text || "Hardware reference",
      projectId: "",
      createdAt: chatTimestamp(),
      projectCount: 0,
    });
    syncChatRoute(requestChatId);
    appendChatMessage({ id: userMessageId, role: "user", content: userContent, imagePreview: imageData, status: "idle" });
    appendThreadMessage(requestChatId, { id: userMessageId, role: "user", content: userContent, imagePreview: imageData, status: "idle" });
    appendChatMessage({ id: assistantMessageId, role: "assistant", content: "Thinking…", status: "loading" });
    appendThreadMessage(requestChatId, { id: assistantMessageId, role: "assistant", content: "Thinking…", status: "loading" });
    setPrompt("");
    setSelectedImage(null);
    setSelectedImageSource("upload");
    setGenerationInputNotice(null);
    setContextSubmitting(true);

    try {
      const res = await fetch(`${API_URL}/projects/${encodeURIComponent(requestProjectId)}/context/messages`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        body: JSON.stringify({
          conversation_id: requestChatId,
          text,
          attachments: imageData ? [{
            attachment_id: `context-image-${userMessageId}`,
            kind: "image",
            name: "hardware-reference.png",
            media_type: imageData.match(/^data:([^;,]+)/)?.[1] || "image/png",
            data_url: imageData,
            source: selectedImageSource,
          }] : [],
        }),
      });
      if (!res.ok) {
        noteAuthResponseStatus(res.status);
        throw new Error(await readApiErrorMessage(res));
      }
      const data = await res.json();
      const turnKind = typeof data?.turn_kind === "string" ? data.turn_kind : "context";
      const persistedProjectId = typeof data?.design_brief?.project_id === "string"
        ? data.design_brief.project_id
        : typeof data?.workflow?.project_id === "string"
          ? data.workflow.project_id
          : "";
      const workflowState = typeof data?.workflow?.state === "string" ? data.workflow.state : "";
      const buildPlanId = typeof data?.build_execution?.plan_id === "string"
        ? data.build_execution.plan_id
        : "";
      const buildJobId = typeof data?.build_execution?.job_id === "string"
        ? data.build_execution.job_id
        : "";
      const buildExecutionStatus = typeof data?.build_execution?.status === "string"
        ? data.build_execution.status
        : "";
      const buildRequiresRequestBoundExecution = data?.build_execution?.request_bound_execution !== false;
      const buildIsActive = buildExecutionStatus === "planned" || buildExecutionStatus === "running";
      const buildPipelineProgress = buildPlanId
        ? createAgentPipelineProgress(defaultAgentPipelineSteps, generateProductImage, chatTimestamp(), buildJobId || null)
        : null;
      if (persistedProjectId) contextProjectIdsRef.current[requestChatId] = persistedProjectId;
      if (workflowState) {
        setContextWorkflowStates((current) => ({ ...current, [requestChatId]: workflowState }));
      }
      const assistantContent = typeof data?.assistant_message === "string"
        ? data.assistant_message
        : "How can I help with your hardware idea?";
      updateChatMessage(assistantMessageId, {
        content: assistantContent,
        status: buildIsActive ? "loading" : buildExecutionStatus === "failed" ? "error" : "success",
        pipelineProgress: buildPipelineProgress,
        contextProjectId: persistedProjectId || null,
        workflowState: workflowState || null,
        contextQuestions: Array.isArray(data?.questions) ? data.questions : [],
        contextSuggestions: normalizeContextSuggestions(data?.suggestions),
        buildPlanId: buildPlanId || null,
        buildJobId: buildJobId || null,
        buildRequiresRequestBoundExecution,
      });
      updateThreadMessage(requestChatId, assistantMessageId, {
        content: assistantContent,
        status: buildIsActive ? "loading" : buildExecutionStatus === "failed" ? "error" : "success",
        pipelineProgress: buildPipelineProgress,
        contextProjectId: persistedProjectId || null,
        workflowState: workflowState || null,
        contextQuestions: Array.isArray(data?.questions) ? data.questions : [],
        contextSuggestions: normalizeContextSuggestions(data?.suggestions),
        buildPlanId: buildPlanId || null,
        buildJobId: buildJobId || null,
        buildRequiresRequestBoundExecution,
      });
      setGenerationInputNotice(
        buildPlanId
          ? "Build started. Live agent progress is shown above."
          : turnKind === "context"
          ? "Project context updated."
          : turnKind === "proceed"
            ? "Project handed to the next agent stage."
            : null,
      );
      if (buildPlanId && buildJobId && persistedProjectId) {
        const run = beginContextBuildRun(
          persistedProjectId,
          buildPlanId,
          buildJobId,
          requestChatId,
          assistantMessageId,
        );
        watchContextBuild(
          persistedProjectId,
          buildPlanId,
          buildJobId,
          requestChatId,
          assistantMessageId,
          run,
          buildRequiresRequestBoundExecution,
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not save project context.";
      updateChatMessage(assistantMessageId, { content: message, status: "error" });
      updateThreadMessage(requestChatId, assistantMessageId, { content: message, status: "error" });
      setGenerationInputNotice(message);
    } finally {
      setContextSubmitting(false);
    }
  };

  const handleGatherContext = (event: React.FormEvent) => {
    event.preventDefault();
    void submitGatherContext();
  };

  const handleBuildNow = async () => {
    if (contextBuildStarting || contextSubmitting || activeGenerationRef.current) return;
    const requestChatId = activeChatId;
    const availableMessages = requestChatId
      ? chatThreads[requestChatId] || chatMessages
      : chatMessages;
    const persistedContextMessage = [...availableMessages]
      .reverse()
      .find((message) => Boolean(message.contextProjectId));
    const projectId = requestChatId
      ? contextProjectIdsRef.current[requestChatId] || persistedContextMessage?.contextProjectId || ""
      : "";
    if (!requestChatId || !projectId) {
      setGenerationInputNotice("Share the initial project context before starting the build.");
      return;
    }

    setContextBuildStarting(true);
    setGenerationInputNotice(null);
    try {
      const response = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/context/messages`, {
        method: "POST",
        headers: await generationRequestHeaders(),
        body: JSON.stringify({
          conversation_id: requestChatId,
          requested_tool: "build_project",
        }),
      });
      if (!response.ok) {
        noteAuthResponseStatus(response.status);
        throw new Error(await readApiErrorMessage(response));
      }
      const outcome = await response.json();
      const workflowState = typeof outcome?.workflow?.state === "string"
        ? outcome.workflow.state
        : "building";
      const buildPlanId = typeof outcome?.build_execution?.plan_id === "string"
        ? outcome.build_execution.plan_id
        : "";
      const buildJobId = typeof outcome?.build_execution?.job_id === "string"
        ? outcome.build_execution.job_id
        : "";
      const buildStatus = typeof outcome?.build_execution?.status === "string"
        ? outcome.build_execution.status
        : "planned";
      const buildRequiresRequestBoundExecution = outcome?.build_execution?.request_bound_execution !== false;
      const buildIsActive = buildStatus === "planned" || buildStatus === "running";
      const pipelineProgress = buildPlanId
        ? createAgentPipelineProgress(defaultAgentPipelineSteps, generateProductImage, chatTimestamp(), buildJobId || null)
        : null;
      contextProjectIdsRef.current[requestChatId] = projectId;
      setContextWorkflowStates((current) => ({ ...current, [requestChatId]: workflowState }));
      const message: ChatMessage = {
        id: newChatMessageId(),
        role: "assistant",
        content: typeof outcome?.assistant_message === "string"
          ? outcome.assistant_message
          : buildIsActive
            ? "I’ve started the design build."
            : "The first design revision is ready for review.",
        status: buildIsActive ? "loading" : buildStatus === "failed" ? "error" : "success",
        timestamp: chatTimestamp(),
        contextProjectId: projectId,
        workflowState,
        pipelineProgress,
        buildPlanId: buildPlanId || null,
        buildJobId: buildJobId || null,
        buildRequiresRequestBoundExecution,
      };
      appendChatMessage(message);
      appendThreadMessage(requestChatId, message);
      setGenerationInputNotice(
        buildIsActive ? "Build started. Live agent progress is shown above." : "Design ready for review.",
      );
      if (buildPlanId && buildJobId) {
        const run = beginContextBuildRun(projectId, buildPlanId, buildJobId, requestChatId, message.id);
        watchContextBuild(
          projectId,
          buildPlanId,
          buildJobId,
          requestChatId,
          message.id,
          run,
          buildRequiresRequestBoundExecution,
        );
      }
    } catch (error) {
      setGenerationInputNotice(error instanceof Error ? error.message : "Could not start the build.");
    } finally {
      setContextBuildStarting(false);
    }
  };
  return {
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
    cancelContextBuild,
    contextProjectIdsRef,
  };
}
