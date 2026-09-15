import { test, expect } from "@playwright/test";

const printers = [
  { printer_id: "creality_ender_3_04", display_name: "Creality Ender-3", nozzle_mm: 0.4, material: "PLA", layer_height_mm: 0.2 },
  { printer_id: "bambu_a1_04", display_name: "Bambu Lab A1", nozzle_mm: 0.4, material: "PLA", layer_height_mm: 0.2 },
];
async function api(page, { available = false, failSave = false, failLoad = false } = {}) {
  const saved = new Map();
  const writes = [];
  await page.route("**/api/user/settings/fabrication", async (route) => {
    const owner = route.request().headers().authorization;
    if (route.request().method() === "PUT") {
      if (failSave) return route.fulfill({ status: 503, json: { detail: { message: "unavailable" } } });
      const body = route.request().postDataJSON();
      writes.push({ owner, body });
      saved.set(owner, body.printer_id);
    } else if (failLoad) return route.fulfill({ status: 503, json: {} });
    await route.fulfill({ json: { printer_id: saved.get(owner) || printers[0].printer_id,
      source: saved.has(owner) ? "user" : "default", updated_at: saved.has(owner) ? "today" : null, printers } });
  });
  await page.route("**/api/projects/*/exports", (route) => route.fulfill({ json: {
    project_id: "project", step: { filename: "assembly.step", sha256: "a".repeat(64), size_bytes: 100,
      download_url: "/projects/project/exports/step/" + "a".repeat(64) },
    printers: printers.map((printer) => ({ ...printer, available, unavailable_reason: available ? null : "OrcaSlicer is not installed on this worker." })),
  } }));
  await page.route("**/api/projects/*/exports/step/*", (route) => route.fulfill({ contentType: "model/step", body: "STEP fixture" }));
  return { saved, writes };
}

test("save while worker unavailable; restore across reload, projects and account settings", async ({ page }) => {
  const state = await api(page);
  await page.goto("/");
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue(printers[0].printer_id);
  await expect(page.getByRole("button", { name: "Generate G-code" })).toBeDisabled();
  await page.getByRole("combobox", { name: "Printer" }).selectOption("bambu_a1_04");
  await page.getByRole("button", { name: "Save printer preference" }).click();
  await expect(page.getByRole("status")).toHaveText("Printer preference saved to your account.");
  expect(state.writes).toEqual([{ owner: "Bearer alice", body: { printer_id: "bambu_a1_04" } }]);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("bambu_a1_04");
  await page.getByRole("button", { name: "Other project", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("bambu_a1_04");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download STEP", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("assembly.step");
  await page.getByRole("button", { name: "Toggle account settings" }).click();
  await expect(page.getByRole("heading", { name: "Printer & fabrication" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("bambu_a1_04");
});

test("switching accounts clears draft selection and does not leak saved preferences", async ({ page }) => {
  await api(page);
  await page.goto("/");
  await page.getByRole("combobox", { name: "Printer" }).selectOption("bambu_a1_04");
  await page.getByRole("button", { name: "Save printer preference" }).click();
  await expect(page.getByRole("status")).toContainText("saved to your account");
  await page.getByRole("button", { name: "Switch to Bob" }).click();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("creality_ender_3_04");
  await expect(page.getByRole("status")).toHaveText("Not saved to your account yet.");
  await page.getByRole("button", { name: "Switch to Alice" }).click();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("bambu_a1_04");
});

test("failed save stays unsaved and can be retried", async ({ page }) => {
  const state = await api(page, { failSave: true });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Printer" }).selectOption("bambu_a1_04");
  await page.getByRole("button", { name: "Save printer preference" }).click();
  await expect(page.getByRole("alert")).toContainText("were not saved");
  await expect(page.getByRole("status")).toHaveText("Not saved to your account yet.");
  await expect(page.getByRole("button", { name: "Save printer preference" })).toBeEnabled();
  expect(state.writes).toHaveLength(0);
});

test("failed preferences do not block STEP and offer retry instead of a fake saved default", async ({ page }) => {
  await api(page, { failLoad: true });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  await expect(page.getByRole("combobox", { name: "Printer" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Retry printer settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download STEP", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Generate G-code" })).toBeDisabled();
});

test("generation uses the selected reviewed preset; an override does not change account settings", async ({ page }) => {
  const state = await api(page, { available: true });
  let submitted;
  await page.route("**/api/projects/*/exports/gcode", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 503, json: { detail: { message: "Test worker unavailable" } } });
  });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Printer" }).selectOption("bambu_a1_04");
  await page.getByRole("button", { name: "Generate G-code" }).click();
  await expect(page.getByText("Test worker unavailable", { exact: true })).toBeVisible();
  expect(submitted).toEqual({ printer_id: "bambu_a1_04" });
  expect(state.writes).toHaveLength(0);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Printer" })).toHaveValue("creality_ender_3_04");
});
