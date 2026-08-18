-- Encrypted per-user BYOK/provider settings.
--
-- The backend stores only encrypted config blobs here. Decryption requires the
-- server-only BLUEPRINT_USER_SECRETS_KEY and never happens in browser clients.

create table if not exists public.user_integration_configs (
  owner_user_id text primary key,
  encrypted_config text not null,
  encryption_key_id text not null,
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at text not null
);

comment on table public.user_integration_configs is
  'Encrypted BYOK/provider settings keyed by Clerk owner_user_id. API keys must not be stored in plaintext columns.';

comment on column public.user_integration_configs.encrypted_config is
  'Fernet-encrypted UserIntegrationConfig JSON. Requires server-only BLUEPRINT_USER_SECRETS_KEY to decrypt.';

alter table public.user_integration_configs enable row level security;

revoke all on table public.user_integration_configs from anon;
revoke all on table public.user_integration_configs from authenticated;

grant select, insert, update, delete on table public.user_integration_configs to service_role;
