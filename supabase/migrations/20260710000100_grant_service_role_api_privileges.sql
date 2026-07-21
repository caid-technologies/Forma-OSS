-- Supabase CLI 2.106+ no longer auto-exposes newly-created public tables to API
-- roles by default. Forma's backend uses the server-side service role through
-- supabase-py, so grant that role access to the tables and identity sequences.

grant usage on schema public to service_role;

grant select, insert, update, delete
  on all tables in schema public
  to service_role;

grant usage, select
  on all sequences in schema public
  to service_role;

alter default privileges in schema public
  grant select, insert, update, delete
  on tables
  to service_role;

alter default privileges in schema public
  grant usage, select
  on sequences
  to service_role;
