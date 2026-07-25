import FormaWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function JobsPage() {
  return <FormaWorkspace homeView="jobs" showDeveloperTools={showDeveloperTools()} />;
}
