"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type VideoGenerationMode = "image-to-video" | "video-to-video";

export type VideoModelOption = {
  id: string;
  label: string;
  mode: VideoGenerationMode;
};

type VideoGenerationAvailability = {
  configured: boolean;
  reason: string | null;
};

type UseVideoModelsOptions = {
  apiUrl: string;
  enabled: boolean;
  onAvailabilityChange: (availability: VideoGenerationAvailability) => void;
};

const DEFAULT_ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"];

function normalizeVideoGenerationMode(value: unknown): VideoGenerationMode {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  return ["video-to-video", "video_to_video", "video2video", "v2v", "video"].includes(normalized)
    ? "video-to-video"
    : "image-to-video";
}

export function useVideoModels({
  apiUrl,
  enabled,
  onAvailabilityChange,
}: UseVideoModelsOptions) {
  const [models, setModels] = useState<VideoModelOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [aspectRatios, setAspectRatios] = useState(DEFAULT_ASPECT_RATIOS);
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const loadedRef = useRef(false);
  const loadingRef = useRef(false);
  const requestIdRef = useRef(0);
  const availabilityCallbackRef = useRef(onAvailabilityChange);
  availabilityCallbackRef.current = onAvailabilityChange;

  const load = useCallback(async (force = false) => {
    if ((!enabled && !force) || (loadedRef.current && !force) || loadingRef.current) return;

    const requestId = ++requestIdRef.current;
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/video/models`);
      if (!response.ok) {
        let message = `Request failed with ${response.status}`;
        try {
          const payload = await response.json();
          message = typeof payload?.detail === "string" ? payload.detail : message;
        } catch {
          // Keep the status-based fallback.
        }
        throw new Error(message);
      }

      const data = await response.json();
      const nextModels: VideoModelOption[] = (Array.isArray(data.models) ? data.models : [])
        .map((item: any) => {
          if (typeof item === "string") {
            return { id: item, label: item, mode: "image-to-video" as VideoGenerationMode };
          }
          const id = typeof item?.id === "string" ? item.id : typeof item?.model === "string" ? item.model : "";
          if (!id) return null;
          return {
            id,
            label: typeof item?.label === "string" ? item.label : id,
            mode: normalizeVideoGenerationMode(item?.mode || item?.type || item?.inputType || item?.input_type),
          };
        })
        .filter((item: VideoModelOption | null): item is VideoModelOption => Boolean(item));

      if (requestIdRef.current !== requestId) return;
      loadedRef.current = true;
      setModels(nextModels);

      const rawAspectRatios = data.aspectRatioOptions || data.aspect_ratio_options;
      const configuredAspectRatios = (Array.isArray(rawAspectRatios) ? rawAspectRatios : [])
        .map((item: any) => (typeof item === "string" ? item.trim() : typeof item?.id === "string" ? item.id.trim() : ""))
        .filter(Boolean);
      const nextAspectRatios = configuredAspectRatios.length ? configuredAspectRatios : DEFAULT_ASPECT_RATIOS;
      setAspectRatios(nextAspectRatios);
      setAspectRatio((current) => nextAspectRatios.includes(current) ? current : nextAspectRatios[0] || "16:9");

      if ("generationConfigured" in data || "generation_configured" in data) {
        availabilityCallbackRef.current({
          configured: Boolean(data.generationConfigured ?? data.generation_configured),
          reason: typeof data.reason === "string" ? data.reason : null,
        });
      }

      setSelectedModel((current) => {
        if (current && nextModels.some((item) => item.id === current)) return current;
        const defaultModel = data.defaultModel || data.default_model;
        if (
          typeof defaultModel === "string" &&
          nextModels.some((item) => item.id === defaultModel && item.mode === "image-to-video")
        ) {
          return defaultModel;
        }
        return nextModels.find((item) => item.mode === "image-to-video")?.id || nextModels[0]?.id || "";
      });
    } catch (loadError) {
      if (requestIdRef.current === requestId) {
        setError(loadError instanceof Error ? loadError.message : "Video models are unavailable.");
      }
    } finally {
      loadingRef.current = false;
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [apiUrl, enabled]);

  useEffect(() => {
    if (!enabled || loadedRef.current) return;
    void load();
  }, [enabled, load]);

  return {
    models,
    loading,
    error,
    selectedModel,
    setSelectedModel,
    aspectRatios,
    aspectRatio,
    setAspectRatio,
    refresh: () => load(true),
  };
}
