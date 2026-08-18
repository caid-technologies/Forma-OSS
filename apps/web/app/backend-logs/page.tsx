import { notFound } from "next/navigation";
import FormaWorkspace from "../blueprint-workspace";
import { showDeveloperTools } from "../../lib/server-feature-flags";

export default function BackendLogsPage() {
  if (!showDeveloperTools()) notFound();
  return <FormaWorkspace homeView="logs" showDeveloperTools={true} />;
}
