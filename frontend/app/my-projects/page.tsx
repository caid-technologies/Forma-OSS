import FormaWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function MyProjectsPage() {
  return <FormaWorkspace homeView="my-projects" showDeveloperTools={showDeveloperTools()} />;
}
