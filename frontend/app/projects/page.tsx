import FormaWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function ProjectsPage() {
  return <FormaWorkspace homeView="projects" showDeveloperTools={showDeveloperTools()} />;
}
