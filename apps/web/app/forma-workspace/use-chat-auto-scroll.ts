"use client";

import { useCallback, useLayoutEffect, useRef } from "react";

const FOLLOW_THRESHOLD_PX = 120;

export default function useChatAutoScroll(conversationKey: string, updateKey: unknown) {
  const containerRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const shouldFollowRef = useRef(true);
  const previousConversationRef = useRef(conversationKey);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    if (container.scrollHeight <= container.clientHeight + FOLLOW_THRESHOLD_PX) {
      shouldFollowRef.current = true;
      return;
    }

    const end = endRef.current;
    const distanceFromEnd = end
      ? end.getBoundingClientRect().bottom - container.getBoundingClientRect().bottom
      : container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldFollowRef.current = Math.abs(distanceFromEnd) <= FOLLOW_THRESHOLD_PX;
  }, []);

  useLayoutEffect(() => {
    const conversationChanged = previousConversationRef.current !== conversationKey;
    previousConversationRef.current = conversationKey;
    if (conversationChanged) shouldFollowRef.current = true;

    const container = containerRef.current;
    if (!container || !shouldFollowRef.current) return;
    const end = endRef.current;
    const nextTop = end
      ? container.scrollTop + end.getBoundingClientRect().bottom - container.getBoundingClientRect().bottom
      : container.scrollHeight;
    container.scrollTo({ top: nextTop, behavior: "auto" });
  }, [conversationKey, updateKey]);

  return { containerRef, endRef, handleScroll };
}
