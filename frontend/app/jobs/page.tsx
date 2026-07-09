import BlueprintWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function JobsPage() {
  return <BlueprintWorkspace homeView="jobs" showDeveloperTools={showDeveloperTools()} />;
}
