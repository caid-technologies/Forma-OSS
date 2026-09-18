import { expect, test, type Route } from "@playwright/test";
import type { RuntimeConfigContract } from "../lib/config";
import type { OpenCodeCommand, OpenCodeEvent, OpenCodeSession } from "../lib/opencode";

const projectId = "746df932-f4ed-49a4-a36e-5a50a22aa918";
const sessionId = "session-opencode-chat";
const commandIds = ["command-first-turn", "command-second-turn"];
const answers = ["Hello from OpenCode.", "Still here in the same OpenCode session."];
const publishedProject = {
  project_id: projectId,
  chat_id: "839aeb42-31d5-4b74-91f8-a93bc3a17db6",
  can_chat: true,
  prompt: "hi",
  project_ir: {
    overview: {
      title: "USB-powered status monitor",
      description: "A minimal low-voltage status monitor using an ESP32 development board.",
      difficulty: "Beginner",
      estimated_cost: 5,
      category: "Monitoring",
    },
    part_definitions: [{
      part_definition_id: "esp32",
      part_number: "ESP32-DevKitC",
      name: "ESP32 development board",
      category: "Microcontroller",
      unit_price: 5,
      rationale: "Provides USB power and an onboard controller for the status monitor.",
      pins: [],
    }],
    components: Array.from({ length: 9 }, (_, index) => ({
      ref_des: `U${index + 1}`, part_definition_id: "esp32", rationale: "Controller module",
    })),
    connections: [],
    nets: [],
    assembly: [],
    constraints: ["Power from 5V USB only."],
    validation: { critical: [], warning: [], info: [] },
    // Identity is supplied by the GET envelope, as consumed by withProjectResponseMetadata.
    assembly_metadata: { workflow: "default", source_prompt: "hi" },
  },
};

const runtimeConfig: RuntimeConfigContract = {
  contract_version: 1,
  authority: "backend",
  forma_dev_mode: false,
  generation: {
    ready: true,
    available: true,
    reason: null,
    selected_llm: null,
    llm_options: [],
  },
  images: {
    enabled: false,
    configured: false,
    request_capable: false,
    provider: null,
    model: null,
    generate_by_default: false,
    reason: null,
  },
  workflow: {
    default_id: "default",
    options: [{ id: "default", label: "Default", description: "Local OpenCode authoring" }],
  },
  provider_setup: { required: false, llm_required: false, image_required: false },
  deployment: {
    hosted_chat_enabled: false,
    authoring_mode_enabled: true,
    authoring_access: true,
    opencode_connector_id: "mini-pc-1",
  },
  video: {
    generation: { configured: false, reason: null },
    self_correction: { configured: false, reason: null },
  },
};

function event(
  sequence: number,
  kind: OpenCodeEvent["kind"],
  overrides: Partial<OpenCodeEvent> = {},
): OpenCodeEvent {
  return {
    event_id: `event-${sequence}`,
    sequence,
    session_id: sessionId,
    project_id: projectId,
    kind,
    status: null,
    message: null,
    revision_id: null,
    error: null,
    created_at: "2026-09-12T12:00:00Z",
    ...overrides,
  };
}

// FORMA_AUTH_MODE=local must be supplied to the local web server, not mocked in the browser.
test.use({ serviceWorkers: "block" });

for (const accessResult of ["enabled", "maintenance", "failed"] as const) {
  test(`Chat access loading handles ${accessResult} without a maintenance flash`, async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    const appOrigin = new URL(baseURL!).origin;
    let releaseConfig!: () => void;
    const configGate = new Promise<void>((resolve) => { releaseConfig = resolve; });
    let configRequests = 0;

    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === appOrigin && !/^\/api(?:\/|$)/.test(url.pathname)) {
        await route.continue();
        return;
      }
      const path = url.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
      if (path === "/runtime/config") {
        configRequests += 1;
        await configGate;
        if (accessResult === "failed" && configRequests === 1) {
          await route.fulfill({ status: 503, json: { detail: "Temporarily unavailable" } });
        } else {
          await route.fulfill({ json: {
            ...runtimeConfig,
            deployment: { ...runtimeConfig.deployment, authoring_access: accessResult !== "maintenance" },
          } });
        }
        return;
      }
      if (["/projects", "/my/projects"].includes(path)) {
        await route.fulfill({ json: { items: [], total: 0, has_more: false } });
      } else if (["/chats", "/a2a/jobs", "/example-project-object-jobs"].includes(path)) {
        await route.fulfill({ json: [] });
      } else {
        await route.fulfill({ json: { status: "ok", is_admin: false, steps: [], models: [] } });
      }
    });

    try {
      await page.goto("/", { waitUntil: "domcontentloaded", timeout: 120_000 });
      const loading = page.getByRole("status").filter({ hasText: "Loading chat…" });
      const maintenance = page.getByRole("status", { name: "Hosted chat maintenance" });
      const composer = page.getByPlaceholder("Describe the product, constraints, references, and outputs you need…", { exact: true });
      await expect(loading).toBeVisible();
      await expect.poll(() => configRequests).toBe(1);
      await expect(maintenance).toHaveCount(0);
      await expect(composer).toHaveCount(0);
      releaseConfig();

      if (accessResult === "maintenance") {
        await expect(maintenance).toBeVisible();
        await expect(composer).toHaveCount(0);
      } else {
        if (accessResult === "failed") {
          await expect(page.getByRole("alert").filter({ hasText: "Chat could not be loaded" })).toBeVisible();
          await expect(maintenance).toHaveCount(0);
          await page.getByRole("button", { name: "Retry loading chat" }).click();
        }
        await expect(composer).toBeVisible();
        await expect(maintenance).toHaveCount(0);
      }
      await expect(loading).toHaveCount(0);
    } finally {
      releaseConfig();
    }
  });
}

for (const resultMode of ["unpublished", "published", "draft", "wired", "forbidden", "unavailable", "malformed", "null-response", "network-error", "missing-revision"] as const) test(`OpenCode chat handles ${resultMode} project output`, async ({ page, baseURL }) => {
  const projectPublished = ["published", "draft", "wired"].includes(resultMode);
  const resultLoadFails = !projectPublished && resultMode !== "unpublished";
  const readiness = resultMode === "draft" ? "draft" : resultMode === "wired" ? "complete" : "partial";
  const savedProject = structuredClone(publishedProject);
  if (resultMode === "draft") {
    savedProject.project_ir.components = [];
    savedProject.project_ir.part_definitions = [];
  }
  const wiredIR = {
    ...publishedProject.project_ir,
    part_definitions: [{
      ...publishedProject.project_ir.part_definitions[0],
      pins: [{ pin_id: "VBUS", name: "USB power", pin_type: "Power", voltage: 5 }],
    }],
    components: publishedProject.project_ir.components.slice(0, 2),
    nets: [{ net_id: "USB", name: "USB power", net_type: "Power", pins: [
      { ref_des: "U1", pin_id: "VBUS" }, { ref_des: "U2", pin_id: "VBUS" },
    ] }],
  };
  test.setTimeout(180_000);
  const appOrigin = new URL(baseURL!).origin;
  expect(["localhost", "127.0.0.1", "[::1]"]).toContain(new URL(appOrigin).hostname);

  const unexpectedRequests: string[] = [];
  const pageErrors: string[] = [];
  const configErrors: string[] = [];
  const sessionRequests: unknown[] = [];
  const commandRequests: { path: string; body: unknown }[] = [];
  const polls: { turn: number; cursor: number }[] = [];
  const completedTurns: number[] = [];
  const projectProbes: { turn: number; afterCompletion: boolean }[] = [];
  const projectResponseStatuses: number[] = [];
  let originalChatUrl = "";
  let releaseProgress!: () => void;
  let releaseCompletion!: () => void;
  const progressGate = new Promise<void>((resolve) => { releaseProgress = resolve; });
  const completionGate = new Promise<void>((resolve) => { releaseCompletion = resolve; });

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && message.text().includes("Error fetching runtime config")) {
      configErrors.push(message.text());
    }
  });

  // Only local app assets/navigation may escape the mocks. Unknown backends fail closed.
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === appOrigin && !/^\/api(?:\/|$)/.test(url.pathname)) {
      await route.continue();
      return;
    }
    unexpectedRequests.push(`${route.request().method()} ${url.href}`);
    await route.abort("blockedbyclient");
  });

  const mockBackend = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
    const method = request.method();

    if (method === "OPTIONS") {
      await route.fulfill({ status: 204 });
      return;
    }
    if (method === "GET" && path === "/runtime/config") {
      await route.fulfill({ json: runtimeConfig });
      return;
    }
    if (method === "GET" && path === "/") {
      await route.fulfill({ json: { status: "ok" } });
      return;
    }
    if (method === "GET" && ["/projects", "/my/projects"].includes(path)) {
      await route.fulfill({ json: {
        items: [], total: 0, has_more: false,
        limit: Number(url.searchParams.get("limit") || 6),
        offset: Number(url.searchParams.get("offset") || 0),
      } });
      return;
    }
    if (method === "GET" && ["/chats", "/a2a/jobs", "/example-project-object-jobs"].includes(path)) {
      await route.fulfill({ json: [] });
      return;
    }
    if (method === "GET" && path === "/admin/session") {
      await route.fulfill({ json: { is_admin: false } });
      return;
    }
    if (method === "GET" && path === "/pipeline/steps") {
      await route.fulfill({ json: { steps: [] } });
      return;
    }
    if (method === "GET" && path === "/video/models") {
      await route.fulfill({ json: { models: [], generation_configured: false } });
      return;
    }
    if (method === "POST" && path === "/opencode/sessions") {
      sessionRequests.push(request.postDataJSON());
      const session: OpenCodeSession = {
        session_id: sessionId,
        connector_id: "mini-pc-1",
        project_id: projectId,
        owner_user_id: "local-user",
        status: "active",
      };
      await route.fulfill({ json: session });
      return;
    }
    if (method === "POST" && path === `/opencode/sessions/${sessionId}/commands`) {
      commandRequests.push({ path, body: request.postDataJSON() });
      const command: OpenCodeCommand = {
        command_id: commandIds[commandRequests.length - 1],
        session_id: sessionId,
        project_id: projectId,
        operation: "project_message",
        status: "queued",
      };
      await route.fulfill({ json: command });
      return;
    }
    if (method === "GET" && path === `/opencode/sessions/${sessionId}/events`) {
      const cursor = Number(url.searchParams.get("cursor"));
      const turn = commandRequests.length;
      polls.push({ turn, cursor });
      let events: OpenCodeEvent[] = [];
      if (turn === 1 && cursor === 0) {
        events = [event(1, "connector_unavailable", {
          event_id: `connector_unavailable_${sessionId}`,
          message: "Waiting for the local OpenCode connector.",
        })];
      } else if (turn === 1 && cursor === 1) {
        await progressGate;
        events = [event(2, "queued", { status: "queued" }), event(3, "working", { status: "running" })];
      } else if ((turn === 1 && cursor === 3) || (turn === 2 && cursor === 5)) {
        if (turn === 1) await completionGate;
        const sequence = turn === 1 ? 4 : 6;
        // The canonical terminal event shares the page with the answer but has no message.
        events = [
          event(sequence, "assistant_message", { message: answers[turn - 1] }),
          event(sequence + 1, "completed", {
            event_id: `${commandIds[turn - 1]}:terminal`,
            status: "succeeded",
            revision_id: resultMode === "missing-revision" ? "saved-revision" : null,
          }),
        ];
        completedTurns.push(turn);
      }
      await route.fulfill({ json: { events, next_cursor: events.at(-1)?.sequence ?? cursor } });
      return;
    }
    if (method === "GET" && path === `/projects/${projectId}`) {
      const turn = commandRequests.length;
      projectProbes.push({ turn, afterCompletion: completedTurns.includes(turn) });
      if (resultMode === "network-error") {
        await route.abort("failed");
        return;
      }
      const status = resultMode === "forbidden" ? 403
        : resultMode === "unavailable" ? 503
        : resultMode === "malformed" || resultMode === "null-response" ? 200
        : !projectPublished ? 404 : projectProbes.length === 1 ? 503 : 200;
      projectResponseStatuses.push(status);
      await route.fulfill({
        status,
        json: resultMode === "null-response" ? null : resultMode === "malformed" ? { project_id: projectId } : status === 200 ? { ...savedProject, project_ir: resultMode === "wired" ? wiredIR : savedProject.project_ir, project_readiness: readiness } : {
          detail: status === 404 ? "Project not found" : "Project store temporarily unavailable",
        },
      });
      return;
    }

    unexpectedRequests.push(`${method} ${url.href}`);
    await route.fulfill({ status: 501, json: { detail: `Unmocked endpoint: ${method} ${path}` } });
  };

  await page.route("**/api/**", mockBackend);
  await page.route(/^https?:\/\/(?:localhost|127\.0\.0\.1):8000(?:\/|$)/, mockBackend);
  await page.clock.install();

  try {
    try {
      await page.goto("/", { waitUntil: "domcontentloaded", timeout: 120_000 });
    } catch (error) {
      // Match the existing suite's workaround for a first Next dev compilation.
      if (!String(error).includes("ERR_ABORTED")) throw error;
      await page.goto("/", { waitUntil: "domcontentloaded", timeout: 120_000 });
    }

    const composer = page.getByPlaceholder("Describe the product, constraints, references, and outputs you need\u2026", { exact: true });
    const followUpComposer = projectPublished ? page.getByRole("textbox", { name: /Describe a change to/ }) : composer;
    const stop = page.getByRole("button", { name: "Stop generation", exact: true });
    const missingProject = page.getByText(/no longer available in (?:the )?project database/i);
    const projectLinks = page.locator(`a[href*="${projectId}"]`);
    const projectOutput = page.getByTestId("project-pane");
    const firstAnswer = page.getByRole("main").getByText(answers[0], { exact: false });
    const secondAnswer = page.getByRole("main").getByText(answers[1], { exact: false });

    await expect(page.getByRole("status", { name: "Forma Agent is authoring this workspace.", exact: true })).toBeVisible();
    await expect(composer).toBeVisible();

    await test.step("keep polling after connector_unavailable without loading the reserved project", async () => {
      await composer.fill("hi");
      await composer.press("Enter");
      await expect.poll(() => polls).toContainEqual({ turn: 1, cursor: 1 });
      await expect(page).toHaveURL(/\/chat\/[^/?#]+$/);
      originalChatUrl = page.url();
      expect(new URL(originalChatUrl).pathname.split("/").at(-1)).not.toBe(publishedProject.chat_id);
      await expect(stop).toBeVisible();
      expect(sessionRequests).toEqual([{ connector_id: "mini-pc-1" }]);
      expect(projectProbes).toEqual([]);
      await expect(missingProject).toHaveCount(0);
      await expect(projectLinks).toHaveCount(0);

      releaseProgress();
      await expect.poll(() => polls).toContainEqual({ turn: 1, cursor: 3 });
      await expect(stop).toBeVisible();
      expect(projectProbes).toEqual([]);
      await expect(missingProject).toHaveCount(0);
      await expect(projectLinks).toHaveCount(0);
    });

    await test.step(projectPublished
      ? "preserve the answer and original chat URL after canonical completion and a 503 retry"
      : "preserve the answer after canonical completion and exactly one 404 probe", async () => {
      releaseCompletion();
      if (resultLoadFails) {
        await expect.poll(() => projectProbes.length).toBeGreaterThan(0);
        await page.clock.runFor(6_000);
        await expect(stop).toHaveCount(0);
        await expect(page.getByRole("main").getByText(/OpenCode.*(?:project could not be loaded|no usable Hardware IR|project is not available)/).first()).toBeVisible();
        await expect(page.getByRole("main").getByText(/Hello from OpenCode/).first()).toBeVisible();
        await expect(projectOutput).toHaveCount(0);
        await expect(page).toHaveURL(originalChatUrl);
        expect(projectProbes).toHaveLength(resultMode === "unavailable" || resultMode === "network-error" ? 3 : 1);
        await page.clock.runFor(10_000);
        expect(polls).toHaveLength(3);
        return;
      }
      await expect(firstAnswer).toBeVisible();
      if (projectPublished) {
        await expect.poll(() => projectResponseStatuses[0]).toBe(503);
      } else {
        await expect(stop).toHaveCount(0);
        await expect.poll(() => projectProbes).toEqual([{ turn: 1, afterCompletion: true }]);
      }

      // Advance beyond the poll and hydration retry delays without a wall-clock sleep.
      await page.clock.runFor(6_000);
      await expect(stop).toHaveCount(0);
      await expect(firstAnswer).toBeVisible();
      await expect(firstAnswer).toHaveCount(1);
      await expect(missingProject).toHaveCount(0);
      await expect(page).toHaveURL(originalChatUrl);
      if (projectPublished) {
        await expect.poll(() => projectResponseStatuses.slice(0, 2)).toEqual([503, 200]);
        await expect(projectOutput).toBeVisible();
        if (resultMode === "draft") await expect(page.getByText(/Draft saved only/).first()).toBeVisible();
        if (resultMode === "published") await expect(page.getByText(/An incomplete design was saved/).first()).toBeVisible();
        if (resultMode === "wired") await expect(page.getByText(/Draft saved only|An incomplete design was saved/)).toHaveCount(0);
        await expect(projectOutput.getByRole("heading", { name: publishedProject.project_ir.overview.title, exact: true })).toBeVisible();
        await expect(projectOutput.getByText(publishedProject.project_ir.overview.description, { exact: true })).toBeVisible();
        // Successful publication may also trigger route/inline hydration GETs.
        expect(projectProbes.every((probe) => probe.turn === 1 && probe.afterCompletion)).toBe(true);
        expect(projectResponseStatuses.slice(1).every((status) => status === 200)).toBe(true);
      } else {
        await expect(projectLinks).toHaveCount(0);
        await expect(projectOutput).toHaveCount(0);
        expect(projectProbes).toEqual([{ turn: 1, afterCompletion: true }]);
      }
      expect(polls).toEqual([{ turn: 1, cursor: 0 }, { turn: 1, cursor: 1 }, { turn: 1, cursor: 3 }]);
    });

    if (resultLoadFails) {
      expect(unexpectedRequests).toEqual([]);
      expect(pageErrors).toEqual([]);
      return;
    }

    await test.step("send a second turn in the same session and original UI chat", async () => {
      await followUpComposer.fill("Are you still there?");
      await followUpComposer.press("Enter");
      await expect(secondAnswer).toBeVisible();
      await expect(stop).toHaveCount(0);
      if (projectPublished) {
        await expect.poll(() => projectProbes).toContainEqual({ turn: 2, afterCompletion: true });
      } else {
        await expect.poll(() => projectProbes).toEqual([
          { turn: 1, afterCompletion: true }, { turn: 2, afterCompletion: true },
        ]);
      }
      await page.clock.runFor(6_000);
      await expect(firstAnswer).toBeVisible();
      await expect(firstAnswer).toHaveCount(1);
      await expect(secondAnswer).toBeVisible();
      await expect(secondAnswer).toHaveCount(1);
      await expect(missingProject).toHaveCount(0);
      await expect(page).toHaveURL(originalChatUrl);
      if (projectPublished) {
        await expect(projectOutput).toBeVisible();
        await expect(projectOutput.getByRole("heading", { name: publishedProject.project_ir.overview.title, exact: true })).toBeVisible();
        expect(projectProbes.every((probe) => probe.afterCompletion)).toBe(true);
        expect(projectResponseStatuses.slice(1).every((status) => status === 200)).toBe(true);
      } else {
        await expect(projectLinks).toHaveCount(0);
        expect(projectProbes).toHaveLength(2);
      }
      expect(sessionRequests).toEqual([{ connector_id: "mini-pc-1" }]);
      expect(commandRequests).toEqual(["hi", "Are you still there?"].map((message) => ({
        path: `/opencode/sessions/${sessionId}/commands`,
        body: { message, idempotency_key: expect.stringMatching(/^web-.+/) },
      })));
      expect(polls).toEqual([
        { turn: 1, cursor: 0 }, { turn: 1, cursor: 1 }, { turn: 1, cursor: 3 }, { turn: 2, cursor: 5 },
      ]);
    });

    if (projectPublished) await test.step("the real OpenCode page shares one pane and preserves mobile drafts", async () => {
      const layout = page.getByTestId("chat-project-layout");
      await expect(layout).toHaveAttribute("data-layout", "split");
      await expect(projectOutput).toHaveCount(1);
      await expect(page.getByTestId("chat-pane").getByTestId("project-pane")).toHaveCount(0);
      await expect(page.getByTestId("chat-pane").locator("canvas")).toHaveCount(0);
      const currentCard = page.getByRole("button", { name: /View current project/ }).last();
      await expect(currentCard).toBeVisible();
      await page.getByRole("button", { name: "Close project", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await currentCard.click();
      await expect(projectOutput).toHaveCount(1);
      await page.getByRole("button", { name: "View project full screen", exact: true }).click();
      await expect(page.getByRole("dialog", { name: "Project workspace", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(layout).toHaveAttribute("data-layout", "split");
      await expect(projectOutput).toHaveCount(1);
      await page.screenshot({ path: `test-results/opencode-${resultMode}-workspace-desktop.png`, fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "Chat", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await followUpComposer.fill("Preserve this mobile draft");
      await page.getByRole("button", { name: "Show project", exact: true }).click();
      await expect(projectOutput).toHaveCount(1);
      await expect(page.getByTestId("chat-pane")).toBeHidden();
      await page.getByRole("button", { name: "Chat", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await expect(followUpComposer).toHaveValue("Preserve this mobile draft");
      await page.screenshot({ path: `test-results/opencode-${resultMode}-workspace-mobile.png`, fullPage: true });
      await followUpComposer.fill("");
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.getByRole("button", { name: "Show project", exact: true }).click();
      await expect(layout).toHaveAttribute("data-layout", "split");
    });

    await test.step("New chat resets the rendered conversation with legacy hosted chat disabled", async () => {
      const previousUrl = page.url();
      const newChat = page.getByRole("button", { name: "New chat", exact: true }).filter({ visible: true });
      await expect(newChat).toBeEnabled();
      await followUpComposer.fill("Unsent draft");
      await newChat.click();
      await expect(page).not.toHaveURL(previousUrl);
      await page.clock.runFor(6_000);
      await expect(composer).toHaveValue("");
      await expect(firstAnswer).toHaveCount(0);
      await expect(secondAnswer).toHaveCount(0);
      await expect(newChat).toBeDisabled();
      await expect(page.getByRole("status", { name: "Hosted chat maintenance", exact: true })).toHaveCount(0);
      await expect(missingProject).toHaveCount(0);
      await expect(projectLinks).toHaveCount(0);
      await expect(projectOutput).toHaveCount(0);
    });

    expect(unexpectedRequests, "Every backend request must be mocked; no external requests may escape").toEqual([]);
    expect(configErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
  } finally {
    releaseProgress();
    releaseCompletion();
  }
});
