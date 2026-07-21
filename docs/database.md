# Database

Forma stores component templates and generated projects in Supabase when configured, with a **SQLite fallback** for local development.

Database selection is configured in `backend/database.py`:
- Supabase mode uses the Supabase Python client with `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`.
- Backend Supabase writes require a server-side service/secret key; anon and publishable keys obey RLS and will fail to seed/write by default.
- Raw Postgres connection strings are intentionally ignored by the app database layer.
- With no Supabase client configuration, the backend falls back to `SQLITE_DATABASE_URL` or `sqlite:///./blueprint.db`.
- Set `DATABASE_BACKEND=sqlite` to force SQLite, or `DATABASE_BACKEND=supabase` to require Supabase client configuration.
- Set `BLUEPRINT_DEV_MODE=true` to force SQLite when Supabase credentials point at a remote project. For local Supabase testing, `DATABASE_BACKEND=supabase` is honored when `SUPABASE_URL` points at localhost/127.0.0.1. Dev mode still forces A2A job metadata to SQLite and disables Supabase Storage writes; uploaded/generated image data remains inline in the stored Hardware IR.

## Storage model
Database models are defined in `backend/database.py`:

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
- `owner_user_id` (optional Clerk user id that owns mutation rights)
- `visibility` (`public` by default; public project reads are allowed through the API)
- `title`
- `prompt`
- `hardware_ir` (JSON representation of the IR)
- `created_at`

`hardware_ir.assembly_metadata.project_id` must match `generated_projects.project_id`. Supabase Storage image keys are written under `images/<project_id>/...` so the DB row, route id, IR metadata, and object path share the same UUID.

Projects are public artifacts: `GET /api/projects` and `GET /api/projects/{project_id}` do not require the project owner. Mutating a project, deleting it, or saving derived artifacts requires the signed-in Clerk user to match `owner_user_id` when deployed auth is enabled.

### project_chats
Private chat threads owned by a Clerk user.
- `chat_id` (unique)
- `owner_user_id` (Clerk user id; required)
- `title`
- `messages` (JSON array)
- `created_at`
- `updated_at`

Chats are not publicly readable. Sharing is intentionally deferred to a future sharing/ACL table.

### user_integration_configs
Encrypted per-user BYOK/provider settings.
- `owner_user_id` (Clerk user id; primary key)
- `encrypted_config` (Fernet-encrypted `UserIntegrationConfig` JSON)
- `encryption_key_id` (non-secret fingerprint of the server key used for operations/debugging)
- `version`
- `created_at`
- `updated_at`

The backend decrypts this table only server-side using `BLUEPRINT_USER_SECRETS_KEY`. The table has RLS enabled, anon/authenticated grants revoked, and service-role-only access. Do not add plaintext API key columns to this table.

### a2a_jobs
A2A job metadata follows `JOB_METADATA_BACKEND`:
- `auto` stores A2A jobs in Supabase when the main app database is Supabase, otherwise in SQLite.
- `sqlite` forces the Python stdlib `sqlite3` store.
- `BLUEPRINT_DEV_MODE=true` overrides this setting and uses SQLite for remote Supabase URLs. Local Supabase URLs are allowed so developers can test the Supabase backend locally.
- SQLite path default: `./blueprint_jobs.db`
- SQLite path override: `JOB_METADATA_DB_PATH`
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
