import type { ReactNode } from "react";

import { WorkspaceStatusCorner } from "./sidebar";
import type { WorkspaceStatusPresentation } from "../../lib/connection-status";

type WorkspaceFrameProps = {
  collapsed: boolean;
  mobileSidebar: ReactNode;
  desktopSidebar: ReactNode;
  children: ReactNode;
  homeMobileTopPadding?: boolean;
  workspaceStatus: WorkspaceStatusPresentation;
};

export default function WorkspaceFrame({
  collapsed,
  mobileSidebar,
  desktopSidebar,
  children,
  homeMobileTopPadding = false,
  workspaceStatus,
}: WorkspaceFrameProps) {
  return (
    <div
      className={
        homeMobileTopPadding
          ? "relative h-[100dvh] w-full overflow-hidden bg-[#0f1117] font-sans text-zinc-100"
          : "relative h-[100dvh] w-full overflow-hidden bg-[#0f1117] font-sans text-zinc-200"
      }
    >
      {mobileSidebar}
      <WorkspaceStatusCorner status={workspaceStatus} />
      <div
        className={`grid h-full min-h-0 min-w-0 overflow-hidden ${
          collapsed ? "md:grid-cols-[72px_minmax(0,1fr)]" : "md:grid-cols-[260px_minmax(0,1fr)]"
        }`}
      >
        {desktopSidebar}
        <div
          className={
            homeMobileTopPadding
              ? "flex h-full min-h-0 min-w-0 flex-col overflow-hidden pt-12 md:pt-0"
              : "grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden"
          }
        >
          {children}
        </div>
      </div>
    </div>
  );
}
