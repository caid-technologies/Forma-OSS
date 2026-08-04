import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const allowedNames = new Set([
  "BLUEPRINT_ADMIN_USER_IDS",
  "BLUEPRINT_USER_SECRETS_KEY",
  "CLERK_SECRET_KEY",
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
  "REDIS_URL",
  "SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  "SUPABASE_S3_BUCKET",
  "SUPABASE_S3_ENDPOINT",
  "SUPABASE_STORAGE_PUBLIC_BASE_URL",
  "VIDEO_S3_BUCKET",
  "LLM_RESPONSE_FORMAT",
  "GOOGLE_API_KEY",
  "GOOGLE_PROJECT_NAME",
  "GOOGLE_PROJCT_NAME",
  "GOOGLE_PROJECT_NUMBER",
  "GEMINI_API_KEY",
  "GEMINI_ALLOWED_MODELS",
  "GEMINI_FALLBACK_MODEL",
  "STRICT_GEMINI",
  "OPENAI_API_KEY",
  "OPENAI_MODEL",
  "OPENAI_ALLOWED_MODELS",
  "OPENAI_TIMEOUT_SECONDS",
  "IMAGE_OUTPUT_ENABLED",
  "IMAGE_PROVIDER",
  "OPENAI_IMAGE_API_KEY",
  "OPENAI_IMAGE_MODEL",
  "OPENAI_IMAGE_SIZE",
  "OPENAI_IMAGE_QUALITY",
  "OPENAI_IMAGE_OUTPUT_FORMAT",
  "DESIGN_RESEARCH_ENABLED",
  "FIRECRAWL_API_KEY",
  "TAVILY_API_KEY",
  "FIREWORKS_API_KEY",
  "GMI_CLOUD_API_KEY",
  "LANGFUSE_BASE_URL",
  "LANGFUSE_PUBLIC_KEY",
  "LANGFUSE_SECRET_KEY",
]);

const requiredNames = [
  "BLUEPRINT_USER_SECRETS_KEY",
  "CLERK_SECRET_KEY",
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
  "REDIS_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  "SUPABASE_URL",
];

function parseEnvFile(path) {
  const values = {};
  for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator < 1) continue;
    const key = line.slice(0, separator).trim().replace(/^export\s+/u, "");
    if (!allowedNames.has(key)) continue;
    let value = line.slice(separator + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    if (value) values[key] = value;
  }
  return values;
}

const checkOnly = process.argv.includes("--check");
const suppliedFiles = process.argv.slice(2).filter((argument) => argument !== "--check");
const envFiles = suppliedFiles.length > 0
  ? suppliedFiles
  : ["../../.env", "../../.env.production.local"];
const backendEnvironment = {};
for (const envFile of envFiles) {
  Object.assign(backendEnvironment, parseEnvFile(resolve(envFile)));
}

const missing = requiredNames.filter((name) => !backendEnvironment[name]);
if (!backendEnvironment.GOOGLE_API_KEY && !backendEnvironment.GEMINI_API_KEY) {
  missing.push("GOOGLE_API_KEY or GEMINI_API_KEY");
}
if (missing.length > 0) {
  throw new Error(`Required backend configuration is missing: ${missing.join(", ")}`);
}

const serialized = JSON.stringify(backendEnvironment);
const bytes = Buffer.byteLength(serialized, "utf8");
if (bytes > 5_120) {
  throw new Error(`FORMA_BACKEND_ENV is ${bytes} bytes; Cloudflare secrets are limited to 5120 bytes.`);
}

if (checkOnly) {
  console.log(`Validated ${Object.keys(backendEnvironment).length} allowlisted backend settings (${bytes} bytes).`);
  process.exit(0);
}

const result = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["wrangler", "secret", "put", "FORMA_BACKEND_ENV"],
  { input: `${serialized}\n`, stdio: ["pipe", "inherit", "inherit"] },
);

if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
console.log(`Uploaded ${Object.keys(backendEnvironment).length} allowlisted backend settings as one encrypted Worker secret.`);
