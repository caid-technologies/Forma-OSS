import FormaWorkspace from "../../blueprint-workspace";
import { showDeveloperTools } from "../../../lib/server-feature-flags";

type ProjectPageProps = {
  params: {
    projectId: string;
  };
};

export default function ProjectPage({ params }: ProjectPageProps) {
  return <FormaWorkspace routeProjectId={params.projectId} showDeveloperTools={showDeveloperTools()} />;
}
