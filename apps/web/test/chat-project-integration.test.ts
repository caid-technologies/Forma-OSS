import assert from "node:assert/strict";
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
  assert.equal((chat.match(/<ChatProjectArtifact\b/g) || []).length, 1);
  assert.ok(chat.indexOf("<ChatProjectArtifact") < chat.indexOf("ref={containerRef}"));
  assert.match(chat, /<ConversationMessageList/);
});
test("main home chat uses the same workspace without an inline artifact", () => {
  assert.ok(home.includes("project={started ? projectArtifact : null}"));
  assert.doesNotMatch(home, /^\s*\{projectArtifact\}\s*$/m);
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
  assert.doesNotMatch(surface, /70dvh|min-h-\[540px\]|setFullScreen|scrollableVerticalParent/);
});
test("main authoring, read-only, submit, stop and retry behavior remains wired", () => {
  assert.ok(chat.includes("onSubmit={onSubmit}"));
  assert.ok(chat.includes("onClick={canStop ? onStop : retryMode ? onRetryFailedBuild : undefined}"));
  assert.ok(chat.includes('assistantLabel={authoringActive ? "OpenCode" : "Forma"}'));
  assert.ok(chat.includes("canEdit={chatAvailable && Boolean(onRenameTitle)}"));
  assert.ok(chat.includes("!chatAvailable && !readOnly"));
  assert.match(home, /className=\{started\s*\? "relative/);
  assert.ok(home.includes("onSubmit={onSubmit}"));
});
test("CAD teardown cancels browser downloads and guards non-cancellable SDK work", () => {
  assert.match(cad, /controller\.abort\(\)/);
  assert.ok(cad.includes("fetch(url, { signal })"));
  assert.equal((cad.match(/signal\.throwIfAborted\(\)/g) || []).length, 2);
  assert.ok(cad.includes("if (cancelled) return;"));
});
