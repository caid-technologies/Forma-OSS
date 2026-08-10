"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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

export type A2AJob = {
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
  owner_user_id?: string | null;
  owner_username?: string | null;
  owner_display_name?: string | null;
  owner_email?: string | null;
  owner_github_username?: string | null;
};

export type BackendLogs = {
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

export type HeaderFactory = () => HeadersInit | Promise<HeadersInit>;
export type ApiErrorReader = (response: Response) => Promise<string>;

type ApiDependencies = {
  apiUrl: string;
  getHeaders: HeaderFactory;
  readError: ApiErrorReader;
};

type RefreshOptions = {
  silent?: boolean;
};

const ADMIN_REQUEST_TIMEOUT_MS = 15000;
const adminSessionCache = new Map<string, boolean>();

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = ADMIN_REQUEST_TIMEOUT_MS
) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export type UseAdminSessionOptions = ApiDependencies & {
  enabled: boolean;
  authRequired: boolean;
  authReady: boolean;
  signedIn: boolean | null | undefined;
  requestScopeKey?: string | null;
};

export type UseAdminSessionResult = {
  isAdmin: boolean;
  loaded: boolean;
  loading: boolean;
  refresh: () => Promise<void>;
};

export function useAdminSession({
  apiUrl,
  getHeaders,
  readError,
  enabled,
  authRequired,
  authReady,
  signedIn,
  requestScopeKey,
}: UseAdminSessionOptions): UseAdminSessionResult {
  const cacheKey = `${apiUrl}:${requestScopeKey || (authRequired ? "anonymous" : "local")}`;
  const [isAdmin, setIsAdmin] = useState(() => adminSessionCache.get(cacheKey) || false);
  const [loaded, setLoaded] = useState(() => adminSessionCache.has(cacheKey));
  const [loading, setLoading] = useState(false);
  const requestIdRef = useRef(0);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const refresh = useCallback(async () => {
    if (!enabled) return;

    const requestId = ++requestIdRef.current;
    if (authRequired && !authReady) {
      setIsAdmin(false);
      setLoaded(false);
      setLoading(false);
      return;
    }
    if (authRequired && !signedIn) {
      setIsAdmin(false);
      setLoaded(true);
      setLoading(false);
      adminSessionCache.set(cacheKey, false);
      return;
    }

    setLoading(true);
    try {
      const response = await fetchWithTimeout(`${apiUrl}/admin/session`, {
        headers: await getHeaders(),
      });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      if (requestIdRef.current === requestId && enabledRef.current) {
        const nextIsAdmin = Boolean(payload?.is_admin);
        adminSessionCache.set(cacheKey, nextIsAdmin);
        setIsAdmin(nextIsAdmin);
      }
    } catch (error) {
      if (requestIdRef.current === requestId && enabledRef.current) {
        console.error("Error fetching admin session", error);
        adminSessionCache.set(cacheKey, false);
        setIsAdmin(false);
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoaded(true);
        setLoading(false);
      }
    }
  }, [apiUrl, authReady, authRequired, cacheKey, enabled, getHeaders, readError, signedIn]);

  useEffect(() => {
    if (!enabled) {
      requestIdRef.current += 1;
      setIsAdmin(false);
      setLoaded(false);
      setLoading(false);
      return;
    }

    if (adminSessionCache.has(cacheKey)) {
      setIsAdmin(Boolean(adminSessionCache.get(cacheKey)));
      setLoaded(true);
    } else {
      setIsAdmin(false);
      setLoaded(false);
    }
    void refresh();
    return () => {
      requestIdRef.current += 1;
    };
  }, [cacheKey, enabled, refresh]);

  return { isAdmin, loaded, loading, refresh };
}

export type UseJobsOptions = ApiDependencies & {
  enabled: boolean;
  requestScopeKey?: string | null;
  pollIntervalMs?: number;
  initialStatusFilter?: string;
};

export type UseJobsResult = {
  jobs: A2AJob[];
  loading: boolean;
  error: string | null;
  statusFilter: string;
  setStatusFilter: (status: string) => void;
  lastUpdatedAt: string | null;
  refresh: (status?: string, options?: RefreshOptions) => Promise<void>;
  fetchJob: (jobId: string) => Promise<A2AJob | null>;
};

export function useJobs({
  apiUrl,
  getHeaders,
  readError: _readError,
  enabled,
  requestScopeKey = "default",
  pollIntervalMs = 5000,
  initialStatusFilter = "all",
}: UseJobsOptions): UseJobsResult {
  const [jobs, setJobs] = useState<A2AJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const refreshTokensRef = useRef<Record<string, object>>({});
  const jobRequestsRef = useRef<Record<string, Promise<A2AJob | null>>>({});
  const requestScopeRef = useRef(requestScopeKey);
  requestScopeRef.current = requestScopeKey;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const refresh = useCallback(async (
    status = statusFilter,
    options: RefreshOptions = {}
  ) => {
    if (!enabled) return;

    const refreshKey = status || "all";
    if (refreshTokensRef.current[refreshKey]) return;
    const refreshToken = {};
    refreshTokensRef.current[refreshKey] = refreshToken;

    const requestId = ++requestIdRef.current;
    if (!options.silent) setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ limit: "200" });
      if (status !== "all") params.set("status", status);
      const nextJobs: A2AJob[] = [];
      const errors: string[] = [];

      try {
        const response = await fetchWithTimeout(`${apiUrl}/a2a/jobs?${params.toString()}`, {
          headers: await getHeaders(),
        });
        if (!response.ok) throw new Error(`A2A jobs endpoint returned ${response.status}`);
        const payload = await response.json();
        if (Array.isArray(payload)) nextJobs.push(...payload);
      } catch (requestError) {
        console.error("Error fetching A2A jobs", requestError);
        errors.push("A2A jobs");
      }

      try {
        const response = await fetchWithTimeout(`${apiUrl}/example-project-object-jobs?${params.toString()}`, {
          headers: await getHeaders(),
        });
        if (!response.ok) throw new Error(`Example jobs endpoint returned ${response.status}`);
        const payload = await response.json();
        if (Array.isArray(payload)) nextJobs.push(...payload);
      } catch (requestError) {
        console.error("Error fetching example project object jobs", requestError);
        errors.push("example jobs");
      }

      nextJobs.sort((left, right) => {
        const leftTime = new Date(left.created_at || left.updated_at || 0).getTime();
        const rightTime = new Date(right.created_at || right.updated_at || 0).getTime();
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
      });

      if (requestIdRef.current !== requestId || !enabledRef.current) return;
      setJobs(nextJobs);
      setLastUpdatedAt(new Date().toISOString());
      if (errors.length && !nextJobs.length) {
        setError("Jobs are unavailable");
      } else if (errors.length) {
        setError(`${errors.join(" and ")} unavailable`);
      }
    } catch (requestError) {
      if (requestIdRef.current === requestId && enabledRef.current) {
        console.error("Error fetching jobs", requestError);
        setError("Jobs are unavailable");
      }
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
      if (refreshTokensRef.current[refreshKey] === refreshToken) {
        delete refreshTokensRef.current[refreshKey];
      }
    }
  }, [apiUrl, enabled, getHeaders, statusFilter]);

  const fetchJob = useCallback(async (jobId: string): Promise<A2AJob | null> => {
    if (!jobId) return null;
    const scopeKey = requestScopeKey || "anonymous";
    const requestKey = `${scopeKey}\u0000${jobId}`;
    const pendingRequest = jobRequestsRef.current[requestKey];
    if (pendingRequest) return pendingRequest;

    const request = (async () => {
      try {
        const response = await fetchWithTimeout(`${apiUrl}/a2a/jobs/${encodeURIComponent(jobId)}`, {
          headers: await getHeaders(),
        });
        if (!response.ok) return null;
        const job = await response.json() as A2AJob;
        return requestScopeRef.current === requestScopeKey ? job : null;
      } catch (requestError) {
        console.error("Error fetching A2A job", requestError);
        return null;
      }
    })();
    jobRequestsRef.current[requestKey] = request;
    try {
      return await request;
    } finally {
      if (jobRequestsRef.current[requestKey] === request) delete jobRequestsRef.current[requestKey];
    }
  }, [apiUrl, getHeaders, requestScopeKey]);

  useEffect(() => {
    jobRequestsRef.current = {};
  }, [requestScopeKey]);

  useEffect(() => {
    if (!enabled) {
      requestIdRef.current += 1;
      refreshTokensRef.current = {};
      setLoading(false);
      return;
    }

    void refresh(statusFilter);
    const poll = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void refresh(statusFilter, { silent: true });
      }
    };
    const intervalId = window.setInterval(poll, pollIntervalMs);
    document.addEventListener("visibilitychange", poll);

    return () => {
      requestIdRef.current += 1;
      refreshTokensRef.current = {};
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [enabled, pollIntervalMs, refresh, statusFilter]);

  return {
    jobs,
    loading,
    error,
    statusFilter,
    setStatusFilter,
    lastUpdatedAt,
    refresh,
    fetchJob,
  };
}

export type UseBackendLogsOptions = ApiDependencies & {
  enabled: boolean;
  pollIntervalMs?: number;
};

export type UseBackendLogsResult = {
  logs: BackendLogs | null;
  loading: boolean;
  error: string | null;
  lastUpdatedAt: string | null;
  refresh: (options?: RefreshOptions) => Promise<void>;
};

export function useBackendLogs({
  apiUrl,
  getHeaders,
  readError,
  enabled,
  pollIntervalMs = 5000,
}: UseBackendLogsOptions): UseBackendLogsResult {
  const [logs, setLogs] = useState<BackendLogs | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const refreshTokenRef = useRef<object | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const refresh = useCallback(async (options: RefreshOptions = {}) => {
    if (!enabled) return;

    if (refreshTokenRef.current) return;
    const refreshToken = {};
    refreshTokenRef.current = refreshToken;

    const requestId = ++requestIdRef.current;
    if (!options.silent) setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ lines: "300" });
      const response = await fetchWithTimeout(`${apiUrl}/logs/backend?${params.toString()}`, {
        headers: await getHeaders(),
      });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      if (requestIdRef.current === requestId && enabledRef.current) {
        setLogs(payload);
        setLastUpdatedAt(new Date().toISOString());
      }
    } catch (requestError) {
      if (requestIdRef.current === requestId && enabledRef.current) {
        console.error("Error fetching backend logs", requestError);
        setError(requestError instanceof Error ? requestError.message : "Backend logs are unavailable");
      }
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
      if (refreshTokenRef.current === refreshToken) refreshTokenRef.current = null;
    }
  }, [apiUrl, enabled, getHeaders, readError]);

  useEffect(() => {
    if (!enabled) {
      requestIdRef.current += 1;
      refreshTokenRef.current = null;
      setLoading(false);
      return;
    }

    void refresh();
    const poll = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void refresh({ silent: true });
      }
    };
    const intervalId = window.setInterval(poll, pollIntervalMs);
    document.addEventListener("visibilitychange", poll);

    return () => {
      requestIdRef.current += 1;
      refreshTokenRef.current = null;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [enabled, pollIntervalMs, refresh]);

  return { logs, loading, error, lastUpdatedAt, refresh };
}
