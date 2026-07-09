import BlueprintWorkspace from "../../blueprint-workspace";
import { showDeveloperTools } from "../../../lib/server-feature-flags";

type ProjectPageProps = {
  params: {
    projectId: string;
  };
};

export default function ProjectPage({ params }: ProjectPageProps) {
  return <BlueprintWorkspace routeProjectId={params.projectId} showDeveloperTools={showDeveloperTools()} />;
}
