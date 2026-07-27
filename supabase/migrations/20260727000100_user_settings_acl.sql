-- Keep per-user data-usage preferences server-owned. The backend resolves the
-- authenticated owner id and accesses this table with the service role.

alter table public.user_settings enable row level security;

revoke all on table public.user_settings from anon;
revoke all on table public.user_settings from authenticated;

grant select, insert, update, delete on table public.user_settings to service_role;
grant usage, select on sequence public.user_settings_id_seq to service_role;
