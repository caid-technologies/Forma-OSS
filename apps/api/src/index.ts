import { env } from "cloudflare:workers";
import { Container, getContainer, type StopParams } from "@cloudflare/containers";

const requiredContainerVariables = [
  "BLUEPRINT_USER_SECRETS_KEY",
  "CLERK_SECRET_KEY",
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
  "REDIS_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  "SUPABASE_URL",
] as const;

function parseBackendEnvironment(serialized: string): Record<string, string> {
  let value: unknown;
  try {
    value = JSON.parse(serialized);
  } catch {
    throw new Error("FORMA_BACKEND_ENV must be a JSON object of backend environment variables.");
  }

  if (value === null || Array.isArray(value) || typeof value !== "object") {
    throw new Error("FORMA_BACKEND_ENV must be a JSON object of backend environment variables.");
  }

  const parsed: Record<string, string> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry !== "string" || !entry.trim()) {
      throw new Error(`FORMA_BACKEND_ENV entry ${key} must be a non-empty string.`);
    }
    parsed[key] = entry;
  }

  const missing: string[] = requiredContainerVariables.filter((key) => !parsed[key]);
  if (!parsed.GOOGLE_API_KEY && !parsed.GEMINI_API_KEY) {
    missing.push("GOOGLE_API_KEY or GEMINI_API_KEY");
  }
  if (missing.length > 0) {
    throw new Error(`FORMA_BACKEND_ENV is missing required entries: ${missing.join(", ")}.`);
  }
  return parsed;
}

export class FormaApiContainer extends Container<Cloudflare.Env> {
  defaultPort = 8000;
  requiredPorts = [8000];
  sleepAfter = "15m";
  enableInternet = true;
  envVars = {
    ...parseBackendEnvironment(env.FORMA_BACKEND_ENV),
    PORT: env.PORT,
    APP_ENV: env.APP_ENV,
    BLUEPRINT_AUTH_MODE: env.BLUEPRINT_AUTH_MODE,
    BLUEPRINT_DEPLOYMENT: env.BLUEPRINT_DEPLOYMENT,
    BLUEPRINT_DEV_MODE: env.BLUEPRINT_DEV_MODE,
    BLUEPRINT_DEBUG: env.BLUEPRINT_DEBUG,
    DATABASE_BACKEND: env.DATABASE_BACKEND,
    BLUEPRINT_IMAGE_STORAGE_BACKEND: env.BLUEPRINT_IMAGE_STORAGE_BACKEND,
    JOB_METADATA_BACKEND: env.JOB_METADATA_BACKEND,
    LLM_PROVIDER: env.LLM_PROVIDER,
    LLM_MODEL: env.LLM_MODEL,
    GEMINI_MODEL: env.GEMINI_MODEL,
    STRICT_LLM: env.STRICT_LLM,
    REDIS_CACHE_PREFIX: env.REDIS_CACHE_PREFIX,
    CORS_ALLOWED_ORIGINS: env.CORS_ALLOWED_ORIGINS,
    PUBLIC_FRONTEND_ORIGIN: env.PUBLIC_FRONTEND_ORIGIN,
    PROJECT_PURGE_WORKER_ENABLED: env.PROJECT_PURGE_WORKER_ENABLED,
    A2A_SOCKET_ENABLED: env.A2A_SOCKET_ENABLED,
    LOG_LEVEL: env.LOG_LEVEL,
  };

  override onStart(): void {
    console.log(JSON.stringify({ message: "Forma API container started" }));
  }

  override onStop({ exitCode, reason }: StopParams): void {
    console.log(
      JSON.stringify({ message: "Forma API container stopped", exitCode, reason }),
    );
  }

  override onError(error: unknown): never {
    console.error(
      JSON.stringify({
        message: "Forma API container error",
        error: error instanceof Error ? error.message : String(error),
      }),
    );
    throw error;
  }
}

export default {
  async fetch(request, workerEnv): Promise<Response> {
    try {
      return await getContainer(workerEnv.FORMA_API_CONTAINER).fetch(request);
    } catch (error) {
      console.error(
        JSON.stringify({
          message: "Forma API routing failed",
          path: new URL(request.url).pathname,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
      return Response.json(
        { error: "Backend container is temporarily unavailable." },
        { status: 503 },
      );
    }
  },
} satisfies ExportedHandler<Cloudflare.Env>;
