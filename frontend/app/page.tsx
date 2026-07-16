import BlueprintWorkspace from "./blueprint-workspace";
import { deployedAuthRequired } from "../lib/deployed-auth";
import { showDeveloperTools } from "../lib/server-feature-flags";

export default function Home() {
  return <BlueprintWorkspace authRequired={deployedAuthRequired()} showDeveloperTools={showDeveloperTools()} />;
}
