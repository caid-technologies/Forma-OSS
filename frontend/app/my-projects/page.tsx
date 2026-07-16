import BlueprintWorkspace from "../blueprint-workspace";
import { deployedAuthRequired } from "../../lib/deployed-auth";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function MyProjectsPage() {
  return <BlueprintWorkspace authRequired={deployedAuthRequired()} homeView="my-projects" showDeveloperTools={showDeveloperTools()} />;
}
