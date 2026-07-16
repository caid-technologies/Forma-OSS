export function deployedAuthRequired() {
  const explicit = process.env.BLUEPRINT_AUTH_REQUIRED || process.env.NEXT_PUBLIC_BLUEPRINT_AUTH_REQUIRED;
  if (explicit) return ["1", "true", "yes", "on"].includes(explicit.toLowerCase());
  return process.env.VERCEL === "1" || Boolean(process.env.VERCEL_ENV);
}
