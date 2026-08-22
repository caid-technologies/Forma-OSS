"use client";

import {
  AlertTriangle,
  CheckCircle,
  ExternalLink,
  Eye,
  Film,
  Layers,
  Paperclip,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import CopyButton from "../../components/copy-button";
import { isFinalVideoStatus, formatBytes } from "./admin-panels";
import { previewableImageSrc } from "./project-gallery";
import type { ProjectImageCandidate } from "../../lib/project-images";
import {
  VIDEO_PROMPT_MAX_CHARS,
  videoIdentity,
  videoLabel,
  videoPromptText,
  videoSourceUrl,
  type StoredVideoInfo,
} from "./use-project-video";
import type { VideoGenerationMode, VideoModelOption } from "./use-video-models";

export function videoStatusTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded" || normalized === "success") {
    return "border-[rgb(var(--forma-green-rgb)/0.35)] bg-[rgb(var(--forma-green-rgb)/0.1)] text-[rgb(var(--forma-green-rgb))]";
  }
  if (normalized === "failed" || normalized === "failure" || normalized === "error") {
    return "border-[rgb(var(--forma-red-rgb)/0.35)] bg-[rgb(var(--forma-red-rgb)/0.1)] text-[rgb(var(--forma-red-rgb))]";
  }
  if (normalized === "running" || normalized === "loading" || normalized === "reviewing") {
    return "border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] text-[rgb(var(--forma-cyan-rgb))]";
  }
  if (normalized === "queued") {
    return "border-[rgb(var(--forma-yellow-rgb)/0.35)] bg-[rgb(var(--forma-yellow-rgb)/0.1)] text-[rgb(var(--forma-yellow-rgb))]";
  }
  return "border-[var(--forma-border)] bg-[var(--forma-surface-muted)] text-[var(--forma-text-muted)]";
}

export function VideoPanel({
  projectId,
  readOnly,
  models,
  modelsLoading,
  modelsError,
  selectedModel,
  setSelectedModel,
  mode,
  setMode,
  imageInput,
  setImageInput,
  imageOptions,
  selectedImageSources,
  setSelectedImageSources,
  defaultImage,
  sourceVideoUrl,
  setSourceVideoUrl,
  prompt,
  setPrompt,
  duration,
  setDuration,
  aspectRatio,
  setAspectRatio,
  aspectRatios,
  status,
  statusMessage,
  requestId,
  storedVideo,
  gallery,
  galleryLoading,
  galleryError,
  generationAvailable,
  generationUnavailableReason,
  reviewStatus,
  reviewMessage,
  reviewAvailable,
  reviewUnavailableReason,
  selectedReviewVideoKey,
  setSelectedReviewVideoKey,
  makeNewVideo,
  setMakeNewVideo,
  promptGenerating,
  promptMessage,
  onGenerate,
  onGeneratePrompt,
  onReview,
  onReviewVideo,
  onUploadImage,
  onUseProjectImage,
  onRefreshGallery,
  canGenerate,
  canReview,
  canMakeNewVideo,
  canGeneratePrompt,
}: {
  projectId: string | null;
  readOnly: boolean;
  models: VideoModelOption[];
  modelsLoading: boolean;
  modelsError: string | null;
  selectedModel: string;
  setSelectedModel: (value: string) => void;
  mode: VideoGenerationMode;
  setMode: (value: VideoGenerationMode) => void;
  imageInput: string;
  setImageInput: (value: string) => void;
  imageOptions: ProjectImageCandidate[];
  selectedImageSources: string[];
  setSelectedImageSources: (value: string[]) => void;
  defaultImage: string;
  sourceVideoUrl: string;
  setSourceVideoUrl: (value: string) => void;
  prompt: string;
  setPrompt: (value: string) => void;
  duration: string;
  setDuration: (value: string) => void;
  aspectRatio: string;
  setAspectRatio: (value: string) => void;
  aspectRatios: string[];
  status: string;
  statusMessage: string | null;
  requestId: string | null;
  storedVideo: StoredVideoInfo | null;
  gallery: StoredVideoInfo[];
  galleryLoading: boolean;
  galleryError: string | null;
  generationAvailable: boolean;
  generationUnavailableReason: string | null;
  reviewStatus: string;
  reviewMessage: string | null;
  reviewAvailable: boolean;
  reviewUnavailableReason: string | null;
  selectedReviewVideoKey: string | null;
  setSelectedReviewVideoKey: (value: string | null) => void;
  makeNewVideo: boolean;
  setMakeNewVideo: (value: boolean) => void;
  promptGenerating: boolean;
  promptMessage: string | null;
  onGenerate: () => void;
  onGeneratePrompt: () => void;
  onReview: () => void;
  onReviewVideo: (video: StoredVideoInfo) => void;
  onUploadImage: () => void;
  onUseProjectImage: () => void;
  onRefreshGallery: () => void;
  canGenerate: boolean;
  canReview: boolean;
  canMakeNewVideo: boolean;
  canGeneratePrompt: boolean;
}) {
  const modeModels = models.filter((model) => model.mode === mode);
  const sourceVideos = gallery
    .map((video, index) => ({
      video,
      url: videoSourceUrl(video),
      label: videoLabel(video, `Video ${index + 1}`),
    }))
    .filter((item) => item.url);
  const videoToVideoAvailable = sourceVideos.length > 0;
  const selectedImagePreviewSource = selectedImageSources[0] || imageInput;
  const imagePreview = mode === "image-to-video" ? previewableImageSrc(selectedImagePreviewSource) : null;
  const sourceVideoPreview = mode === "video-to-video" ? sourceVideoUrl : "";
  const isGenerating = status === "loading" || Boolean(requestId && !storedVideo && !isFinalVideoStatus(status));
  const isReviewing = reviewStatus === "loading";
  const generateDisabled = !canGenerate || isGenerating || !modeModels.length;
  const reviewDisabled = !canReview || isReviewing;
  const savedHref = readOnly ? null : storedVideo?.publicUrl || null;
  const allProjectImagesSelected = imageOptions.length > 0 && imageOptions.every((candidate) => selectedImageSources.includes(candidate.src));
  const toggleImageSource = (source: string) => {
    setSelectedImageSources(
      selectedImageSources.includes(source)
        ? selectedImageSources.filter((item) => item !== source)
        : [...selectedImageSources, source]
    );
  };

  if (!generationAvailable) {
    return (
      <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[var(--forma-page)] px-4 py-5 text-[var(--forma-text)] sm:px-5 sm:py-6">
        <div className="mx-auto min-w-0 max-w-[890px]">
          <section className="rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4 sm:p-5">
            <div className="flex flex-col gap-4 border-b border-[var(--forma-border)] pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] text-[rgb(var(--forma-cyan-rgb))]">
                  <Film className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Media</div>
                  <h2 className="mt-1 text-sm font-semibold tracking-tight text-[var(--forma-text-strong)]">Video</h2>
                  <div className="mt-1.5 truncate font-mono text-[10px] text-[var(--forma-text-muted)]">{projectId || "No project id"}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={onReview}
                disabled={reviewDisabled}
                className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] px-3 text-xs font-medium text-[rgb(var(--forma-cyan-rgb))] transition-colors hover:border-[rgb(var(--forma-cyan-rgb)/0.55)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isReviewing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Review
              </button>
            </div>

            {readOnly && (
              <div className="mt-5 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-3 text-xs leading-5 text-[var(--forma-text-secondary)]">
                Read-only project. Video actions are available only to the owner.
              </div>
            )}

            <div className="mt-5 rounded-lg border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] p-4">
              <div className="flex items-start gap-3">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--forma-cyan-rgb))]" />
                <div className="min-w-0">
                  <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[rgb(var(--forma-cyan-rgb))]">Alpha</div>
                  <p className="mt-2 text-sm leading-6 text-[var(--forma-text-body)]">
                    We are in alpha and video generation is coming soon.
                  </p>
                  {generationUnavailableReason && (
                    <p className="mt-2 break-words text-xs leading-5 text-[var(--forma-text-secondary)]">{generationUnavailableReason}</p>
                  )}
                </div>
              </div>
            </div>

            <VideoReviewStatus
              status={reviewStatus}
              message={reviewMessage}
              available={reviewAvailable}
              unavailableReason={reviewUnavailableReason}
              isReviewing={isReviewing}
              makeNewVideo={makeNewVideo}
              setMakeNewVideo={setMakeNewVideo}
              canMakeNewVideo={canMakeNewVideo}
            />

            <VideoGallery
              videos={gallery}
              loading={galleryLoading}
              error={galleryError}
              onRefresh={onRefreshGallery}
              selectedKey={selectedReviewVideoKey}
              onSelect={setSelectedReviewVideoKey}
              onReview={onReviewVideo}
              canReview={canReview}
              canOpenAssets={!readOnly}
              reviewing={isReviewing}
            />
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[var(--forma-page)] px-4 py-5 text-[var(--forma-text)] sm:px-5 sm:py-6">
      <div className="mx-auto flex min-w-0 max-w-[890px] flex-col gap-4">
        <section className="min-w-0 rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4 sm:p-5">
          <div className="mb-5 flex flex-col gap-4 border-b border-[var(--forma-border)] pb-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] text-[rgb(var(--forma-cyan-rgb))]">
                <Film className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Media</div>
                <h2 className="mt-1 text-sm font-semibold tracking-tight text-[var(--forma-text-strong)]">Video</h2>
                <div className="mt-1.5 truncate font-mono text-[10px] text-[var(--forma-text-muted)]">{projectId || "No project id"}</div>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                type="button"
                onClick={onReview}
                disabled={reviewDisabled}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] px-3 text-xs font-medium text-[rgb(var(--forma-cyan-rgb))] transition-colors hover:border-[rgb(var(--forma-cyan-rgb)/0.55)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isReviewing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Review
              </button>
              <button
                type="button"
                onClick={onGenerate}
                disabled={generateDisabled}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[var(--forma-text-strong)] bg-[var(--forma-text-strong)] px-3 text-xs font-medium text-[var(--forma-page)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isGenerating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
                Generate
              </button>
            </div>
          </div>

          {readOnly && (
            <div className="mb-5 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-3 text-xs leading-5 text-[var(--forma-text-secondary)]">
              Read-only project. Video actions are available only to the owner.
            </div>
          )}

          <div className="mb-4 grid grid-cols-2 overflow-hidden rounded-lg border border-[var(--forma-border)]">
            {([
              { value: "image-to-video" as VideoGenerationMode, label: "Image" },
              { value: "video-to-video" as VideoGenerationMode, label: "Video", disabled: !videoToVideoAvailable },
            ]).map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  if (!item.disabled) setMode(item.value);
                }}
                disabled={item.disabled}
                className={`flex h-10 items-center justify-center gap-2 border-r border-[var(--forma-border)] text-xs font-medium last:border-r-0 ${
                  mode === item.value
                    ? "bg-[var(--forma-surface)] text-[var(--forma-text-strong)]"
                    : "bg-[var(--forma-surface-muted)] text-[var(--forma-text-muted)] hover:text-[var(--forma-text-strong)]"
                } disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-[var(--forma-text-muted)]`}
              >
                {item.value === "video-to-video" ? <Film className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                {item.label}
              </button>
            ))}
          </div>

          <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_170px_180px]">
            <label className="block text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
              Model
              <select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                disabled={modelsLoading || !modeModels.length}
                className="mt-2 h-10 w-full rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 text-sm font-normal tracking-normal text-[var(--forma-text-body)] outline-none focus:border-[rgb(var(--forma-cyan-rgb))] disabled:opacity-50"
              >
                {!modeModels.length && <option value="">No models</option>}
                {modeModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
              Aspect ratio
              <select
                value={aspectRatio}
                onChange={(event) => setAspectRatio(event.target.value)}
                className="mt-2 h-10 w-full rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 text-sm font-normal tracking-normal text-[var(--forma-text-body)] outline-none focus:border-[rgb(var(--forma-cyan-rgb))]"
              >
                {aspectRatios.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Duration</div>
              <div className="mt-2 grid grid-cols-2 overflow-hidden rounded-lg border border-[var(--forma-border)]">
                {["5", "10"].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setDuration(value)}
                    className={`h-10 border-r border-[var(--forma-border)] text-xs font-medium last:border-r-0 ${
                      duration === value
                        ? "bg-[var(--forma-surface)] text-[var(--forma-text-strong)]"
                        : "bg-[var(--forma-surface-muted)] text-[var(--forma-text-muted)] hover:text-[var(--forma-text-strong)]"
                    }`}
                  >
                    {value}s
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="video-prompt" className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
                Prompt
              </label>
              <button
                type="button"
                onClick={onGeneratePrompt}
                disabled={!canGeneratePrompt}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] px-3 text-[11px] font-medium text-[rgb(var(--forma-cyan-rgb))] transition-colors hover:border-[rgb(var(--forma-cyan-rgb)/0.55)] disabled:cursor-not-allowed disabled:opacity-40"
                title="Generate an image-to-video prompt from project namespaces"
              >
                {promptGenerating ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Generate prompt
              </button>
            </div>
            <textarea
              id="video-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={VIDEO_PROMPT_MAX_CHARS}
              placeholder="Slow orbit, reveal ports, show display glow."
              className="mt-2 min-h-[132px] w-full resize-none rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 py-3 text-sm font-normal leading-6 tracking-normal text-[var(--forma-text-body)] outline-none placeholder:text-[var(--forma-text-muted)] focus:border-[rgb(var(--forma-cyan-rgb))]"
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              {promptMessage ? (
                <p className="break-words text-[11px] leading-5 text-[var(--forma-text-secondary)]">{promptMessage}</p>
              ) : (
                <span />
              )}
              <span className={`font-mono text-[10px] ${prompt.length > VIDEO_PROMPT_MAX_CHARS - 120 ? "text-[rgb(var(--forma-yellow-rgb))]" : "text-[var(--forma-text-muted)]"}`}>
                {prompt.length}/{VIDEO_PROMPT_MAX_CHARS}
              </span>
            </div>
          </div>

          {mode === "image-to-video" ? (
            <div className="mt-5 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-3">
              <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Image source</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onUploadImage}
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 text-xs font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-page)] hover:text-[var(--forma-text-strong)]"
                  >
                    <Paperclip className="h-4 w-4" />
                    Upload
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedImageSources(allProjectImagesSelected ? [] : imageOptions.map((candidate) => candidate.src))}
                    disabled={!imageOptions.length}
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 text-xs font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-page)] hover:text-[var(--forma-text-strong)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Layers className="h-4 w-4" />
                    {allProjectImagesSelected ? "Clear" : "All"}
                  </button>
                  <button
                    type="button"
                    onClick={onUseProjectImage}
                    disabled={!defaultImage}
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 text-xs font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-page)] hover:text-[var(--forma-text-strong)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Eye className="h-4 w-4" />
                    First
                  </button>
                </div>
              </div>

              {imageOptions.length > 0 && (
                <div className="mb-3 grid gap-2 sm:grid-cols-3">
                  {imageOptions.map((candidate) => {
                    const selected = selectedImageSources.includes(candidate.src);
                    return (
                      <button
                        key={candidate.src}
                        type="button"
                        onClick={() => toggleImageSource(candidate.src)}
                        className={`min-w-0 rounded-lg border p-2 text-left transition ${
                          selected
                            ? "border-[rgb(var(--forma-cyan-rgb)/0.55)] bg-[var(--forma-surface)] text-[rgb(var(--forma-cyan-rgb))]"
                            : "border-[var(--forma-border)] bg-[var(--forma-surface)] text-[var(--forma-text-muted)] hover:border-[var(--forma-text-muted)] hover:text-[var(--forma-text-strong)]"
                        }`}
                        aria-pressed={selected}
                      >
                        <div className="relative h-20 overflow-hidden rounded-md bg-[var(--forma-surface-muted)]">
                          <img src={candidate.src} alt={candidate.label} className="h-full w-full object-cover" />
                          <span className={`absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-md border text-[10px] font-medium ${
                            selected
                              ? "border-[rgb(var(--forma-cyan-rgb))] bg-[rgb(var(--forma-cyan-rgb))] text-[var(--forma-page)]"
                              : "border-[var(--forma-border)] bg-[rgb(var(--forma-chrome-rgb)/0.8)] text-[var(--forma-text-strong)]"
                          }`}>
                            {selected ? <CheckCircle className="h-3.5 w-3.5" /> : null}
                          </span>
                        </div>
                        <div className="mt-2 truncate text-[10px] font-medium">{candidate.label}</div>
                      </button>
                    );
                  })}
                </div>
              )}

              <input
                value={imageInput}
                onChange={(event) => {
                  setImageInput(event.target.value);
                  setSelectedImageSources([]);
                }}
                placeholder="https://... or data:image/..."
                className="h-10 w-full rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 font-mono text-xs text-[var(--forma-text-body)] outline-none placeholder:text-[var(--forma-text-muted)] focus:border-[rgb(var(--forma-cyan-rgb))]"
              />
              <div className="mt-2 text-[11px] leading-5 text-[var(--forma-text-secondary)]">
                {selectedImageSources.length
                  ? `${selectedImageSources.length} project image${selectedImageSources.length === 1 ? "" : "s"} selected.`
                  : "No project images selected; the manual image field will be used."}
              </div>
            </div>
          ) : (
            <label className="mt-5 block text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
              Source video
              <select
                value={sourceVideoUrl}
                onChange={(event) => setSourceVideoUrl(event.target.value)}
                disabled={!sourceVideos.length}
                className="mt-2 h-10 w-full rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 text-sm font-normal tracking-normal text-[var(--forma-text-body)] outline-none focus:border-[rgb(var(--forma-cyan-rgb))] disabled:opacity-50"
              >
                {!sourceVideos.length && <option value="">No saved videos</option>}
                {sourceVideos.map((item) => (
                  <option key={item.url} value={item.url}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <VideoGallery
            videos={gallery}
            loading={galleryLoading}
            error={galleryError}
            onRefresh={onRefreshGallery}
            selectedKey={selectedReviewVideoKey}
            onSelect={setSelectedReviewVideoKey}
            onReview={onReviewVideo}
            canReview={canReview}
            canOpenAssets={!readOnly}
            reviewing={isReviewing}
          />
        </section>

        <aside className="min-w-0 rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4 sm:p-5">
          <div className="aspect-video overflow-hidden rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)]">
            {mode === "video-to-video" && sourceVideoPreview ? (
              <video src={sourceVideoPreview} controls preload="metadata" className="h-full w-full object-contain" />
            ) : imagePreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={imagePreview} alt="Video source preview" className="h-full w-full object-contain" />
            ) : (
              <div className="flex h-full items-center justify-center text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
                No source
              </div>
            )}
          </div>
          {mode === "image-to-video" && selectedImageSources.length > 0 && (
            <div className="mt-2 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 py-2 text-[11px] leading-5 text-[var(--forma-text-secondary)]">
              Previewing the first selected image. Generate will queue {selectedImageSources.length} image source{selectedImageSources.length === 1 ? "" : "s"}.
            </div>
          )}

          <div className="mt-4 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Status</span>
              <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${videoStatusTone(status)}`}>
                {status === "failed" ? <AlertTriangle className="h-3.5 w-3.5" /> : status === "succeeded" ? <CheckCircle className="h-3.5 w-3.5" /> : <RefreshCw className={`h-3.5 w-3.5 ${isGenerating ? "animate-spin" : ""}`} />}
                {status}
              </span>
            </div>
            {requestId && <div className="mt-3 truncate font-mono text-[10px] text-[var(--forma-text-muted)]">{requestId}</div>}
            {statusMessage && <p className="mt-3 break-words text-xs leading-5 text-[var(--forma-text-secondary)]">{statusMessage}</p>}
            {modelsError && <p className="mt-3 break-words text-xs leading-5 text-[rgb(var(--forma-yellow-rgb))]">{modelsError}</p>}
          </div>

          <VideoReviewStatus
            status={reviewStatus}
            message={reviewMessage}
            available={reviewAvailable}
            unavailableReason={reviewUnavailableReason}
            isReviewing={isReviewing}
            makeNewVideo={makeNewVideo}
            setMakeNewVideo={setMakeNewVideo}
            canMakeNewVideo={canMakeNewVideo}
          />

          {storedVideo && (
            <div className="mt-4 rounded-lg border border-[rgb(var(--forma-green-rgb)/0.35)] bg-[rgb(var(--forma-green-rgb)/0.1)] p-4">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[rgb(var(--forma-green-rgb))]">
                <CheckCircle className="h-4 w-4" />
                Saved
              </div>
              {savedHref ? (
                <a
                  href={savedHref}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex max-w-full items-center gap-2 rounded-md border border-[rgb(var(--forma-green-rgb)/0.4)] px-3 py-2 text-xs font-medium text-[rgb(var(--forma-green-rgb))] transition-colors hover:border-[rgb(var(--forma-green-rgb)/0.6)]"
                >
                  <ExternalLink className="h-4 w-4 shrink-0" />
                  Open saved video
                </a>
              ) : (
                <div className="mt-3 break-all font-mono text-xs leading-5 text-[var(--forma-text-body)]">{storedVideo.s3Uri || storedVideo.key}</div>
              )}
              {storedVideo.key && <div className="mt-3 break-all font-mono text-[10px] leading-5 text-[var(--forma-text-muted)]">{storedVideo.key}</div>}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export function VideoReviewStatus({
  status,
  message,
  available,
  unavailableReason,
  isReviewing,
  makeNewVideo,
  setMakeNewVideo,
  canMakeNewVideo,
}: {
  status: string;
  message: string | null;
  available: boolean;
  unavailableReason: string | null;
  isReviewing: boolean;
  makeNewVideo: boolean;
  setMakeNewVideo: (value: boolean) => void;
  canMakeNewVideo: boolean;
}) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Review</span>
        <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${videoStatusTone(status)}`}>
          {status === "failed" ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : status === "succeeded" ? (
            <CheckCircle className="h-3.5 w-3.5" />
          ) : isReviewing ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" />
          )}
          {status}
        </span>
      </div>
      <label className={`mt-3 flex min-h-10 items-center gap-3 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 py-2 text-xs font-medium ${
        canMakeNewVideo ? "text-[var(--forma-text-body)]" : "text-[var(--forma-text-muted)]"
      }`}>
        <input
          type="checkbox"
          checked={makeNewVideo}
          onChange={(event) => setMakeNewVideo(event.target.checked)}
          disabled={!canMakeNewVideo || isReviewing}
          className="h-4 w-4 accent-[rgb(var(--forma-cyan-rgb))] disabled:cursor-not-allowed"
        />
        <span>Make new video</span>
      </label>
      {message && <p className="mt-3 break-words text-xs leading-5 text-[var(--forma-text-secondary)]">{message}</p>}
      {!available && unavailableReason && <p className="mt-3 break-words text-xs leading-5 text-[rgb(var(--forma-yellow-rgb))]">{unavailableReason}</p>}
    </div>
  );
}

export function VideoGallery({
  videos,
  loading,
  error,
  onRefresh,
  selectedKey,
  onSelect,
  onReview,
  canReview,
  canOpenAssets,
  reviewing,
}: {
  videos: StoredVideoInfo[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  selectedKey: string | null;
  onSelect: (value: string | null) => void;
  onReview: (video: StoredVideoInfo) => void;
  canReview: boolean;
  canOpenAssets: boolean;
  reviewing: boolean;
}) {
  return (
    <div className="mt-5 rounded-lg border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Film className="h-4 w-4 text-[rgb(var(--forma-cyan-rgb))]" />
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Gallery</div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={!canOpenAssets}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] text-[var(--forma-text-muted)] transition-colors hover:bg-[var(--forma-page)] hover:text-[var(--forma-text-strong)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-[var(--forma-surface)] disabled:hover:text-[var(--forma-text-muted)]"
          title={canOpenAssets ? "Refresh gallery" : "Videos are available only on projects you generated."}
          aria-label="Refresh gallery"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="mb-3 break-words rounded-md border border-[rgb(var(--forma-yellow-rgb)/0.35)] bg-[rgb(var(--forma-yellow-rgb)/0.1)] p-3 text-xs leading-5 text-[rgb(var(--forma-yellow-rgb))]">
          {error}
        </div>
      )}

      {loading && !videos.length ? (
        <div className="rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4 text-xs leading-5 text-[var(--forma-text-secondary)]">
          Loading gallery…
        </div>
      ) : videos.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {videos.map((video, index) => {
            const key = videoIdentity(video, `video-${index}`);
            const reviewable = Boolean(videoSourceUrl(video));
            return (
              <VideoGalleryItem
                key={key}
                video={video}
                identity={key}
                selected={selectedKey === key}
                onSelect={() => onSelect(key)}
                onReview={() => onReview(video)}
                canReview={canReview && reviewable}
                canOpenAssets={canOpenAssets}
                reviewing={reviewable && reviewing && selectedKey === key}
                reviewable={reviewable}
              />
            );
          })}
        </div>
      ) : (
        <div className="rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface)] p-4 text-xs leading-5 text-[var(--forma-text-secondary)]">
          No videos yet.
        </div>
      )}
    </div>
  );
}

export function VideoGalleryItem({
  video,
  identity,
  selected,
  onSelect,
  onReview,
  canReview,
  canOpenAssets,
  reviewing,
  reviewable,
}: {
  video: StoredVideoInfo;
  identity: string;
  selected: boolean;
  onSelect: () => void;
  onReview: () => void;
  canReview: boolean;
  canOpenAssets: boolean;
  reviewing: boolean;
  reviewable: boolean;
}) {
  const playableUrl = canOpenAssets ? videoSourceUrl(video) || null : null;
  const openUrl = canOpenAssets ? playableUrl || null : null;
  const label = videoLabel(video);
  const prompt = videoPromptText(video);

  return (
    <article className={`min-w-0 overflow-hidden rounded-lg border bg-[var(--forma-surface)] transition ${
      selected
        ? "border-[rgb(var(--forma-cyan-rgb)/0.55)]"
        : "border-[var(--forma-border)]"
    }`}>
      <div className="aspect-video bg-[var(--forma-surface-muted)]">
        {playableUrl ? (
          <video src={playableUrl} controls preload="metadata" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
            Video saved
          </div>
        )}
      </div>
      <div className="border-t border-[var(--forma-border)] p-3">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-mono text-[11px] text-[var(--forma-text-secondary)]">{label}</div>
            <div className="mt-1 truncate font-mono text-[10px] text-[var(--forma-text-muted)]">{identity}</div>
          </div>
          <span className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-medium uppercase tracking-[0.12em] ${
            selected
              ? "border-[rgb(var(--forma-cyan-rgb)/0.45)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] text-[rgb(var(--forma-cyan-rgb))]"
              : "border-[var(--forma-border)] text-[var(--forma-text-muted)]"
          }`}>
            {selected ? "Selected" : reviewable ? "Reviewable" : "No URL"}
          </span>
        </div>
        <div className="mt-3 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] p-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Prompt</div>
          <p className="mt-2 max-h-28 overflow-y-auto break-words text-xs leading-5 text-[var(--forma-text-secondary)]">
            {prompt || "No prompt saved for this video."}
          </p>
        </div>
        {video.key && <div className="mt-2 break-all font-mono text-[10px] leading-4 text-[var(--forma-text-muted)]">{video.key}</div>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">{formatBytes(video.sizeBytes || 0)}</span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSelect}
              disabled={!reviewable || !canOpenAssets}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--forma-border)] px-2 text-[10px] font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-surface-muted)] hover:text-[var(--forma-text-strong)] disabled:cursor-not-allowed disabled:opacity-40"
              title={canOpenAssets ? (reviewable ? "Select video for review" : "This saved video needs an HTTP(S) URL before review") : "Videos are available only on projects you generated."}
            >
              {selected ? <CheckCircle className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              Select
            </button>
            <button
              type="button"
              onClick={() => {
                onSelect();
                onReview();
              }}
              disabled={!canReview || reviewing}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[rgb(var(--forma-cyan-rgb)/0.35)] bg-[rgb(var(--forma-cyan-rgb)/0.1)] px-2 text-[10px] font-medium text-[rgb(var(--forma-cyan-rgb))] transition-colors hover:border-[rgb(var(--forma-cyan-rgb)/0.55)] disabled:cursor-not-allowed disabled:opacity-40"
              title={reviewable ? "Review selected video" : "This saved video needs an HTTP(S) URL before review"}
            >
              {reviewing ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              Review
            </button>
            {openUrl ? (
              <a
                href={openUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--forma-border)] px-2 text-[10px] font-medium text-[var(--forma-text-body)] transition-colors hover:bg-[var(--forma-surface-muted)] hover:text-[var(--forma-text-strong)]"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open
              </a>
            ) : (
              <span className="truncate font-mono text-[10px] text-[var(--forma-text-muted)]">{video.s3Uri || "-"}</span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
