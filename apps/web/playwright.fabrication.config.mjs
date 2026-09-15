import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", testMatch: "fabrication-settings.spec.mjs", workers: 1, retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:4176", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "node test/serve-fabrication-fixture.mjs", url: "http://127.0.0.1:4176", reuseExistingServer: false },
});
