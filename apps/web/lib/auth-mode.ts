export type BlueprintAuthMode = "local" | "clerk";

export function blueprintAuthMode(): BlueprintAuthMode {
  const value = (process.env.BLUEPRINT_AUTH_MODE || "").trim().toLowerCase();
  if (!value) {
    throw new Error('BLUEPRINT_AUTH_MODE is required. Expected "local" or "clerk".');
  }
  if (value !== "local" && value !== "clerk") {
    throw new Error(`Invalid BLUEPRINT_AUTH_MODE=${JSON.stringify(value)}. Expected "local" or "clerk".`);
  }
  return value;
}

export function clerkAuthRequired() {
  return blueprintAuthMode() === "clerk";
}
