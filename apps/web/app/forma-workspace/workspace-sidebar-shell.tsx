"use client";

import type { ReactNode } from "react";

import type { WorkspaceStatusPresentation } from "../../lib/connection-status";
import { ChatSidebar, MobileSidebarDrawer, type ChatListItem } from "./sidebar";
import WorkspaceFrame from "./workspace-frame";

export type WorkspaceSidebarShellProps = {
  collapsed: boolean;
  mobileSidebarOpen: boolean;
  onMobileSidebarClose: () => void;
  onToggleCollapsed: () => void;
  onHome: () => void;
  chats: ChatListItem[];
  activeChatId: string | null;
  onNewChat: () => void;
  newChatDisabled: boolean;
  onOpenChat: (item: ChatListItem) => void;
  onRenameChat?: (item: ChatListItem, title: string) => void;
  onPinChat?: (item: ChatListItem) => void;
  onDeleteChat?: (item: ChatListItem) => void;
  waitingChatIds: Set<string>;
  chatsLoading?: boolean;
  showJobs: boolean;
  jobsPending?: boolean;
  showDeveloperTools: boolean;
  authRequired: boolean;
  workspaceStatus: WorkspaceStatusPresentation;
  homeMobileTopPadding?: boolean;
  children: ReactNode;
};

export function WorkspaceSidebarShell({
  collapsed,
  mobileSidebarOpen,
  onMobileSidebarClose,
  onToggleCollapsed,
  onHome,
  chats,
  activeChatId,
  onNewChat,
  newChatDisabled,
  onOpenChat,
  onRenameChat,
  onPinChat,
  onDeleteChat,
  waitingChatIds,
  chatsLoading,
  showJobs,
  jobsPending,
  showDeveloperTools,
  authRequired,
  workspaceStatus,
  homeMobileTopPadding = false,
  children,
}: WorkspaceSidebarShellProps) {
  const shared = {
    collapsed,
    onToggle: onToggleCollapsed,
    onHome,
    chats,
    activeChatId,
    onNewChat,
    newChatDisabled,
    onOpenChat,
    onRenameChat,
    onPinChat,
    onDeleteChat,
    waitingChatIds,
    chatsLoading,
    showJobs,
    jobsPending,
    showDeveloperTools,
    authRequired,
  };

  return (
    <WorkspaceFrame
      collapsed={collapsed}
      workspaceStatus={workspaceStatus}
      homeMobileTopPadding={homeMobileTopPadding}
      mobileSidebar={(
        <MobileSidebarDrawer
          open={mobileSidebarOpen}
          onClose={onMobileSidebarClose}
          {...shared}
        />
      )}
      desktopSidebar={<ChatSidebar {...shared} />}
    >
      {children}
    </WorkspaceFrame>
  );
}
