"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export default function useChromeHeaderScroll(resetKey?: unknown) {
  const lastHeaderScrollRef = useRef(0);
  const [headerAway, setHeaderAway] = useState(false);

  useEffect(() => {
    lastHeaderScrollRef.current = 0;
    setHeaderAway(false);
  }, [resetKey]);

  const updateFromContainer = useCallback((container: HTMLElement | null | undefined) => {
    if (!container) return;
    const top = container.scrollTop;
    const delta = top - lastHeaderScrollRef.current;
    lastHeaderScrollRef.current = top;
    if (top <= 16) {
      setHeaderAway(false);
      return;
    }
    if (delta > 8) setHeaderAway(true);
    else if (delta < -8) setHeaderAway(false);
  }, []);

  const onCapturedScroll = useCallback((event: Event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.scrollHeight <= target.clientHeight + 1) return;
    updateFromContainer(target);
  }, [updateFromContainer]);

  const bindCapture = useCallback((node: HTMLElement | null) => {
    if (!node) return () => {};
    node.addEventListener("scroll", onCapturedScroll, true);
    return () => node.removeEventListener("scroll", onCapturedScroll, true);
  }, [onCapturedScroll]);

  return { headerAway, updateFromContainer, bindCapture };
}
