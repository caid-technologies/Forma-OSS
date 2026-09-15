# Shared chat project workspace

## Implemented UI

The project workspace is no longer appended to the conversation. Both existing
entry points, `ChatWorkspace` in `apps/web/app/forma-workspace.tsx` and
`HomeChatView`, now use `chat-project-layout.tsx`.

On containers at least 960 pixels wide, chat and project occupy independent panes
with a draggable, keyboard-operable divider. On narrower containers, Chat and
Project controls select the visible view. Closing the project removes its viewer
subtree; it is not merely hidden with CSS. The chat remains mounted while a
narrow-screen project is open so an unsent composer draft is preserved.

Completed assistant messages carry lightweight project-reference cards. Clicking
a card for the active project opens the shared pane. A link to a different project
navigates to that project's existing authorized route instead of silently displaying
the currently selected project.

Full screen changes the presentation of the same project subtree, not a second
instance. Escape exits full screen, focus is contained in the dialog, background
content is inert during the dialog, and focus/scroll-lock cleanup runs on exit.
The existing project namespace tabs, ownership checks, submit handlers, and stop
handlers are retained. The started home-chat composer is in normal layout flow so
it cannot cover the narrow-screen Project view.

## Resource-lifetime contract

- There is one conditional project slot per active chat layout.
- Changing conversation identity replaces the previous session subtree. There is
  no hidden viewer per chat and no unbounded map of mounted projects.
- Changing project identity replaces the previous project subtree. Ordinary
  message updates and full-screen changes do not key the viewer by message count.
- Existing active-tab-only rendering remains in place.
- Layout state contains four primitives; cards contain project references, not
  copied project JSON, model buffers, STEP files, or renderers.
- Unmounting allows the underlying viewer's existing cleanup to run. This is not
  a claim that all raw project payloads are evicted from the parent state, nor a
  measured GPU/RAM reduction. Reopening a closed viewer may rebuild it.

## Historical revisions are a separate follow-up

The current message contract supplies `projectId`, not a reliably persisted exact
revision pointer with an authorized historical-read path. Cards therefore say
**Latest saved state — not a historical snapshot**. This implementation does not
fabricate revision numbers or present today's model as the result of an old turn.

A subsequent revision-history feature should persist the exact revision ID from
each completed operation, fetch historical artifacts on demand, expose explicit
Latest versus historical selection, and keep historical inspection read-only until
an explicit restore or branch action. Per-artifact loading cancellation, retained
camera snapshots on close, and byte-bounded model caches can be added separately
when supported by the viewer/data contracts and validated by profiling.

## Validation

Run the state and real-entry-point regression tests from `apps/web`:

```sh
node --experimental-strip-types --test test/chat-project-layout.test.ts test/chat-project-integration.test.ts
```

Browser tests bundle the actual shared layout and card components with an
instrumented stand-in viewer. This fixture is not a production route and does not
contact authoring/model APIs. It checks desktop/mobile layout, message updates,
viewer mount/unmount counts during repeated chat switching, full-screen identity,
focus containment, draft retention, tab lifetimes, and keyboard resizing.

```sh
npm ci --legacy-peer-deps
npm install --no-save --package-lock=false --legacy-peer-deps @playwright/test@1.63.0 esbuild@0.25.12
npx playwright install chromium
npx playwright test --config playwright.workspace.config.mjs
```

The read-only `Chat project workspace UI` workflow also attempts a full frontend
typecheck and publishes browser reports/screenshots. See the PR checks for actual
results. Component-lifetime assertions are not a real CAD GPU-memory benchmark;
production authoring, hardware rendering, and memory profiling remain additional
integration checks. No deployment or merge is performed by this change.
