# Database

Forma stores component templates and generated projects in Supabase when configured, with a **SQLite fallback** for local development.

Database selection is composed in `blueprint_core/database.py`. Provider lifecycle and backend-specific behavior live under `blueprint_core/persistence/providers/`, while application repositories live under `blueprint_core/persistence/repositories/`:
- Supabase mode uses the Supabase Python client with `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`.
- Backend Supabase writes require a server-side service/secret key; anon and publishable keys obey RLS and will fail to seed/write by default.
- Raw Postgres connection strings are intentionally ignored by the app database layer.
- With no Supabase client configuration, the backend falls back to `SQLITE_DATABASE_URL` or `sqlite:///./blueprint.db`.
- Set `DATABASE_BACKEND=sqlite` to force SQLite, or `DATABASE_BACKEND=supabase` to require Supabase client configuration.
- Image storage and workspace/user integration stores follow the selected primary backend. In SQLite mode, merely having Supabase credentials in the environment does not enable remote ancillary stores. Use `BLUEPRINT_IMAGE_STORAGE_BACKEND=supabase`, `BLUEPRINT_WORKSPACE_INTEGRATIONS_BACKEND=supabase`, or `BLUEPRINT_USER_INTEGRATIONS_BACKEND=supabase` only as explicit overrides.
- Set `BLUEPRINT_DEV_MODE=true` to force SQLite when Supabase credentials point at a remote project. For local Supabase testing, `DATABASE_BACKEND=supabase` is honored when `SUPABASE_URL` points at localhost/127.0.0.1. Dev mode disables Supabase Storage writes; uploaded/generated image data remains inline in the stored Hardware IR.

The provider is selected once during application composition. Domain-facing database functions delegate to that provider's repository adapter; they do not select a backend per operation. SQLite creates and upgrades the shared local schema, while Supabase expects deployment migrations to be applied before startup. Both providers validate the complete application schema contract and fail startup when a required table or column is missing.

There is one physical application database per deployment. Passing an explicit path to `JobMetadataStore` creates a standalone SQLite provider only for isolated tests and the `jobs --local --db-path` inspection command; normal application code always uses the primary provider.

## Storage model
Shared database models are defined in `blueprint_core/persistence/models.py`:

### component_templates
Seed component library used by the Component Selection Agent.
- `part_number` (unique)
- `name`
- `category`
- `description`
- `price`
- `sourcing_url`
- `pins` (JSON list of `PinDefinition`)
- `use_cases` (JSON list of strings)

### generated_projects
Archived outputs from the pipeline.
- `project_id` (unique canonical UUID string; used directly in `/project/<uuid>` routes)
- `chat_id` (optional private chat/thread id that created the project)
- `owner_user_id` (provider-neutral internal user id that owns mutation rights)
- `visibility` (`public` by default; `private` projects are readable only by their owner)
- `title`
- `prompt`
- `hardware_ir` (JSON representation of the IR)
- `created_at`

`hardware_ir.assembly_metadata.project_id` must match `generated_projects.project_id`. Supabase Storage image keys are written under `images/<project_id>/...` so the DB row, route id, IR metadata, and object path share the same UUID.

`GET /api/projects` returns public artifacts only. `GET /api/projects/{project_id}` allows public projects or the owning identity; private non-owner reads return 404. Mutating, deleting, chatting with, or saving derived artifacts requires the request's provider-neutral user context to match `owner_user_id`.

### project_chats
Private chat threads owned by an authenticated user.
- `chat_id` (unique)
- `owner_user_id` (provider-neutral internal user id; required)
- `title`
- `messages` (JSON array)
- `created_at`
- `updated_at`

Chats are not publicly readable. Sharing is intentionally deferred to a future sharing/ACL table.

### user_integration_configs
Encrypted per-user BYOK/provider settings.
- `owner_user_id` (provider-neutral internal user id; primary key)
- `encrypted_config` (Fernet-encrypted `UserIntegrationConfig` JSON)
- `encryption_key_id` (non-secret fingerprint of the server key used for operations/debugging)
- `version`
- `created_at`
- `updated_at`

The backend decrypts this table only server-side using `BLUEPRINT_USER_SECRETS_KEY`. The table has RLS enabled, anon/authenticated grants revoked, and service-role-only access. Do not add plaintext API key columns to this table.

### workspace_integration_configs

Encrypted workspace-scoped provider settings used when `BLUEPRINT_AUTH_MODE=local`. Supabase-primary workspaces store Fernet ciphertext in this table; SQLite-primary runtimes use an encrypted file even if Supabase credentials are also present. The backend refuses to start without `BLUEPRINT_USER_SECRETS_KEY`, and `BLUEPRINT_WORKSPACE_SECRETS_KEY` can optionally isolate workspace encryption from per-user encryption.

### a2a_jobs
A2A jobs use the primary application database. SQLite stores this table alongside projects in `SQLITE_DATABASE_URL`, and Supabase stores it alongside the hosted application tables. During the transition, rows from `JOB_METADATA_DB_PATH` or `./blueprint_jobs.db` are imported idempotently into a file-backed primary SQLite database; the legacy file is retained.
- Stored data: job ids, sender/recipient/action, lifecycle status, timestamps, redacted payload metadata, `source_usage` metadata for Catalog/data warehouse vs Web Research/Firecrawl, compact result summaries, structured operation pass/fail metadata, image output status/error metadata, errors, and optional `error_debug` traces when `BLUEPRINT_DEBUG=true`

### alpha_signups
Alpha access leads captured when `BLUEPRINT_DEPLOYMENT=true` and live LLM generation is unavailable.
- `name`
- `email`
- `organization`
- `additional_info`
- `source`
- `metadata_json`
- `created_at`

## Seeding the database
Seed data is defined in `backend/seed_db.py`. Running:
```bash
python3 backend/seed_db.py
```
creates the initial component library (MCUs, sensors, displays, actuators, power parts).

On server startup, if the `component_templates` table is empty, the backend will also auto-seed the templates.

## Extensibility ideas
- Component metadata enrichment (availability, supply chain links)
- Versioned project history and diffing
- User accounts and shared project workspaces
- Parameterized footprints and PCB-ready libraries
