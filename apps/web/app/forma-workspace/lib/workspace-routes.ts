import {
  BookOpen,
  CircuitBoard,
  Clapperboard,
  ClipboardList,
  Cuboid,
  LayoutDashboard,
} from "lucide-react";

export const workspaceTabs = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "bom", label: "Bill of Materials", icon: ClipboardList },
  { id: "mechanical", label: "Mechanical", icon: Cuboid },
  { id: "schematic", label: "Electrical", icon: CircuitBoard },
  { id: "assembly", label: "Documentation", icon: BookOpen },
  { id: "video", label: "Media", icon: Clapperboard },
];

export const workspaceTabNamespaces: Record<string, string> = {
  overview: "product.overview",
  bom: "product.bom",
  mechanical: "product.mech",
  schematic: "product.electrical",
  assembly: "project.docs",
  video: "product.visuals.video",
  jobs: "project.history.jobs",
  logs: "project.runtime.logs",
};

export function normalizeTab(tab: string | null) {
  if (!tab) return null;
  const aliases: Record<string, string> = {
    chat: "overview",
    concept: "overview",
    info: "overview",
    image: "overview",
    mech: "mechanical",
    wire: "schematic",
    electrical: "schematic",
    docs: "assembly",
    documentation: "assembly",
    billing: "bom",
    materials: "bom",
    media: "video",
  };
  const normalized = aliases[tab] || tab;
  return workspaceTabs.some((item) => item.id === normalized) ? normalized : null;
}

export function workspaceTabMeta(tab: string | null) {
  const normalized = normalizeTab(tab);
  return workspaceTabs.find((item) => item.id === normalized) || workspaceTabs[0];
}

export function workspaceNamespaceForTab(tab: string | null) {
  const meta = workspaceTabMeta(tab);
  return workspaceTabNamespaces[meta.id] || meta.id;
}

export function projectRoute(projectId: string) {
  return `/project/${encodeURIComponent(projectId)}`;
}

export function chatRoute(chatId: string) {
  return `/chat/${encodeURIComponent(chatId)}`;
}

export function safeDecodeProjectId(projectId: string) {
  try {
    return decodeURIComponent(projectId);
  } catch {
    return projectId;
  }
}

export function safeDecodeChatId(chatId: string) {
  try {
    return decodeURIComponent(chatId);
  } catch {
    return chatId;
  }
}
