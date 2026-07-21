import FormaWorkspace from "../blueprint-workspace";
import { deployedAuthRequired } from "../../lib/deployed-auth";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function JobsPage() {
  return <FormaWorkspace authRequired={deployedAuthRequired()} homeView="jobs" showDeveloperTools={showDeveloperTools()} />;
}
