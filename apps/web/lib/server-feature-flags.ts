function isTruthyEnv(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value || "").trim().toLowerCase());
}

export function showDeveloperTools() {
  return (
    process.env.NODE_ENV === "development" ||
    isTruthyEnv(process.env.BLUEPRINT_DEBUG) ||
    isTruthyEnv(process.env.BLUEPRINT_DEV_MODE) ||
    isTruthyEnv(process.env.NEXT_PUBLIC_BLUEPRINT_DEBUG) ||
    isTruthyEnv(process.env.NEXT_PUBLIC_BLUEPRINT_DEV_MODE)
  );
}
