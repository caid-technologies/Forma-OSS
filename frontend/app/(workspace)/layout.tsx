import { showDeveloperTools } from "../../lib/server-feature-flags";
import WorkspaceRouteShell from "./workspace-route-shell";

export default function WorkspaceLayout() {
  return <WorkspaceRouteShell showDeveloperTools={showDeveloperTools()} />;
}
