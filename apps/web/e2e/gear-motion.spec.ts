import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

test("gear example plays, pauses, scrubs and reopens both real bodies", async ({ page, baseURL }, testInfo) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const origin = new URL(baseURL!).origin;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === origin && !url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname.replace(/^\/api(?=\/|$)/, "");
    if (path === "/runtime/config") return route.fulfill({ json: {
      contract_version: 1, authority: "backend", forma_dev_mode: false,
      generation: { ready: true, available: true, reason: null, selected_llm: null, llm_options: [] },
      images: { enabled: false, configured: false, request_capable: false, provider: null, model: null, generate_by_default: false, reason: null },
      workflow: { default_id: "default", options: [{ id: "default", label: "Default", description: "Test" }] },
      provider_setup: { required: false, llm_required: false, image_required: false },
      deployment: { hosted_chat_enabled: false, authoring_mode_enabled: true, authoring_access: true, opencode_connector_id: "test" },
      video: { generation: { configured: false, reason: null }, self_correction: { configured: false, reason: null } },
    } });
    if (["/projects", "/my/projects"].includes(path)) return route.fulfill({ json: { items: [], total: 0, has_more: false } });
    if (["/chats", "/a2a/jobs", "/example-project-object-jobs"].includes(path)) return route.fulfill({ json: [] });
    return route.fulfill({ json: { status: "ok", is_admin: false, steps: [], models: [] } });
  });

  await page.goto("/?example=spur_gear_pair&tab=mechanical", { waitUntil: "domcontentloaded" });
  const view = page.getByLabel("Articulated CAD motion preview", { exact: true });
  await expect(view).toBeVisible({ timeout: 120_000 });
  await expect(view.locator("canvas")).toBeVisible();
  const driver = view.getByLabel("GEAR_DRIVER angle", { exact: true });
  const driven = view.getByLabel("GEAR_DRIVEN angle", { exact: true });
  const timeline = view.getByRole("slider", { name: "Mechanism timeline" });
  await expect(driver).toHaveText("0.0°");
  await timeline.fill("125");
  await expect(driver).toHaveText("90.0°");
  await expect(driven).toHaveText("-45.0°");
  await page.screenshot({ path: testInfo.outputPath("gears-quarter-driver-turn.png") });
  await view.getByRole("button", { name: "Driver gear", exact: true }).click();
  await view.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(() => driver.innerText()).not.toBe("90.0°");
  await view.getByRole("button", { name: "Pause", exact: true }).click();
  const a = parseFloat(await driver.innerText());
  const b = parseFloat(await driven.innerText());
  expect(Math.abs(a + b * 2)).toBeLessThan(.11);
  const paused = await timeline.inputValue();
  await page.waitForTimeout(200);
  expect(await timeline.inputValue()).toBe(paused);
  await view.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(driver).toHaveText("0.0°");
  await expect(driven).toHaveText("0.0°");
  await page.reload();
  await expect(view).toBeVisible();
  await expect(view.getByRole("button", { name: "Driven gear", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
