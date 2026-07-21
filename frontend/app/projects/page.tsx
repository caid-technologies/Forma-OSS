import FormaWorkspace from "../blueprint-workspace";
import { deployedAuthRequired } from "../../lib/deployed-auth";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function ProjectsPage() {
  return <FormaWorkspace authRequired={deployedAuthRequired()} homeView="projects" showDeveloperTools={showDeveloperTools()} />;
}
