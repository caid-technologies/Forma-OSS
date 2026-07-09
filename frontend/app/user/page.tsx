import { notFound } from "next/navigation";
import { showDeveloperTools } from "../../lib/server-feature-flags";
import UserIntegrationsPage from "./user-integrations-page";

export default function UserPage() {
  if (!showDeveloperTools()) notFound();
  return <UserIntegrationsPage />;
}
