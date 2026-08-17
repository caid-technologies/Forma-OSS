import { webConfig } from "./config";

export type FormaAuthMode = "local" | "clerk";

export function formaAuthMode(): FormaAuthMode {
  const value = webConfig.authMode;
  if (!value) {
    throw new Error('FORMA_AUTH_MODE is required. Expected "local" or "clerk".');
  }
  if (value !== "local" && value !== "clerk") {
    throw new Error(`Invalid FORMA_AUTH_MODE=${JSON.stringify(value)}. Expected "local" or "clerk".`);
  }
  return value;
}

export function clerkAuthRequired() {
  return formaAuthMode() === "clerk";
}
