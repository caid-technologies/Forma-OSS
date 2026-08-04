function truthy(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value || "").trim().toLowerCase());
}

const development = process.env.NODE_ENV === "development";
const productionApiUrl = "https://forma-api.caid.workers.dev";

export const webConfig = {
  development,
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    (development ? "http://localhost:8000" : productionApiUrl),
  publicDeveloperTools:
    development ||
    truthy(process.env.NEXT_PUBLIC_BLUEPRINT_DEBUG) ||
    truthy(process.env.NEXT_PUBLIC_BLUEPRINT_DEV_MODE),
  serverDeveloperTools:
    development ||
    truthy(process.env.BLUEPRINT_DEBUG) ||
    truthy(process.env.BLUEPRINT_DEV_MODE) ||
    truthy(process.env.NEXT_PUBLIC_BLUEPRINT_DEBUG) ||
    truthy(process.env.NEXT_PUBLIC_BLUEPRINT_DEV_MODE),
  authMode: (process.env.BLUEPRINT_AUTH_MODE || "").trim().toLowerCase(),
} as const;
