import BlueprintWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function ProjectsPage() {
  return <BlueprintWorkspace homeView="projects" showDeveloperTools={showDeveloperTools()} />;
}
