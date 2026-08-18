"use client";

import { useEffect, useRef } from "react";

export type DeferredTaskOptions = {
  enabled?: boolean;
  delayMs?: number;
  timeoutMs?: number;
  taskKey?: string | number;
};

type ScheduleDeferredTaskOptions = Pick<DeferredTaskOptions, "delayMs" | "timeoutMs">;

/**
 * Schedules non-critical work after the browser has had an opportunity to
 * paint. The timeout keeps the task from waiting indefinitely for idle time.
 */
export function scheduleDeferredTask(
  task: () => void,
  { delayMs = 0, timeoutMs = 1500 }: ScheduleDeferredTaskOptions = {}
) {
  if (typeof window === "undefined") return () => {};

  let cancelled = false;
  let animationFrameId: number | null = null;
  let idleCallbackId: number | null = null;
  let delayId: number | null = null;
  let timeoutId: number | null = null;

  const runTask = () => {
    if (cancelled) return;
    cancelled = true;
    task();
  };

  const waitForIdle = () => {
    if (cancelled) return;

    if (typeof window.requestIdleCallback === "function") {
      idleCallbackId = window.requestIdleCallback(runTask, {
        timeout: Math.max(0, timeoutMs),
      });
      return;
    }

    timeoutId = window.setTimeout(runTask, 0);
  };

  animationFrameId = window.requestAnimationFrame(() => {
    animationFrameId = null;
    if (cancelled) return;
    if (delayMs > 0) {
      delayId = window.setTimeout(() => {
        delayId = null;
        waitForIdle();
      }, delayMs);
      return;
    }
    waitForIdle();
  });

  return () => {
    cancelled = true;
    if (animationFrameId !== null) window.cancelAnimationFrame(animationFrameId);
    if (idleCallbackId !== null && typeof window.cancelIdleCallback === "function") {
      window.cancelIdleCallback(idleCallbackId);
    }
    if (delayId !== null) window.clearTimeout(delayId);
    if (timeoutId !== null) window.clearTimeout(timeoutId);
  };
}

/**
 * Runs a task after first paint. Callback changes are read through a ref, so
 * they do not cancel and reschedule already-deferred work.
 */
export function useDeferredTask(
  task: () => void,
  { enabled = true, delayMs = 0, timeoutMs = 1500, taskKey = "default" }: DeferredTaskOptions = {}
) {
  const taskRef = useRef(task);
  taskRef.current = task;

  useEffect(() => {
    if (!enabled) return;
    return scheduleDeferredTask(() => taskRef.current(), { delayMs, timeoutMs });
  }, [delayMs, enabled, taskKey, timeoutMs]);
}
