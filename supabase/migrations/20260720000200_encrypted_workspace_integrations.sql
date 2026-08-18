-- Encrypted workspace-level provider defaults and server-owned integration settings.
--
-- Per-user BYOK remains in user_integration_configs. This table is for global
-- defaults such as provider/model allowlists and optional server-owned provider
-- credentials. The backend stores only encrypted config blobs here.

create table if not exists public.workspace_integration_configs (
  config_key text primary key default 'default',
  encrypted_config text not null,
  encryption_key_id text not null,
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at text not null
);

comment on table public.workspace_integration_configs is
  'Encrypted workspace-level provider defaults and server-owned integration settings. API keys must not be stored in plaintext columns.';

comment on column public.workspace_integration_configs.encrypted_config is
  'Fernet-encrypted UserIntegrationConfig JSON. Requires server-only BLUEPRINT_USER_SECRETS_KEY to decrypt.';

alter table public.workspace_integration_configs enable row level security;

revoke all on table public.workspace_integration_configs from anon;
revoke all on table public.workspace_integration_configs from authenticated;

grant select, insert, update, delete on table public.workspace_integration_configs to service_role;
