-- Immutable, versioned DesignBrief snapshots used as the canonical handoff
-- between conversation context and downstream planning/execution.

create table if not exists public.design_briefs (
  id text primary key,
  design_brief_id text not null,
  project_id text not null,
  conversation_id text not null,
  owner_user_id text not null,
  brief_version integer not null check (brief_version >= 1),
  schema_version text not null,
  previous_version integer check (previous_version is null or previous_version >= 1),
  payload_json jsonb not null,
  created_at text not null,
  constraint design_briefs_project_version_unique unique (project_id, brief_version)
);

create index if not exists idx_design_briefs_stable_id_version
  on public.design_briefs (design_brief_id, brief_version desc);

create index if not exists idx_design_briefs_owner_project_version
  on public.design_briefs (owner_user_id, project_id, brief_version desc);

create index if not exists idx_design_briefs_conversation
  on public.design_briefs (conversation_id);

alter table public.design_briefs enable row level security;

revoke all on table public.design_briefs from anon, authenticated;
grant select, insert, delete on table public.design_briefs to service_role;

comment on table public.design_briefs is
  'Append-only DesignBrief snapshots. API updates insert a new brief_version; existing payloads are immutable.';

comment on column public.design_briefs.schema_version is
  'Version of the DesignBrief payload contract, independent of the snapshot brief_version.';
