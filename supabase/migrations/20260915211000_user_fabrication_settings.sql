-- Account-scoped printer preferences, independent of privacy/provider settings.
-- Apply before deploying the backend; SQLite creates this table at startup.
create table if not exists public.user_fabrication_settings (
  owner_user_id text primary key check (length(trim(owner_user_id)) > 0),
  printer_id text not null check (printer_id in ('creality_ender_3_04', 'bambu_a1_04')),
  updated_at text not null
);

alter table public.user_fabrication_settings enable row level security;
revoke all on table public.user_fabrication_settings from public, anon, authenticated;
grant select, insert, update, delete on table public.user_fabrication_settings to service_role;

comment on table public.user_fabrication_settings is
  'Server-owned per-account reviewed printer bundle. Owner resolved by authenticated API; no executable paths, secrets or raw G-code.';
