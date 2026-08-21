import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number(process.env.FRONTEND_PORT || 3010);
const backendPort = Number(process.env.BACKEND_PORT || 8010);
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${frontendPort}`;
const webServer = process.env.PLAYWRIGHT_REUSE_EXISTING === "1"
  ? undefined
  : {
      command: [
        "cd ../.. &&",
        "FORMA_AUTH_MODE=local",
        "FORMA_USER_SECRETS_KEY=${FORMA_USER_SECRETS_KEY:-playwright-local-secret-not-for-production}",
        "FORMA_DEV_MODE=true",
        "DATABASE_BACKEND=sqlite",
        "SQLITE_DATABASE_URL=${SQLITE_DATABASE_URL:-sqlite:///$PWD/tmp/playwright/forma-e2e.db}",
        "LLM_PROVIDER=simulation",
        "IMAGE_OUTPUT_ENABLED=false",
        "IMAGE_PROVIDER=none",
        `NEXT_PUBLIC_API_URL=http://127.0.0.1:${backendPort}`,
        `BACKEND_PORT=${backendPort}`,
        `FRONTEND_PORT=${frontendPort}`,
        "./scripts/development/dev.sh",
      ].join(" "),
      url: baseURL,
      reuseExistingServer: false,
      timeout: 120_000,
    };

export default defineConfig({
  testDir: "./test/e2e",
  timeout: 90_000,
  expect: {
    timeout: 20_000,
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  ...(webServer ? { webServer } : {}),
});
