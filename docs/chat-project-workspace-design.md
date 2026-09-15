# Shared chat project workspace

Status: **design proposal; implementation and runtime validation pending**.

This change documents the proposed interaction and acceptance criteria. It does
not change the chat UI, introduce revision endpoints, or claim a memory reduction.

## Problem and inspection baseline

The observed chat interface places the complete project component after the
conversation. It competes with the message history for scrolling space and makes
project changes difficult to associate with the messages that produced them.

The source inspection for this proposal used commit
`4c3e1e9626f3621785247de08e521b60294f0e94`:

- `apps/web/app/forma-workspace.tsx`: `ChatWorkspace` places
  `ChatProjectArtifact` after the message list and its scroll anchor.
- `apps/web/app/forma-workspace/conversation-message-list.tsx`: message rendering.
- `apps/web/app/forma-workspace/cad-model-panel.tsx`: dynamically loaded viewport,
  mesh loading, and a cancellation flag that suppresses stale state updates but
  does not abort the underlying file fetch.

The feature PR targets `dev` as required by `CONTRIBUTING.md`. That branch has
diverged from the inspected baseline and does not yet contain all of these
components. Reconcile the necessary frontend prerequisites before implementing;
do not import unrelated `main` history into this feature PR.

## Interaction

### Conversation

Keep a compact project-update card under the assistant response that successfully
produced a saved revision. A card contains a project reference, revision reference,
short change summary, affected sections, and an optional thumbnail reference.
Streaming progress remains part of the in-progress message; it does not create
project snapshots or additional viewer instances.

Example, illustrative rather than an existing revision:

> USB Game Controller · Revision 12
>
> Updated the rear shell and trigger clearance.
>
> Changed: CAD, Mechanical
>
> View CAD · View changes

A historical card must open the exact referenced revision. Where a legacy message
has no revision identity, label its action **Open latest project**. Never label a
link as a historical revision when it actually resolves to the current project.

### Workspace

On desktop, use one resizable workspace pane alongside the conversation. Keep the
existing project-section navigation inside that pane. The chat and project content
scroll independently; the composer stays attached to the chat column.

On narrow screens, offer a Chat / Project switch. Full-screen mode changes the
presentation of the same workspace rather than mounting another desktop, mobile,
or modal copy. Closing the project view releases heavyweight content rather than
merely hiding it with CSS.

Retain small restoration state outside the heavyweight panel: active tab, selected
revision, camera transform, and compatible part selection. Scope that state to the
project/chat identity and bound its storage. Do not cache mounted component trees.

Provide keyboard-accessible pane controls, visible focus states, suitable minimum
pane widths, and focus restoration when returning to chat. Full-screen mode must
support Escape. Preserve chat scroll position and any unsent draft.

## Data boundaries

Messages reference artifacts; they do not own them. Proposed frontend attachment:

```ts
export type ProjectUpdateReference = {
  projectId: string;
  revisionId: string;
  summary: string;
  changedSections: string[];
  thumbnailUrl?: string;
};
```

Do not put project JSON, STEP bytes, mesh arrays, textures, or base64 previews into
chat messages. Resolve references through the authorized project/revision data
layer. Persist the exact revision returned by the completed operation, not a later
lookup of whichever revision happens to be latest.

Use durable canonical revision storage rather than a parallel browser-side
snapshot system. Verify the available read contracts and authorization on `dev`
before introducing new endpoints. The message contract, persistence adapters,
legacy hydration, and pagination all need to preserve the reference consistently.

Fetch metadata-only revision lists and load selected revision content on demand.
Reuse references to unchanged artifacts. Loading metadata must not eagerly load
all revision meshes. Cache keys must include authorization scope, project identity,
revision identity, and artifact identity where applicable; clear private caches on
sign-out or identity change.

## Update and navigation behavior

- **Generating:** keep the last successful model visible with an updating status.
  A failed or cancelled generation must not replace it with an incomplete model.
- **Following Latest:** advance only after a successful revision is committed.
  Ordinary streaming events must not reload the CAD model.
- **Inspecting history:** keep the selected revision fixed and display a newer-
  revision notification when appropriate. Inspecting a historical revision is
  read-only; using it as an edit base requires an explicit operation.
- **Switching chats:** save small UI state, detach the outgoing view, and load the
  incoming selection in the shared workspace. Background job status is independent
  of whether its heavyweight viewer is mounted.

Use selection/request identities to reject stale responses. An outgoing chat's
late model load must never appear in the incoming chat. Abort fetches where the
client API supports `AbortSignal`, and retain stale-result guards for import or
kernel work that cannot be aborted. A client-side abort does not imply that a
server-side generation or import was cancelled.

## Memory and rendering policy

Start with one active heavyweight project tab and no inactive decoded-model cache.
Keep inactive tabs unmounted. Dynamic imports defer code loading; they are not a
substitute for instance lifecycle management.

Separate three kinds of resource ownership:

1. Durable project and revision data lives on the backend.
2. Small UI restoration state lives in a bounded client store.
3. Mesh buffers, textures, workers, and rendering resources belong to the active
   viewer or an explicitly owned shared resource manager.

On replacement or teardown, verify the viewport package's supported cleanup
behavior. Release resources owned by the outgoing model, stop obsolete rendering
work and listeners, revoke owned object URLs, and drop client references to its
large buffers. Do not dispose resources that another live owner still uses.
Unmounting React alone is not proof that GPU resources have been released.

Reuse rendering infrastructure across model changes when the viewport supports
that lifecycle. For large models, permit a loading placeholder while releasing the
old model before preparing its replacement; avoid requiring two fully decoded
models at once. Pausing rendering reduces active work but does not itself release
retained geometry or textures.

Add an inactive model cache only after profiling establishes a need. Any such cache
must have a byte budget, eviction, authorization scoping, and explicit cleanup.
Virtualize or paginate long message/revision lists independently; virtualizing the
DOM does not bound an otherwise unbounded data or mesh cache.

## Implementation sequence

1. Reconcile the frontend prerequisites with `dev`; extract the workspace layout
   from the large chat module without changing generation or permission behavior.
2. Move project content outside the message scroller. Add desktop split mode,
   narrow-screen switching, and full-screen presentation with a single active view.
3. Add honest lightweight project links first, then revision-specific cards only
   when exact revision references survive the complete persistence/read path.
4. Add scoped UI restoration state, load cancellation, stale-response isolation,
   and verified heavyweight-resource cleanup.
5. Add regression tests, perform browser profiling, and record measured results
   before marking the implementation ready for review.

## Acceptance checklist

All items are pending; this document does not represent completed tests.

- [ ] No complete project workspace is appended beneath the conversation.
- [ ] At most one heavyweight project view is mounted across responsive and
      full-screen modes; hiding/closing the project releases that content.
- [ ] Project controls do not move the chat scroll position or discard the draft.
- [ ] Historical cards resolve exact saved revisions; legacy links explicitly
      identify themselves as links to the latest project.
- [ ] New revisions advance Latest but do not replace a pinned historical view.
- [ ] Failed/cancelled work does not create a successful revision card.
- [ ] Switching chats during an in-flight load cannot display stale project data.
- [ ] Unchanged CAD artifacts are not reloaded on ordinary chat streaming events.
- [ ] Keyboard navigation, Escape, focus restoration, and narrow-screen layout work.
- [ ] Public/read-only project access and authorization checks remain intact.
- [ ] Relevant unit and browser tests pass; type checking and lint results are
      recorded, including any pre-existing failures.
- [ ] Repeated chat, tab, and revision switching is profiled with small and large
      representative models. After loads settle and cleanup runs, retained model
      resources do not grow monotonically with the number of switches.

Record browser/device, model sizes, iteration count, retained heap/resource counts,
and transient peaks. Do not promise a fixed RAM saving before measurement.
