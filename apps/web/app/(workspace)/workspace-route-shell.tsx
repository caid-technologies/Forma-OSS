"use client";

import { usePathname } from "next/navigation";
import FormaWorkspace from "../forma-workspace";

type WorkspaceRouteShellProps = {
  showDeveloperTools: boolean;
};

type WorkspaceHomeView = "chat" | "projects" | "my-projects" | "jobs" | "settings" | "about";

function dynamicSegment(pathname: string, prefix: string): string | null {
  if (!pathname.startsWith(prefix)) return null;
  return pathname.slice(prefix.length).split("/", 1)[0] || null;
}

export default function WorkspaceRouteShell({ showDeveloperTools }: WorkspaceRouteShellProps) {
  const pathname = usePathname() || "/";
  const routeChatId = dynamicSegment(pathname, "/chat/");
  const routeProjectId = dynamicSegment(pathname, "/project/");
  let homeView: WorkspaceHomeView = "chat";

  if (pathname === "/projects" || pathname.startsWith("/projects/")) {
    homeView = "projects";
  } else if (pathname === "/my-projects" || pathname.startsWith("/my-projects/")) {
    homeView = "my-projects";
  } else if (pathname === "/jobs" || pathname.startsWith("/jobs/")) {
    homeView = "jobs";
  } else if (pathname === "/settings" || pathname.startsWith("/settings/")) {
    homeView = "settings";
  } else if (pathname === "/about" || pathname.startsWith("/about/")) {
    homeView = "about";
  }

  return (
    <FormaWorkspace
      routeChatId={routeChatId}
      routeProjectId={routeProjectId}
      homeView={homeView}
      showDeveloperTools={showDeveloperTools}
    />
  );
}
