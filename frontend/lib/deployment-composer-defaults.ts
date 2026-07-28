const WEB_RESEARCH_WORKFLOW_ID = "web_research";

type WorkflowOption = {
  id: string;
};

type DeploymentComposerDefaultsInput = {
  blueprintDevMode: unknown;
  imageProviderConfigured: boolean;
  workflows: WorkflowOption[];
};

export function deploymentComposerDefaults({
  blueprintDevMode,
  imageProviderConfigured,
  workflows,
}: DeploymentComposerDefaultsInput) {
  const deploymentDefaultsEnabled = blueprintDevMode === false;

  return {
    generateImages: deploymentDefaultsEnabled && imageProviderConfigured,
    workflowId:
      deploymentDefaultsEnabled && workflows.some((workflow) => workflow.id === WEB_RESEARCH_WORKFLOW_ID)
        ? WEB_RESEARCH_WORKFLOW_ID
        : null,
  };
}
