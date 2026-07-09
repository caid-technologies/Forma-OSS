import { notFound } from "next/navigation";
import BlueprintWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function BackendLogsPage() {
  if (!showDeveloperTools()) notFound();
  return <BlueprintWorkspace homeView="logs" showDeveloperTools={true} />;
}
