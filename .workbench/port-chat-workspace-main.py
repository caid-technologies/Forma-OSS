"""One-time integration helper. Removed before review; never used at app runtime."""
from pathlib import Path
import subprocess

SOURCE = "e20037ba38c06f60a55d89b451855e2027ac9d32"
BASE = "ccd6d67b02968259b38f6a585e9d9366bcc5c3f0"
subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], check=True)
assets = [
    "apps/web/app/forma-workspace/chat-project-layout.tsx",
    "apps/web/app/forma-workspace/chat-project-layout.module.css",
    "apps/web/lib/chat-project-layout.ts",
    "apps/web/test/chat-project-layout.test.ts",
    "apps/web/e2e/chat-project-workspace.spec.mjs",
    "apps/web/playwright.workspace.config.mjs",
    "apps/web/test/fixtures/chat-project-workspace.tsx",
    "apps/web/test/fixtures/chat-project-workspace.css",
    "apps/web/test/serve-chat-project-fixture.mjs",
]
for name in assets:
    path = Path(name)
    assert not path.exists(), f"Refusing to overwrite {name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(subprocess.check_output(["git", "show", f"{SOURCE}:{name}"]))

def replace(text, old, new, count=1):
    assert text.count(old) == count, f"Expected {count} occurrences of {old[:100]!r}, got {text.count(old)}"
    return text.replace(old, new)

path = Path("apps/web/app/forma-workspace.tsx")
assert subprocess.check_output(["git", "hash-object", str(path)], text=True).strip() == "4552a19091e2f57c40d35dce658dce94d9421510"
s = path.read_text()
s = replace(s, 'import HomeChatView from "./forma-workspace/home-chat-view";', 'import HomeChatView from "./forma-workspace/home-chat-view";\nimport ChatProjectLayout, { ChatProjectSurface } from "./forma-workspace/chat-project-layout";')
s = replace(s, '              projectArtifact={', '              projectArtifactId={inlineChatProjectId}\n              projectArtifact={')
start = s.index("function ChatWorkspace(")
end = s.index("function scrollableVerticalParent(", start)
chat = s[start:end]
artifact_start = chat.index("                <ChatProjectArtifact")
artifact_end = chat.index("                />", artifact_start) + len("                />")
artifact = chat[artifact_start:artifact_end]
chat = chat[:artifact_start] + chat[artifact_end:]
chat = replace(chat, '  return (\n    <div className="relative flex h-full', '  return (\n    <ChatProjectLayout\n      conversationKey={chatId || projectId || "project-chat"}\n      projectId={projectId}\n      project={(chatAvailable || readOnly) && projectId ? (\n' + artifact + '\n      ) : null}\n    >\n    <div className="relative flex h-full')
chat = replace(chat, '    </div>\n  );\n}\n', '    </div>\n    </ChatProjectLayout>\n  );\n}\n')
s = s[:start] + chat + s[end:]
start = s.index("function scrollableVerticalParent(")
end = s.index("function ProjectWorkspacePanel(", start)
old = subprocess.check_output(["git", "show", f"{SOURCE}:apps/web/app/forma-workspace.tsx"], text=True)
new_surface = old[old.index("function ChatProjectArtifact("):old.index("function ProjectWorkspacePanel(")]
s = s[:start] + new_surface + s[end:]
s = replace(s, "  Maximize2,\n  Minimize2,\n", "")
path.write_text(s)

path = Path("apps/web/app/forma-workspace/home-chat-view.tsx")
s = path.read_text()
s = replace(s, 'import useChatAutoScroll from "./use-chat-auto-scroll";', 'import useChatAutoScroll from "./use-chat-auto-scroll";\nimport ChatProjectLayout from "./chat-project-layout";')
s = replace(s, "  projectArtifact?: ReactNode;", "  projectArtifact?: ReactNode;\n  projectArtifactId?: string | null;")
s = replace(s, "  projectArtifact,\n", "  projectArtifact,\n  projectArtifactId,\n")
s = replace(s, "  return (\n    <section", '  return (\n    <ChatProjectLayout conversationKey={conversationKey} projectId={projectArtifactId} project={started ? projectArtifact : null}>\n    <section')
s = replace(s, "            {projectArtifact}\n", "")
s = replace(s, "    </section>\n  );", "    </section>\n    </ChatProjectLayout>\n  );")
form_start = s.index('            className={`${\n            started')
form_end = s.index("\n          >", form_start)
s = s[:form_start] + '''            className={started
              ? "relative z-20 max-h-[50dvh] shrink-0 overflow-y-auto overscroll-contain border-t border-[var(--forma-border)] bg-[var(--forma-page)] px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-4"
              : "fixed bottom-0 left-0 right-0 z-30 max-h-[calc(100dvh-3rem)] shrink-0 overflow-y-auto overscroll-contain bg-transparent px-3 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1 sm:px-4 md:static md:order-1 md:left-auto md:right-auto md:z-20 md:max-h-none md:overflow-visible md:bg-transparent md:p-0"}''' + s[form_end:]
path.write_text(s)

path = Path("apps/web/app/forma-workspace/conversation-message-list.tsx")
s = path.read_text()
s = replace(s, 'import CopyButton from "../../components/copy-button";', 'import CopyButton from "../../components/copy-button";\nimport { ProjectUpdateCard } from "./chat-project-layout";')
s = replace(s, "          {showPipeline && renderPipelineProgress(message)}", "          {showPipeline && renderPipelineProgress(message)}\n          <ProjectUpdateCard message={message} />")
path.write_text(s)

# Cancel browser-side file reads and prevent later import/mesh stages after teardown.
# The SDK's getMesh/importCadFile calls do not expose cancellation here; guard their results.
path = Path("apps/web/app/forma-workspace/cad-model-panel.tsx")
s = path.read_text()
s = replace(s, "    let cancelled = false;", "    let cancelled = false;\n    const controller = new AbortController();")
s = replace(s, '        const { OpenCadApiClient } = await import("opencad-viewport");', '        const { OpenCadApiClient } = await import("opencad-viewport");\n        if (cancelled) return;')
s = replace(s, "await loadFileMesh(api, descriptor.url, descriptor.filename);", "await loadFileMesh(api, descriptor.url, descriptor.filename, controller.signal);")
s = replace(s, "      cancelled = true;", "      cancelled = true;\n      controller.abort();")
s = replace(s, "  filename: string,\n): Promise<MeshPayload> {\n  const response = await fetch(url);", "  filename: string,\n  signal: AbortSignal,\n): Promise<MeshPayload> {\n  const response = await fetch(url, { signal });")
s = replace(s, "  const blob = await response.blob();\n  const file", "  const blob = await response.blob();\n  signal.throwIfAborted();\n  const file")
s = replace(s, "  return api.getMesh(imported.shape_id);", "  signal.throwIfAborted();\n  return api.getMesh(imported.shape_id);")
path.write_text(s)

# Browser tests must await the ResizeObserver/effect-driven mount after each chat switch.
path = Path("apps/web/e2e/chat-project-workspace.spec.mjs")
s = path.read_text()
s = replace(s, '    await page.getByRole("button", { name: "Controller chat" }).click();\n', '    await page.getByRole("button", { name: "Controller chat" }).click();\n    await expect(page.getByTestId("model-canvas")).toHaveAttribute("aria-label", "Model for controller");\n    await expect.poll(async () => (await stats(page)).live).toBe(1);\n')
s = replace(s, '  expect((await stats(page)).live).toBe(1);', '  await expect.poll(async () => (await stats(page)).live).toBe(1);')
path.write_text(s)

Path("apps/web/test/chat-project-integration.test.ts").write_text('''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const workspace = readFileSync(new URL("../app/forma-workspace.tsx", import.meta.url), "utf8");
const home = readFileSync(new URL("../app/forma-workspace/home-chat-view.tsx", import.meta.url), "utf8");
const messages = readFileSync(new URL("../app/forma-workspace/conversation-message-list.tsx", import.meta.url), "utf8");
const cad = readFileSync(new URL("../app/forma-workspace/cad-model-panel.tsx", import.meta.url), "utf8");
const chat = workspace.slice(workspace.indexOf("function ChatWorkspace("), workspace.indexOf("function ChatProjectArtifact("));
const surface = workspace.slice(workspace.indexOf("function ChatProjectArtifact("), workspace.indexOf("function ProjectWorkspacePanel("));

test("main project chat moves exactly one artifact outside the conversation scroller", () => {
  assert.match(chat, /<ChatProjectLayout/);
  assert.ok(chat.includes("project={(chatAvailable || readOnly) && projectId ? ("));
  assert.equal((chat.match(/<ChatProjectArtifact\\b/g) || []).length, 1);
  assert.ok(chat.indexOf("<ChatProjectArtifact") < chat.indexOf("ref={containerRef}"));
  assert.match(chat, /<ConversationMessageList/);
});
test("main home chat uses the same workspace without an inline artifact", () => {
  assert.ok(home.includes("project={started ? projectArtifact : null}"));
  assert.doesNotMatch(home, /^\\s*\\{projectArtifact\\}\\s*$/m);
  assert.match(home, /<ConversationMessageList/);
  assert.ok(workspace.includes("projectArtifactId={inlineChatProjectId}"));
});
test("both main chat entry points share the lightweight message card renderer", () => {
  assert.ok(messages.includes("<ProjectUpdateCard message={message} />"));
  assert.doesNotMatch(messages, /<ChatProjectArtifact|<CadModelPanel|<OpenCadViewport/);
});
test("surface preserves project tabs without the old fixed-height inline card", () => {
  assert.match(surface, /<ChatProjectSurface/);
  assert.match(surface, /<ProjectWorkspacePanel/);
  assert.doesNotMatch(surface, /70dvh|min-h-\\[540px\\]|setFullScreen|scrollableVerticalParent/);
});
test("main authoring, read-only, submit, stop and retry behavior remains wired", () => {
  assert.ok(chat.includes("onSubmit={onSubmit}"));
  assert.ok(chat.includes("onClick={canStop ? onStop : retryMode ? onRetryFailedBuild : undefined}"));
  assert.ok(chat.includes('assistantLabel={authoringActive ? "OpenCode" : "Forma"}'));
  assert.ok(chat.includes("canEdit={chatAvailable && Boolean(onRenameTitle)}"));
  assert.ok(chat.includes("!chatAvailable && !readOnly"));
  assert.match(home, /className=\\{started\\s*\\? "relative/);
  assert.ok(home.includes("onSubmit={onSubmit}"));
});
test("CAD teardown cancels browser downloads and guards non-cancellable SDK work", () => {
  assert.match(cad, /controller\\.abort\\(\\)/);
  assert.ok(cad.includes("fetch(url, { signal })"));
  assert.equal((cad.match(/signal\\.throwIfAborted\\(\\)/g) || []).length, 2);
  assert.ok(cad.includes("if (cancelled) return;"));
});
''')

Path("docs/chat-project-workspace.md").write_text('''# Shared chat project workspace

The UI is based on `main`, including the OpenCode chat flow, reusable ConversationMessageList, read-only handling and gallery performance changes. No dev-only changes are included.

## Interaction

On wide containers, the conversation and current project use independent, resizable panes. On narrow containers, Chat / Project controls switch the visible pane while preserving the composer draft. Full screen expands the same project subtree; Escape returns to the prior view. The project remains available without scrolling to the end of the chat.

Completed assistant messages render lightweight project-reference cards. Current-project cards open the shared pane. Cards referencing another project use its existing authorized project route. They explicitly say "Latest saved state · not a historical snapshot": this PR does not invent immutable revision pointers for old messages.

## Resource lifecycle

Only one project subtree is mounted per active conversation. Closing the pane or switching to Chat on a narrow screen unmounts it; switching conversations replaces the previous session. Full-screen presentation does not duplicate or remount the viewer. Existing tab selection mounts only the active tab. Cards contain IDs and text, never mesh copies or a viewer.

CAD file fetches use an AbortController and cleanup aborts them. Non-cancellable SDK import/mesh calls are guarded so a stale result cannot update the panel or start the next import stage. Parent-held project payloads and SDK-owned GPU disposal are not claimed to have been eliminated or benchmarked.

## Tests

Run the focused state/source tests with Node 22: `node --experimental-strip-types --test test/chat-project-layout.test.ts test/chat-project-integration.test.ts` from apps/web. Run the Chromium layout suite with `npx playwright test --config playwright.workspace.config.mjs`. The browser fixture imports the production layout and uses an instrumented stand-in viewer to check active instance counts, not real CAD GPU memory.

The read-only pull-request workflow targets main and runs full frontend typechecking plus the focused tests. No generated patch or integration helper is needed to build this UI.
''')
subprocess.run(["git", "diff", "--check"], check=True)
print("Integrated shared workspace directly into main's chat components.")
