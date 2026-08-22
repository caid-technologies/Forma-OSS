import { expect, test } from "@playwright/test";

test("simulation flow generates, inspects, and reloads a project without duplicate local execute", async ({ page }) => {
  const executeRequests: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/build/plans/") && url.endsWith("/execute")) {
      executeRequests.push(url);
    }
  });

  await page.goto("/");

  await page.getByRole("textbox", { name: /describe the hardware idea/i }).fill(
    "Build a battery powered plant watering monitor with soil moisture sensing, OLED status, USB-C charging, and a compact 3D printed enclosure.",
  );
  await page.getByRole("button", { name: /check hardware idea/i }).click();

  await expect(page.getByRole("button", { name: /safe prototype defaults/i })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /safe prototype defaults/i }).click();

  await expect(page.getByText(/structured design revision is available for review/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Bill of Materials" })).toBeVisible();

  await page.getByRole("button", { name: "Bill of Materials" }).click();
  await expect(page.getByText(/total estimated cost/i)).toBeVisible();

  await page.getByRole("button", { name: "Mechanical" }).click();
  await expect(page.getByRole("button", { name: "Mechanical" })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Electrical" }).click();
  await expect(page.getByRole("button", { name: "Electrical" })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Documentation" }).click();
  await expect(page.getByRole("heading", { name: "Build Instructions" })).toBeVisible();

  expect(executeRequests).toEqual([]);

  const chatUrl = new URL(page.url());
  const projectId = chatUrl.pathname.split("/").filter(Boolean).at(-1);
  expect(projectId).toBeTruthy();

  await page.goto(`/project/${projectId}?tab=overview`);
  await expect(page.getByRole("heading", { level: 1, name: /Plant Moisture Monitor|Watering System/i })).toBeVisible();
  await expect(page.getByText("Product image disabled")).toBeVisible();
});

test("reload during an active build completes without local execute", async ({ page }) => {
  const executeRequests: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/build/plans/") && url.endsWith("/execute")) {
      executeRequests.push(url);
    }
  });

  await page.goto("/");
  await page.getByRole("textbox", { name: /describe the hardware idea/i }).fill(
    "Build a battery powered plant watering monitor with soil moisture sensing, OLED status, USB-C charging, and a compact 3D printed enclosure.",
  );
  await page.getByRole("button", { name: /check hardware idea/i }).click();
  await expect(page.getByRole("button", { name: /safe prototype defaults/i })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /safe prototype defaults/i }).click();
  await page.reload();
  await expect(page.getByText(/structured design revision is available for review/i)).toBeVisible({ timeout: 60_000 });
  expect(executeRequests).toEqual([]);
});
