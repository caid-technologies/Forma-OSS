export const CONTEXT_BUILD_POLL_MS = 2000;
export const CONTEXT_BUILD_FIRST_POLL_MS = 750;
export const CONTEXT_BUILD_MAX_ATTEMPTS = 600;
export const CONTEXT_BUILD_TIMEOUT_MESSAGE =
  "Build progress timed out. Retry to resume from the latest saved stage.";

export function contextBuildWatchKey(projectId: string, planId: string) {
  return `${projectId}:${planId}`;
}

export function isActiveBuildStatus(status: string | null | undefined) {
  return status === "planned" || status === "running";
}

export function shouldResumeDetachedBuild(options: {
  requestBoundExecution: boolean;
  alreadyWatching: boolean;
}) {
  return !options.requestBoundExecution && !options.alreadyWatching;
}
