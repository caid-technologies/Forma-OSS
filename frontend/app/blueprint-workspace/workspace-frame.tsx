import type { ReactNode } from "react";

type WorkspaceFrameProps = {
  collapsed: boolean;
  mobileSidebar: ReactNode;
  desktopSidebar: ReactNode;
  children: ReactNode;
  homeMobileTopPadding?: boolean;
};

export default function WorkspaceFrame({
  collapsed,
  mobileSidebar,
  desktopSidebar,
  children,
  homeMobileTopPadding = false,
}: WorkspaceFrameProps) {
  return (
    <div
      className={
        homeMobileTopPadding
          ? "h-[100dvh] w-full overflow-hidden bg-[#141519] text-slate-100"
          : "h-[100dvh] w-full overflow-hidden bg-[#141519] text-slate-200"
      }
    >
      {mobileSidebar}
      <div
        className={`grid h-full min-h-0 min-w-0 overflow-hidden ${
          collapsed ? "md:grid-cols-[72px_minmax(0,1fr)]" : "md:grid-cols-[320px_minmax(0,1fr)]"
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
