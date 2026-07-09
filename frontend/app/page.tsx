import BlueprintWorkspace from "./blueprint-workspace";
import { showDeveloperTools } from "../lib/server-feature-flags";

export default function Home() {
  return <BlueprintWorkspace showDeveloperTools={showDeveloperTools()} />;
}
