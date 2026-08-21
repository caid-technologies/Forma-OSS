import { webConfig } from "../../lib/config";

export function normalizeApiUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

export const API_URL = normalizeApiUrl(webConfig.apiBaseUrl);
export const DEFAULT_SHOW_DEVELOPER_TOOLS = webConfig.publicDeveloperTools;

export function downloadBrowserFile(contents: string, filename: string, mimeType: string) {
  const blob = new Blob([contents], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
