import FormaWorkspace from "../../blueprint-workspace";
import { deployedAuthRequired } from "../../../lib/deployed-auth";
import { showDeveloperTools } from "../../../lib/server-feature-flags";

type ProjectPageProps = {
  params: {
    projectId: string;
  };
};

export default function ProjectPage({ params }: ProjectPageProps) {
  return <FormaWorkspace authRequired={deployedAuthRequired()} routeProjectId={params.projectId} showDeveloperTools={showDeveloperTools()} />;
}
