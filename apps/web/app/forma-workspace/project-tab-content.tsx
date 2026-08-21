"use client";

import { memo, type ReactNode } from "react";

import { JobsPanel, LogsPanel } from "./admin-panels";
import {
  AssemblyPanel,
  BomPanel,
  MechanicalPanel,
  OverviewPanel,
} from "./project-detail-panels";
import { JOB_POLL_INTERVAL_MS, LOG_POLL_INTERVAL_MS, generationLlmLabel } from "./workspace-constants";

type ProjectTabContentProps = {
  tabId: string;
  title: string;
  description: string;
  imageCandidates: unknown[];
  features: unknown[];
  metrics: unknown;
  metadata: Record<string, unknown>;
  systemArchitecture: unknown;
  showModelName: boolean;
  showImageSection: boolean;
  components: unknown[];
  bomComponents: unknown[];
  cadSources: unknown[];
  fabricationCost: number;
  canDownloadAssets: boolean;
  mechToggles: unknown;
  setMechToggles: (value: any) => void;
  mechElectricalActive: boolean;
  setMechElectricalActive: (value: boolean) => void;
  mechanical: unknown;
  schematic: ReactNode;
  assembly: unknown;
  issues: unknown[];
  onDownloadJSON: () => void;
  onDownloadMarkdown: () => void;
  videoContent: ReactNode;
  jobs: unknown[];
  jobsLoading: boolean;
  jobsError: string | null;
  jobStatusFilter: string;
  onStatusFilterChange: (value: string) => void;
  onRefreshJobs: () => void;
  onOpenProject: (job: any) => void;
  findProjectForJob: (job: any) => unknown;
  jobsLastUpdatedAt: string | null;
  logs: unknown;
  logsLoading: boolean;
  logsError: string | null;
  onRefreshLogs: () => void;
  logsLastUpdatedAt: string | null;
  canViewAdminTools?: boolean;
};

function ProjectTabContentView({
  tabId,
  title,
  description,
  imageCandidates,
  features,
  metrics,
  metadata,
  systemArchitecture,
  showModelName,
  showImageSection,
  components,
  bomComponents,
  cadSources,
  fabricationCost,
  canDownloadAssets,
  mechToggles,
  setMechToggles,
  mechElectricalActive,
  setMechElectricalActive,
  mechanical,
  schematic,
  assembly,
  issues,
  onDownloadJSON,
  onDownloadMarkdown,
  videoContent,
  jobs,
  jobsLoading,
  jobsError,
  jobStatusFilter,
  onStatusFilterChange,
  onRefreshJobs,
  onOpenProject,
  findProjectForJob,
  jobsLastUpdatedAt,
  logs,
  logsLoading,
  logsError,
  onRefreshLogs,
  logsLastUpdatedAt,
  canViewAdminTools = false,
}: ProjectTabContentProps) {
  switch (tabId) {
    case "overview":
      return (
        <OverviewPanel
          title={title}
          description={description}
          imageCandidates={imageCandidates as any}
          features={features as any}
          metrics={metrics as any}
          metadata={metadata}
          systemArchitecture={systemArchitecture as any}
          showModelName={showModelName}
          showImageSection={showImageSection}
        />
      );
    case "bom":
      return (
        <BomPanel
          components={bomComponents as any}
          metrics={metrics as any}
          cadSources={cadSources as any}
          fabricationCost={fabricationCost}
          canDownloadAssets={canDownloadAssets}
        />
      );
    case "mechanical":
      return (
        <MechanicalPanel
          toggles={mechToggles as any}
          setToggles={setMechToggles}
          electricalActive={mechElectricalActive}
          setElectricalActive={setMechElectricalActive}
          components={components as any}
          features={features as any}
          metadata={metadata}
          mechanical={mechanical as any}
        />
      );
    case "schematic":
      return schematic;
    case "assembly":
      return (
        <AssemblyPanel
          assembly={assembly as any}
          issues={issues as any}
          onDownloadJSON={onDownloadJSON}
          onDownloadMarkdown={onDownloadMarkdown}
          canDownloadAssets={canDownloadAssets}
        />
      );
    case "video":
      return videoContent;
    case "jobs":
      return (
        <JobsPanel
          jobs={jobs as any}
          loading={jobsLoading}
          error={jobsError}
          statusFilter={jobStatusFilter}
          onStatusFilterChange={onStatusFilterChange}
          onRefresh={onRefreshJobs}
          onOpenProject={onOpenProject as any}
          findProjectForJob={findProjectForJob as any}
          lastUpdatedAt={jobsLastUpdatedAt}
          pollIntervalMs={JOB_POLL_INTERVAL_MS}
          title="Project Jobs"
          description="Only jobs tied to this project are shown here."
          emptyMessage="No jobs recorded for this project and filter."
          formatLlmLabel={generationLlmLabel}
        />
      );
    case "logs":
      return canViewAdminTools ? (
        <LogsPanel
          logs={logs as any}
          loading={logsLoading}
          error={logsError}
          onRefresh={onRefreshLogs}
          lastUpdatedAt={logsLastUpdatedAt}
          pollIntervalMs={LOG_POLL_INTERVAL_MS}
        />
      ) : null;
    default:
      return null;
  }
}

export const ProjectTabContent = memo(ProjectTabContentView);
