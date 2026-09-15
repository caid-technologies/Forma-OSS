import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const workspace = readFileSync(new URL("../app/forma-workspace.tsx", import.meta.url), "utf8");
const home = readFileSync(new URL("../app/forma-workspace/home-chat-view.tsx", import.meta.url), "utf8");
const chat = workspace.slice(workspace.indexOf("function ChatWorkspace("), workspace.indexOf("function ChatProjectArtifact("));
const surface = workspace.slice(workspace.indexOf("function ChatProjectArtifact("), workspace.indexOf("function ProjectWorkspacePanel("));

test("project chat puts its one artifact in the shared layout, before the message scroller", () => {
  assert.match(chat, /<ChatProjectLayout/);
  assert.match(chat, /project=\{canChat \? \(/);
  assert.equal((chat.match(/<ChatProjectArtifact\b/g) || []).length, 1);
  assert.ok(chat.indexOf("<ChatProjectArtifact") < chat.indexOf("ref={containerRef}"));
  assert.match(chat, /<ProjectUpdateCard message=\{message\}/);
});
test("home chat uses the same workspace and does not append an artifact to messages", () => {
  assert.match(home, /project=\{started \? projectArtifact : null\}/);
  assert.doesNotMatch(home, /^\s*\{projectArtifact\}\s*$/m);
  assert.match(home, /<ProjectUpdateCard message=\{message\}/);
  assert.match(workspace, /projectArtifactId=\{inlineChatProjectId\}/);
});
test("the shared surface replaces the old 70vh inline card and keeps existing project tabs", () => {
  assert.match(surface, /<ChatProjectSurface/);
  assert.match(surface, /<ProjectWorkspacePanel/);
  assert.doesNotMatch(surface, /70dvh|min-h-\[540px\]|setFullScreen|scrollableVerticalParent/);
});
test("chat submit and stop handlers remain connected; the started home composer is in normal flow", () => {
  assert.match(chat, /onSubmit=\{onSubmit\}/);
  assert.match(chat, /onClick=\{canStop \? onStop : undefined\}/);
  assert.match(home, /className=\{started\s*\? "relative/);
  assert.match(home, /onSubmit=\{onSubmit\}/);
});
test("home project controls clear the mobile chrome without the obsolete composer spacer", () => {
  assert.match(home, /className=\{layoutStyles.home\} data-project=/);
  assert.doesNotMatch(home, /h-40 shrink-0 md:hidden/);
});
