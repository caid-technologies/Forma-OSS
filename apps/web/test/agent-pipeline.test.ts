import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createAgentPipelineProgress,
  mergeMessagePipelineProgressFromJob,
} from "../app/forma-workspace/lib/agent-pipeline";
import { defaultAgentPipelineSteps } from "../app/forma-workspace/workspace-constants";
import type { ChatMessage } from "../app/forma-workspace/types";

test("pipeline merge advances a loading chat message from worker events", () => {
  const seed = createAgentPipelineProgress(defaultAgentPipelineSteps, false, "2026-01-01T00:00:00.000Z", "job-1");
  const message: ChatMessage = {
    id: "msg-1",
    role: "assistant",
    content: "Thinking…",
    status: "loading",
    timestamp: "2026-01-01T00:00:00.000Z",
    pipelineProgress: seed,
  };
  const next = mergeMessagePipelineProgressFromJob(message, {
    job_id: "job-1",
    action: "forma.generate_project",
    sender: "worker-orchestrator",
    recipient: "forma",
    status: "running",
    started_at: "2026-01-01T00:00:00.000Z",
    progress_events: [
      { step_id: "safety_guardrail", status: "completed", observed_at: "2026-01-01T00:00:01.000Z" },
      { step_id: "intent_parser", status: "started", observed_at: "2026-01-01T00:00:02.000Z" },
    ],
  }, seed, false);

  assert.equal(next.status, "loading");
  assert.equal(next.pipelineProgress?.synced, true);
  assert.ok((next.pipelineProgress?.currentStepIndex || 0) >= 1);
});
