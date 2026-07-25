"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  Battery,
  Box,
  CheckCircle,
  ChevronDown,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Eye,
  Info,
  Monitor,
  Printer,
  RefreshCw,
  ShieldCheck,
  Sliders,
  Volume2,
  Wrench,
} from "lucide-react";

import { JobMetric } from "./admin-panels";
import { type ProjectImageCandidate } from "./project-gallery";

const RUNPOD_PARTI_BASE_MODEL = "caid-technologies/parti-base";
const BASETEN_GLM_MODEL = "zai-org/GLM-5.2";

const MechanicalScene = dynamic(() => import("../../components/mechanical-scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-[#0f1014] text-xs font-black uppercase tracking-[0.16em] text-slate-600">
      Loading mechanical preview...
    </div>
  ),
});

const categoryTone: Record<string, { text: string; bg: string; border: string; label: string }> = {
  microcontroller: { text: "text-cyan-400", bg: "bg-cyan-950/40", border: "border-cyan-500/40", label: "MCU" },
  sensor: { text: "text-emerald-400", bg: "bg-emerald-950/30", border: "border-emerald-500/30", label: "SENSOR" },
  actuator: { text: "text-orange-400", bg: "bg-orange-950/35", border: "border-orange-500/40", label: "ACTUATOR" },
  display: { text: "text-pink-400", bg: "bg-pink-950/35", border: "border-pink-500/40", label: "DISPLAY" },
  power: { text: "text-yellow-400", bg: "bg-yellow-950/35", border: "border-yellow-500/40", label: "POWER" },
  passives: { text: "text-violet-400", bg: "bg-violet-950/35", border: "border-violet-500/40", label: "IO" },
  mechanical: { text: "text-rose-400", bg: "bg-rose-950/30", border: "border-rose-500/35", label: "MECH" },
  "3d print": { text: "text-indigo-300", bg: "bg-indigo-950/35", border: "border-indigo-400/35", label: "3D PRINT" },
  default: { text: "text-slate-300", bg: "bg-slate-900", border: "border-slate-700", label: "PART" },
};

function projectLlmDisplayLabel(provider: string, model: string) {
  if (provider === "runpod-serverless" && model === RUNPOD_PARTI_BASE_MODEL) return RUNPOD_PARTI_BASE_MODEL;
  if (provider === "baseten" && model === BASETEN_GLM_MODEL) return "GLM 5.2";
  return `${provider}/${model}`;
}

export function OverviewPanel({
  title,
  description,
  imageCandidates,
  features,
  metrics,
  metadata,
}: {
  title: string;
  description: string;
  imageCandidates: ProjectImageCandidate[];
  features: string[];
  metrics: ReturnType<typeof emptyMetrics>;
  metadata: Record<string, any>;
}) {
  const imageKey = imageCandidates.map((candidate) => candidate.src).join("|");
  const [imageIndex, setImageIndex] = useState(0);

  useEffect(() => {
    setImageIndex(0);
  }, [imageKey]);

  const activeImage = imageCandidates[imageIndex] || null;
  const llmProvider = metadata.runtime_provider || metadata.llm_provider || metadata.requested_provider;
  const llmModel = metadata.runtime_model || metadata.actual_model || metadata.model_name || metadata.requested_model;

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] px-4 py-6 sm:px-5 sm:py-8">
      <div className="mx-auto min-w-0 max-w-[890px]">
        <div className="relative border border-[#2a2c33] bg-[#d5d5d3]">
          {activeImage ? (
            <img
              src={activeImage.src}
              alt={activeImage.label}
              onError={() => setImageIndex((current) => current + 1)}
              className="h-[320px] w-full object-contain sm:h-[440px]"
            />
          ) : (
            <ProductRender product={metadata.product_visual} />
          )}
          <button className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-blue-600 shadow-lg" title={activeImage ? activeImage.label : "Generated visual reference"}>
            <Eye className="h-5 w-5" />
          </button>
          {activeImage && (
            <div className="absolute left-4 top-4 max-w-[calc(100%-6.5rem)] border border-black/10 bg-white/90 px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#202127] shadow-lg">
              {activeImage.label}
            </div>
          )}
        </div>

        {imageCandidates.length > 1 && (
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {imageCandidates.slice(0, 3).map((candidate, index) => (
              <button
                key={`${candidate.src}-${index}`}
                type="button"
                onClick={() => setImageIndex(index)}
                className={`min-w-0 border p-2 text-left transition ${
                  imageIndex === index ? "border-white bg-white text-black" : "border-[#2a2c33] bg-[#17181d] text-slate-400 hover:border-slate-500 hover:text-white"
                }`}
              >
                <img src={candidate.src} alt={candidate.label} className="h-20 w-full bg-black object-cover" />
                <div className="mt-2 truncate text-[10px] font-black uppercase tracking-[0.14em]">{candidate.label}</div>
              </button>
            ))}
          </div>
        )}

        <div className="mt-6 min-w-0 border-t border-[#282a30] px-2 py-6 sm:px-8 sm:py-8">
          <h1 className="break-words text-xl font-black uppercase tracking-[0.12em] text-white sm:text-2xl sm:tracking-[0.18em]">{title}</h1>
          <div className="mt-5 flex flex-wrap gap-2">
            {metadata.workflow && (
              <span className="max-w-full break-words border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-cyan-200 sm:tracking-[0.16em]">
                {metadata.workflow}
              </span>
            )}
            {llmProvider && llmModel && (
              <span className="max-w-full break-words border border-violet-300/30 bg-violet-300/10 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-violet-100 sm:tracking-[0.16em]">
                {projectLlmDisplayLabel(llmProvider, llmModel)}
              </span>
            )}
            {features.slice(0, 12).map((feature, index) => (
              <span key={`${feature}-${index}`} className="max-w-full break-words border border-[#333640] px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.12em] text-slate-400 sm:tracking-[0.16em]">
                {String(feature).split(":")[0]}
              </span>
            ))}
          </div>

          <div className="mt-7">
            <div className="text-[11px] font-black uppercase tracking-[0.22em] text-slate-500">Technical Description</div>
            <p className="mt-4 max-w-3xl break-words text-base leading-8 text-slate-300">{description}</p>
          </div>

          <div className="mt-7 max-w-2xl border border-[#2a2c33]">
            <div className="grid grid-cols-3 border-b border-[#2a2c33] px-4 py-3 text-[12px] font-black uppercase tracking-[0.18em] text-slate-500">
              <span>Category</span>
              <span className="text-center">Parts</span>
              <span className="text-right">Cost</span>
            </div>
            <SummaryRow label="Electrical" parts={metrics.electricalParts} cost={metrics.electricalCost} />
            <SummaryRow label="Mechanical" parts={metrics.mechanicalParts} cost={metrics.mechanicalCost} />
            <SummaryRow label="Total" parts={metrics.totalParts} cost={metrics.totalCost} strong />
          </div>
        </div>
      </div>
    </div>
  );
}

export function BomPanel({
  components,
  metrics,
  cadSources = [],
  fabricationCost = 0,
  canDownloadAssets = false,
}: {
  components: any[];
  metrics: ReturnType<typeof emptyMetrics>;
  cadSources?: any[];
  fabricationCost?: number;
  canDownloadAssets?: boolean;
}) {
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-5">
      <div className="space-y-3 lg:hidden">
        {components.map((component) => {
          const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
          const Icon = iconForCategory(component.category);
          const subtotal = (component.unit_price || 0) * (component.quantity || 1);

          return (
            <article key={component.ref_des} className="border border-[#2a2c33] bg-[#17181d] p-4">
              <div className="flex min-w-0 items-start gap-3">
                <span className={`flex h-11 w-11 shrink-0 items-center justify-center border ${tone.border} ${tone.bg}`}>
                  <Icon className={`h-5 w-5 ${tone.text}`} />
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="break-words text-sm font-black text-white">{component.name}</h3>
                  <p className="mt-2 break-words text-xs leading-5 text-slate-500">{component.rationale}</p>
                  <CategoryBadge category={component.category} />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Qty</div>
                  <div className="mt-1 font-bold text-slate-200">{component.quantity}</div>
                </div>
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2 text-right">
                  <div className="font-black uppercase text-slate-600">Subtotal</div>
                  <div className="mt-1 font-black text-white">~${subtotal.toFixed(2)}</div>
                </div>
                <div className="border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Unit</div>
                  <div className="mt-1 font-bold text-slate-200">~${Number(component.unit_price || 0).toFixed(2)}</div>
                </div>
                <div className="min-w-0 border border-[#25272e] bg-[#141519] px-3 py-2">
                  <div className="font-black uppercase text-slate-600">Source</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {getSourcesForComponent(component).map((source) => (
                      <ComponentSourceAction
                        key={`${source.label}-${source.href}`}
                        source={source}
                        component={component}
                        canDownloadAssets={canDownloadAssets}
                        className="inline-flex justify-center px-2 py-1 text-[10px]"
                      />
                    ))}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto border border-[#2a2c33] lg:block">
        <div className="min-w-[980px]">
          <div className="grid grid-cols-[minmax(420px,1fr)_110px_110px_150px_140px] border-b border-[#f5f5f5] px-5 py-5 text-sm font-black uppercase tracking-widest text-white">
            <span>Part</span>
            <span className="text-center">Qty</span>
            <span>Unit</span>
            <span>Source</span>
            <span className="text-right">Subtotal</span>
          </div>
          <div className="divide-y divide-[#282a30]">
            {components.map((component) => (
              <div key={component.ref_des} className="grid grid-cols-[minmax(420px,1fr)_110px_110px_150px_140px] items-center px-5 py-6">
                <div className="flex items-start gap-4">
                  <PartThumb component={component} />
                  <div className="min-w-0">
                    <h3 className="text-lg font-black text-white">{component.name}</h3>
                    <div className="mt-2 text-sm text-slate-500">{component.category}</div>
                    <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">{component.rationale}</p>
                    <CategoryBadge category={component.category} />
                  </div>
                </div>
                <div className="text-center text-base text-slate-200">{component.quantity}</div>
                <div className="text-base text-slate-200">~${Number(component.unit_price || 0).toFixed(2)}</div>
                <div className="flex flex-col items-start gap-2">
                  {getSourcesForComponent(component).map((source) => (
                    <ComponentSourceAction
                      key={`${source.label}-${source.href}`}
                      source={source}
                      component={component}
                      canDownloadAssets={canDownloadAssets}
                      className="inline-flex min-w-[86px] justify-center px-3 py-2 text-xs"
                    />
                  ))}
                </div>
                <div className="text-right text-lg font-black text-white">~${((component.unit_price || 0) * (component.quantity || 1)).toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-2 border border-[#2a2c33] px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-6">
        <span className="text-sm font-black uppercase tracking-[0.16em] text-slate-400 sm:tracking-[0.22em]">Total Estimated Cost</span>
        <span className="text-2xl font-black text-white sm:text-3xl">~${metrics.totalCost.toFixed(2)}</span>
      </div>

      <div className="mt-5 border border-[#2a2c33] p-4">
        <div className="flex items-start justify-between gap-4 border-b border-[#333640] pb-3">
          <div>
            <h2 className="text-sm font-black uppercase tracking-widest text-white">CAD Sources</h2>
            <div className="mt-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">3D Printed</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Mech Cost</div>
            <div className="mt-1 text-lg font-black text-white">~${fabricationCost.toFixed(2)}</div>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {!canDownloadAssets ? (
            <div className="border border-[#2a2c33] bg-[#141519] p-3 text-xs leading-6 text-slate-500">
              Files are available only on projects you generated.
            </div>
          ) : cadSources.length ? cadSources.slice(0, 3).map((source: any) => (
            <a
              key={`${source.name}-${source.url}`}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="block border border-[#2a2c33] bg-[#141519] p-3 hover:border-cyan-400/60"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-words text-xs font-black uppercase tracking-[0.12em] text-white sm:tracking-[0.14em]">{source.name}</div>
                  <div className="mt-2 break-words text-[10px] font-black uppercase tracking-[0.12em] text-cyan-300 sm:tracking-[0.16em]">{source.source_type || "CAD"} / ${(Number(source.estimated_unit_price_usd || 0)).toFixed(2)}</div>
                </div>
                <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
              </div>
              {source.file_formats?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {source.file_formats.map((format: string) => (
                    <span key={format} className="border border-[#333640] px-2 py-1 text-[10px] font-black uppercase text-slate-500">{format}</span>
                  ))}
                </div>
              )}
            </a>
          )) : (
            <div className="border border-[#2a2c33] bg-[#141519] p-3 text-xs leading-6 text-slate-500">
              No CAD source records attached.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ComponentSourceAction({
  source,
  component,
  canDownloadAssets,
  className = "",
}: {
  source: { label: string; className: string; href: string; title: string };
  component: any;
  canDownloadAssets: boolean;
  className?: string;
}) {
  const isFabricationAsset = source.label.toLowerCase() === "fabricate";
  const baseClass = `${className} font-black italic transition focus:outline-none focus:ring-2 focus:ring-cyan-300`;
  if (isFabricationAsset && !canDownloadAssets) {
    return (
      <span
        title="Files are available only on projects you generated."
        className={`${baseClass} cursor-not-allowed border border-[#2a2c33] bg-[#111216] text-slate-600`}
      >
        {source.label}
      </span>
    );
  }

  return (
    <a
      href={source.href}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open ${source.label} source for ${component.name || component.part_number || "component"}`}
      title={source.title}
      className={`${baseClass} ${source.className} text-black hover:-translate-y-0.5 hover:brightness-110`}
    >
      {source.label}
    </a>
  );
}

export function MechanicalPanel({
  toggles,
  setToggles,
  electricalActive,
  setElectricalActive,
  components,
  features,
  metadata,
  mechanical,
}: {
  toggles: Record<string, boolean>;
  setToggles: (value: any) => void;
  electricalActive: boolean;
  setElectricalActive: (value: boolean) => void;
  components: any[];
  features: string[];
  metadata: Record<string, any>;
  mechanical: Record<string, any>;
}) {
  const visualSpec = metadata.product_visual_spec || {};
  const dimensions = mechanical.render_dimensions || visualSpec.external_dimensions_mm || metadata.render_dimensions || { x_mm: 100, y_mm: 60, z_mm: 36 };
  const placements = mechanical.component_placements || metadata.component_placements || [];
  const relationships = mechanical.spatial_relationships || metadata.spatial_relationships || [];
  const cadSources = Array.isArray(mechanical.cad_sources) ? mechanical.cad_sources : [];
  const fabricationCost = Number(mechanical.fabrication_cost_estimate_usd || 0);

  return (
    <div className="relative h-full overflow-hidden bg-[#141519]">
      <div className="absolute left-6 top-1/2 z-20 w-36 -translate-y-1/2 border border-[#4b4d56] bg-[#17181d]/80 p-4">
        <h2 className="border-b border-slate-400 pb-3 text-sm font-black uppercase tracking-widest text-white">3D CAD</h2>
        <button
          type="button"
          onClick={() => setElectricalActive(!electricalActive)}
          className={`mt-3 flex w-full items-center gap-2 border-b border-slate-500 pb-3 text-left text-xs font-black uppercase ${
            electricalActive ? "text-cyan-400" : "text-slate-700"
          }`}
        >
          <Cpu className="h-3 w-3" />
          Electrical
        </button>
        <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-slate-500">Mechanical</div>
        <div className="mt-2 space-y-2">
          {Object.entries(toggles).map(([key, value]) => (
            <button
              key={key}
              type="button"
              onClick={() => setToggles({ ...toggles, [key]: !value })}
              aria-pressed={value}
              className={`flex items-center gap-2 text-xs font-black uppercase ${
                value ? layerColor(key) : "text-slate-700"
              }`}
            >
              {key === "bodyRotation" ? <RefreshCw className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              {mechanicalToggleLabel(key)}
            </button>
          ))}
        </div>
      </div>

      

      <div className="relative z-10 flex h-full items-center justify-center px-8">
        <div className="relative h-[610px] w-[900px] max-w-full">
          <MechanicalScene
            dimensions={dimensions}
            components={components}
            placements={placements}
            relationships={relationships}
            features={features}
            toggles={toggles}
            electricalActive={electricalActive}
          />
        </div>
      </div>
    </div>
  );
}

export function AssemblyPanel({
  assembly,
  issues,
  onDownloadJSON,
  onDownloadMarkdown,
  canDownloadAssets,
}: {
  assembly: any[];
  issues: any[];
  onDownloadJSON: () => void;
  onDownloadMarkdown: () => void;
  canDownloadAssets: boolean;
}) {
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const exportButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!exportMenuOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!exportMenuRef.current?.contains(event.target as Node)) setExportMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setExportMenuOpen(false);
      exportButtonRef.current?.focus();
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [exportMenuOpen]);

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 border-b border-[#2a2c33] pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-black uppercase tracking-[0.12em] text-white sm:text-xl sm:tracking-[0.18em]">Build Instructions</h2>
          <p className="mt-2 text-xs text-slate-500">Sequential assembly from the generated hardware graph.</p>
        </div>
        <div ref={exportMenuRef} className="relative shrink-0">
          <button
            ref={exportButtonRef}
            type="button"
            onClick={() => setExportMenuOpen((open) => !open)}
            disabled={!canDownloadAssets}
            aria-haspopup="menu"
            aria-expanded={exportMenuOpen}
            aria-controls="docs-export-menu"
            title={canDownloadAssets ? "Choose an export format" : "Files are available only on projects you generated."}
            className="flex items-center justify-center gap-2 border border-[#2a2c33] px-4 py-3 text-xs font-black uppercase tracking-widest text-white hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-white"
          >
            <Download className="h-4 w-4" />
            Export
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${exportMenuOpen ? "rotate-180" : ""}`} />
          </button>

          {exportMenuOpen && (
            <div
              id="docs-export-menu"
              role="menu"
              className="absolute right-0 top-full z-30 mt-2 w-64 border border-[#34363f] bg-[#17181d] p-1 shadow-2xl"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setExportMenuOpen(false);
                  onDownloadJSON();
                }}
                className="group block w-full px-3 py-3 text-left hover:bg-white hover:text-black"
              >
                <span className="block text-xs font-black uppercase tracking-widest">Project JSON</span>
                <span className="mt-1 block text-[10px] font-medium normal-case tracking-normal text-slate-500 group-hover:text-black">Full project data (.json)</span>
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setExportMenuOpen(false);
                  onDownloadMarkdown();
                }}
                className="group block w-full border-t border-[#2a2c33] px-3 py-3 text-left hover:bg-white hover:text-black"
              >
                <span className="block text-xs font-black uppercase tracking-widest">Markdown</span>
                <span className="mt-1 block text-[10px] font-medium normal-case tracking-normal text-slate-500 group-hover:text-black">Build instructions and safety audit (.md)</span>
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          {assembly.map((step) => (
            <section key={step.step_num} className="border border-[#2a2c33] bg-[#17181d] p-5">
              <div className="flex gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center bg-white text-sm font-black text-black">
                  {step.step_num}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-black text-white">{step.title}</h3>
                  <p className="mt-3 break-words text-sm leading-7 text-slate-400">{step.description}</p>
                  {step.danger_flag && (
                    <div className="mt-4 flex gap-2 border border-rose-500/30 bg-rose-950/25 p-3 text-sm leading-6 text-rose-300">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="min-w-0 break-words">{step.danger_message || "Pay close attention to safety constraints during this stage."}</span>
                    </div>
                  )}
                  {step.affected_components?.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {step.affected_components.map((part: string) => (
                        <span key={part} className="border border-[#2a2c33] px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                          {part}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </section>
          ))}
        </div>

        <div className="min-w-0 border border-[#2a2c33] bg-[#17181d] p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-black uppercase tracking-widest text-white">Safety Audit</h3>
          </div>
          {issues.length ? (
            <div className="space-y-3">
              {issues.map((issue, index) => (
                <div key={`${issue.description}-${index}`} className="border border-[#2a2c33] bg-[#141519] p-3">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">{issue.severity} / {issue.category}</div>
                  <p className="mt-2 break-words text-xs leading-6 text-slate-400">{issue.description}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="border border-emerald-500/30 bg-emerald-950/25 p-4 text-xs leading-6 text-emerald-300">
              All electrical nets validated safely.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ChatNamespaceSummaryPanel({
  projectId,
  title,
  description,
  namespace,
  totalGenerationTime,
  components,
  metrics,
  issues,
}: {
  projectId: string | null;
  title: string;
  description: string;
  namespace: string;
  totalGenerationTime: string;
  components: any[];
  metrics: ReturnType<typeof emptyMetrics>;
  issues: any[];
}) {
  const topComponents = components.slice(0, 8);
  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#141519] p-4 sm:p-6">
      <section className="border border-[#2a2c33] bg-[#17181d] p-4 sm:p-5">
        <div className="flex flex-col gap-3 border-b border-[#2a2c33] pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-cyan-300" />
              <h2 className="truncate text-sm font-black uppercase tracking-[0.16em] text-white">Info</h2>
            </div>
            <p className="mt-2 break-words text-sm leading-6 text-slate-400">{description}</p>
          </div>
          <div className="shrink-0 border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 font-mono text-[11px] text-cyan-100">
            {namespace}
          </div>
        </div>

        <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-2 xl:grid-cols-5">
          <JobMetric label="Project" value={projectId || "-"} />
          <JobMetric label="Title" value={title} />
          <JobMetric label="Parts" value={metrics.totalParts} />
          <JobMetric label="Total Generation Time" value={totalGenerationTime} />
          <JobMetric label="Validation" value={issues.length ? `${issues.length} issues` : "approved"} />
        </div>

        <div className="mt-5 border border-[#2a2c33] bg-[#141519] p-4">
          <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Project Components</div>
          {topComponents.length ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {topComponents.map((component, index) => {
                const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
                const Icon = iconForCategory(component.category);
                return (
                  <div key={`${component.ref_des || component.name}-${index}`} className="flex min-w-0 items-center gap-2 border border-[#25272e] bg-black/20 px-3 py-2">
                    <Icon className={`h-4 w-4 shrink-0 ${tone.text}`} />
                    <span className="truncate text-xs font-bold text-slate-300">{component.ref_des ? `${component.ref_des} ` : ""}{component.name || component.part_number || "Component"}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="mt-3 border border-[#25272e] bg-black/20 p-3 text-xs leading-5 text-slate-500">
              No components attached to this project yet.
            </div>
          )}
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Electrical</div>
            <div className="mt-2 text-xl font-black text-white">{metrics.electricalParts}</div>
            <div className="mt-1 text-xs text-slate-500">~${metrics.electricalCost.toFixed(2)}</div>
          </div>
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Mechanical</div>
            <div className="mt-2 text-xl font-black text-white">{metrics.mechanicalParts}</div>
            <div className="mt-1 text-xs text-slate-500">~${metrics.mechanicalCost.toFixed(2)}</div>
          </div>
          <div className="border border-[#2a2c33] bg-[#141519] p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">Total Cost</div>
            <div className="mt-2 text-xl font-black text-white">~${metrics.totalCost.toFixed(2)}</div>
            <div className="mt-1 text-xs text-slate-500">{metrics.totalParts} parts</div>
          </div>
        </div>
      </section>
    </div>
  );
}

export function PartsSidebar({ components, issues, isValid }: { components: any[]; issues: any[]; isValid: boolean }) {
  return (
    <aside className="hidden min-h-0 border-l border-[#282a30] bg-[#17181d] xl:flex xl:flex-col">
      <div className="border-b border-[#282a30] p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Box className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-black uppercase tracking-[0.2em] text-slate-400">Parts List</h2>
          </div>
          <span className="border border-[#30323a] px-2 py-1 text-[10px] text-slate-500">{components.length}</span>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-4 py-4">
        {components.map((component, index) => {
          const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
          const Icon = iconForCategory(component.category);
          return (
            <div key={`${component.ref_des}-${index}`} className="flex min-w-0 items-center gap-3 py-1.5">
              <Icon className={`h-4 w-4 shrink-0 ${tone.text}`} />
              <span className="truncate text-sm font-bold text-slate-300">{component.name}</span>
            </div>
          );
        })}
      </div>
      <div className="border-t border-[#282a30] p-4">
        <div className={`flex items-center gap-2 border p-3 text-xs font-black uppercase tracking-widest ${
          isValid ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300" : "border-rose-500/30 bg-rose-950/20 text-rose-300"
        }`}>
          {isValid ? <CheckCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          {isValid ? "Circuit Approved" : `${issues.length} Issues`}
        </div>
      </div>
    </aside>
  );
}

export function ProductRender({ product }: { product?: string }) {
  return (
    <div className="relative flex h-[440px] items-center justify-center overflow-hidden bg-[#d5d5d3]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_45%_38%,rgba(255,255,255,0.88),rgba(210,210,208,0.35)_48%,rgba(185,185,182,0.55))]" />
      <div className="relative h-64 w-[470px] rotate-[-16deg] skew-x-[-8deg] rounded-[34px] border border-black/20 bg-gradient-to-br from-[#6b6b68] via-[#3f403d] to-[#222321] shadow-2xl">
        <div className="absolute left-9 top-8 h-48 w-[400px] rounded-[28px] border border-white/10 bg-gradient-to-br from-[#888884] via-[#4f504d] to-[#262725]" />
        <div className="absolute right-14 top-10 h-28 w-44 rounded-xl border border-black/40 bg-[#0c0d10] shadow-inner">
          <div className="absolute left-5 top-10 h-px w-32 bg-cyan-300/70 shadow-[12px_-10px_0_rgba(103,232,249,0.45),30px_12px_0_rgba(103,232,249,0.6),58px_-2px_0_rgba(103,232,249,0.5)]" />
          <div className="absolute bottom-4 left-6 flex gap-5 text-white/60">
            <span className="h-3 w-3 border-l-4 border-y-4 border-y-transparent" />
            <span className="h-3 w-3 border-l-4 border-y-4 border-y-transparent" />
            <span className="h-3 w-3 bg-white/60" />
          </div>
        </div>
        <div className="absolute left-28 top-28 h-28 w-28 rounded-full border-[10px] border-[#222] bg-[#565653] shadow-inner">
          <div className="absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/40 bg-[#8a8a84]" />
          <div className="absolute left-[42px] top-[38px] h-0 w-0 border-y-[12px] border-l-[18px] border-y-transparent border-l-[#4a4a48]" />
        </div>
        <span className="absolute left-20 top-24 h-9 w-9 rounded-full border border-black/40 bg-[#777771]" />
        <span className="absolute left-[104px] top-42 h-8 w-8 rounded-full border border-black/40 bg-[#777771]" />
        <span className="absolute right-5 top-32 h-12 w-3 rounded bg-black/50" />
      </div>
      <div className="absolute bottom-6 right-8 text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">
        {product === "pocket_mp3_player" ? "Rendered from extracted MP3 player features" : "Generated visual reference"}
      </div>
    </div>
  );
}

export function SummaryRow({ label, parts, cost, strong = false }: { label: string; parts: number; cost: number; strong?: boolean }) {
  return (
    <div className={`grid grid-cols-3 border-b border-[#2a2c33] px-4 py-3 text-base last:border-b-0 ${strong ? "font-black text-white" : "text-slate-300"}`}>
      <span>{label}</span>
      <span className="text-center">{parts}</span>
      <span className="text-right">${cost.toFixed(2)}</span>
    </div>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  const tone = categoryTone[category?.toLowerCase()] || categoryTone.default;
  const Icon = iconForCategory(category);
  return (
    <span className={`mt-4 inline-flex items-center gap-1.5 border ${tone.border} ${tone.bg} px-3 py-2 text-[10px] font-black uppercase tracking-widest ${tone.text}`}>
      <Icon className="h-3 w-3" />
      {tone.label}
    </span>
  );
}

export function PartThumb({ component }: { component: any }) {
  const tone = categoryTone[component.category?.toLowerCase()] || categoryTone.default;
  const Icon = iconForCategory(component.category);
  return (
    <div className="flex h-[104px] w-[104px] shrink-0 items-center justify-center bg-white">
      <div className={`flex h-16 w-16 items-center justify-center border ${tone.border} ${tone.bg}`}>
        <Icon className={`h-9 w-9 ${tone.text}`} />
      </div>
    </div>
  );
}

function getSourcesForComponent(component: any): Array<{ label: string; className: string; href: string; title: string }> {
  const category = component.category?.toLowerCase();
  const withHref = (source: { label: string; className: string }) => ({
    ...source,
    href: sourceHrefForComponent(component, source.label),
    title: sourceTitleForComponent(component, source.label),
  });

  if (category === "actuator") {
    return [
      { label: "AliExpress", className: "bg-orange-600" },
      { label: "Amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
      { label: "Newegg", className: "bg-orange-500" },
    ].map(withHref);
  }
  if (category === "power" && component.name?.toLowerCase().includes("charger")) {
    return [
      { label: "Amazon", className: "bg-amber-400" },
      { label: "eBay", className: "bg-blue-600 text-white" },
      { label: "Newegg", className: "bg-orange-500" },
    ].map(withHref);
  }
  if (category === "mechanical" || category === "3d print") {
    return [
      { label: "fabricate", className: "bg-blue-600 text-white" },
    ].map(withHref);
  }
  return [
    { label: "eBay", className: "bg-blue-600 text-white" },
    { label: "Amazon", className: "bg-amber-400" },
    { label: "Newegg", className: "bg-orange-500" },
  ].map(withHref);
}

function componentSearchText(component: any) {
  const values = [component.part_number, component.name, component.category].filter(Boolean);
  return values.join(" ").trim() || "electronic component";
}

function sourceHrefForComponent(component: any, label: string) {
  const normalizedLabel = label.toLowerCase();
  const query = encodeURIComponent(componentSearchText(component));

  if (normalizedLabel === "aliexpress") return `https://www.aliexpress.com/wholesale?SearchText=${query}`;
  if (normalizedLabel === "amazon") return `https://www.amazon.com/s?k=${query}`;
  if (normalizedLabel === "ebay") return `https://www.ebay.com/sch/i.html?_nkw=${query}`;
  if (normalizedLabel === "newegg") return `https://www.newegg.com/p/pl?d=${query}`;
  if (normalizedLabel === "fabricate") {
    const explicitUrl = firstComponentSourceUrl(component);
    return explicitUrl || `https://www.printables.com/search/models?q=${query}`;
  }

  return firstComponentSourceUrl(component) || `https://www.google.com/search?q=${query}`;
}

function sourceTitleForComponent(component: any, label: string) {
  const part = component.part_number || component.name || "component";
  if (label.toLowerCase() === "fabricate") return `Find fabrication/CAD sources for ${part}`;
  return `Search ${label} for ${part}`;
}

function firstComponentSourceUrl(component: any) {
  const candidates = [
    component.sourcing_url,
    component.source_url,
    component.supplier_url,
    component.vendor_url,
    component.purchase_url,
    component.url,
  ];
  const match = candidates.find((candidate) => typeof candidate === "string" && /^https?:\/\//i.test(candidate));
  return match || "";
}

function iconForCategory(category = "") {
  const cat = category.toLowerCase();
  if (cat === "microcontroller") return Cpu;
  if (cat === "sensor") return Database;
  if (cat === "power") return Battery;
  if (cat === "display") return Monitor;
  if (cat === "actuator") return Volume2;
  if (cat === "passives") return Sliders;
  if (cat === "mechanical") return Wrench;
  if (cat === "3d print") return Printer;
  return Box;
}

export function MechanicalLabel({ label, index }: { label: string; index: number }) {
  const positions = [
    "left-[36%] top-[19%]",
    "left-[56%] top-[27%]",
    "left-[51%] top-[31%]",
    "left-[42%] top-[48%]",
    "left-[34%] top-[52%]",
    "left-[46%] top-[58%]",
    "left-[48%] top-[63%]",
    "left-[45%] top-[74%]",
    "left-[27%] top-[82%]",
    "left-[24%] top-[86%]",
  ];
  const sizes = index === 4 ? "text-lg" : index > 7 ? "text-sm" : "text-xs";
  return (
    <div className={`absolute ${positions[index]} ${sizes} bg-black/88 px-3 py-1 font-black uppercase tracking-[0.12em] text-violet-300 shadow-lg`}>
      <span className="absolute -left-1 top-0 h-full w-px bg-violet-300" />
      <span>{label}</span>
      <span className="absolute left-1/2 top-full h-40 w-px bg-violet-200/25" />
    </div>
  );
}

function layerColor(key: string) {
  if (key === "structural") return "text-cyan-400";
  if (key === "enclosure") return "text-emerald-400";
  if (key === "mechanism") return "text-amber-400";
  if (key === "print") return "text-violet-300";
  if (key === "bodyRotation") return "text-rose-300";
  return "text-slate-400";
}

function mechanicalToggleLabel(key: string) {
  if (key === "print") return "3D Print";
  if (key === "bodyRotation") return "Body Rotate";
  return key;
}

function emptyMetrics() {
  return { electricalParts: 0, mechanicalParts: 0, totalParts: 0, electricalCost: 0, mechanicalCost: 0, totalCost: 0 };
}

