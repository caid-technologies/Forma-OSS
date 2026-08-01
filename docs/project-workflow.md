# Project workflow state machine

Forma keeps conversational and build lifecycle state separate from generated-project deletion status. `ProjectWorkflowService` is the single authority for validating transitions, while the persistence repository atomically updates the current state and appends an immutable transition record.

## States and transitions

```text
gathering_context -> ready_to_build | building | cancelled | failed
ready_to_build    -> gathering_context | building | cancelled | failed
building          -> awaiting_feedback | cancelled | failed
awaiting_feedback -> gathering_context | building | completed | cancelled | failed
failed            -> gathering_context | ready_to_build | building | cancelled
completed         -> terminal
cancelled         -> terminal
```

The direct `gathering_context -> building` transition supports the later **Build anyway** action. A transition to the current state is a no-op. Repeated commands with the same project-scoped `idempotency_key` return the original transition without appending history.

Each transition records:

- project and owner identifiers;
- prior and resulting states;
- monotonically increasing workflow revision;
- user or system actor and optional actor identifier;
- reason, timestamp, and optional idempotency key.

## API

Authenticated, owner-scoped routes are:

- `POST /projects/{project_id}/workflow` — idempotently initialize `gathering_context`.
- `GET /projects/{project_id}/workflow` — return current state.
- `GET /projects/{project_id}/workflow/transitions` — return current state and ordered history.
- `POST /projects/{project_id}/workflow/transitions` — request a validated transition.

Invalid transitions return HTTP 409 with code `invalid_workflow_transition` and the allowed target states. Optimistic concurrency conflicts use `workflow_transition_conflict`; inaccessible workflows use the non-enumerating `workflow_not_found` response.

## Persistence

SQLite performs the state update and history insert in one SQLAlchemy transaction. Supabase uses the `apply_project_workflow_transition` database function so the same operation remains atomic through PostgREST. Browser roles cannot access either workflow table directly.
