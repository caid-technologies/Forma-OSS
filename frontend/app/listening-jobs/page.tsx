import { notFound } from "next/navigation";
import { showDeveloperTools } from "../../lib/server-feature-flags";
import ListeningJobsPage from "./listening-jobs-page";

export default function ListeningJobsRoute() {
  if (!showDeveloperTools()) notFound();
  return <ListeningJobsPage />;
}
