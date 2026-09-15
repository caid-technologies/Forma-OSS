# Shared chat project workspace

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
