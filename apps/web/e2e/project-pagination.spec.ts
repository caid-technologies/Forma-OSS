import { expect, test, type Page } from "@playwright/test";

type Project = {
  project_id: string;
  title: string;
  description: string;
};

const projects: Project[] = Array.from({ length: 7 }, (_, index) => ({
  project_id: `project-${index + 1}`,
  title: `Project ${index + 1}`,
  description: "A test project",
}));

function pageResponse(url: URL) {
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || 6);
  return {
    items: projects.slice(offset, offset + limit),
    total: projects.length,
    limit,
    offset,
    has_more: offset + limit < projects.length,
  };
}

async function mockProjectList(page: Page, path: string) {
  const endpoint = new RegExp(
    `^https?://(?:localhost|127\\.0\\.0\\.1):8000/(?:api/)?${path}(?:\\?|$)`,
  );
  await page.route(endpoint, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(pageResponse(new URL(route.request().url()))),
    });
  });
}

async function openRoute(page: Page, path: string) {
  try {
    await page.goto(path, { waitUntil: "domcontentloaded", timeout: 120_000 });
  } catch (error) {
    // Next dev can detach a frame while compiling a freshly requested route.
    if (!String(error).includes("ERR_ABORTED")) throw error;
    await page.goto(path, { waitUntil: "domcontentloaded", timeout: 120_000 });
  }
}

function projectCards(page: Page) {
  return page.locator("section.forma-gui-browser[aria-busy='false'] .forma-gui-card:not(.forma-gui-card-skeleton)");
}

test.describe("project pagination", () => {
  test("community keeps six fetched projects per page", async ({ page }) => {
    await mockProjectList(page, "projects");
    await openRoute(page, "/projects");

    await expect(page.getByRole("main").getByRole("heading", { name: "Community" })).toBeVisible();
    await expect(projectCards(page)).toHaveCount(6);
    await expect(page.getByText("Page 1 of 2")).toBeVisible();

    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(projectCards(page)).toHaveCount(1);
    await expect(page.getByText("Page 2 of 2")).toBeVisible();
  });

  test("my projects uses the same page size and search contract", async ({ page }) => {
    const requests: string[] = [];
    await page.route(/^https?:\/\/(?:localhost|127\.0\.0\.1):8000\/(?:api\/)?my\/projects(?:\?|$)/, async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(pageResponse(new URL(route.request().url()))),
      });
    });
    await openRoute(page, "/my-projects");

    await expect(page.getByRole("main").getByRole("heading", { name: "My projects" })).toBeVisible();
    await expect(projectCards(page)).toHaveCount(6);
    await expect(page.getByText("Page 1 of 2")).toBeVisible();

    await page.getByPlaceholder("Search projects").fill("controller");
    await expect.poll(() => requests.some((url) => url.includes("q=controller"))).toBe(true);
  });
});
