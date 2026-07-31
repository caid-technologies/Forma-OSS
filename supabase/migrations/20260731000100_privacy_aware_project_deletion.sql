-- Privacy-aware project deletion, consent, sanitized contribution snapshots,
-- and content-free lifecycle audit records.

alter table public.generated_projects
  add column if not exists status text not null default 'active',
  add column if not exists deleted_at text,
  add column if not exists deletion_requested_by text,
  add column if not exists purge_after text,
  add column if not exists purge_started_at text,
  add column if not exists purge_completed_at text,
  add column if not exists deletion_error text;

alter table public.generated_projects
  drop constraint if exists generated_projects_status_valid;

alter table public.generated_projects
  add constraint generated_projects_status_valid
  check (status in ('active', 'deletion_pending', 'purging', 'purged', 'deletion_failed'));

create index if not exists idx_generated_projects_status
  on public.generated_projects (status);

create index if not exists idx_generated_projects_purge_after
  on public.generated_projects (purge_after)
  where purge_after is not null;

create table if not exists public.project_contribution_consents (
  id text primary key,
  project_id text not null,
  user_id text not null,
  workspace_id text,
  consent_version text not null,
  permitted_purposes jsonb not null default '[]'::jsonb,
  granted_at text not null,
  withdrawn_at text,
  snapshot_created_at text,
  sanitized_at text,
  anonymized_at text,
  purged_at text
);

create unique index if not exists ux_project_contribution_consents_project_user
  on public.project_contribution_consents (project_id, user_id);

create index if not exists idx_project_contribution_consents_user
  on public.project_contribution_consents (user_id);

create table if not exists public.project_contribution_snapshots (
  id text primary key,
  source_project_id text not null,
  consent_record_id text not null,
  sanitization_version text not null,
  contribution_status text not null,
  payload_json jsonb not null,
  created_at text not null,
  sanitized_at text,
  anonymized_at text,
  purged_at text
);

create unique index if not exists ux_project_contribution_snapshots_consent
  on public.project_contribution_snapshots (consent_record_id);

create index if not exists idx_project_contribution_snapshots_source_project
  on public.project_contribution_snapshots (source_project_id);

create table if not exists public.project_deletion_audit (
  id text primary key,
  project_id text not null,
  acting_user_id text,
  action text not null,
  status text not null,
  policy_version text not null,
  details_json jsonb not null default '{}'::jsonb,
  created_at text not null
);

create index if not exists idx_project_deletion_audit_project_created
  on public.project_deletion_audit (project_id, created_at desc);

create index if not exists idx_project_deletion_audit_actor_created
  on public.project_deletion_audit (acting_user_id, created_at desc);

alter table public.project_contribution_consents enable row level security;
alter table public.project_contribution_snapshots enable row level security;
alter table public.project_deletion_audit enable row level security;

revoke all on table public.project_contribution_consents from anon, authenticated;
revoke all on table public.project_contribution_snapshots from anon, authenticated;
revoke all on table public.project_deletion_audit from anon, authenticated;

grant select, insert, update, delete on table public.project_contribution_consents to service_role;
grant select, insert, update, delete on table public.project_contribution_snapshots to service_role;
grant select, insert, update, delete on table public.project_deletion_audit to service_role;

comment on table public.project_contribution_consents is
  'Purpose-specific, versioned project contribution consent retained for audit.';

comment on table public.project_contribution_snapshots is
  'Separately stored sanitized contribution data; never an operational project copy.';

comment on table public.project_deletion_audit is
  'Project deletion and contribution lifecycle events without project content.';
