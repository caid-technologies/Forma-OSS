-- Immutable canonical project revisions shared by workers and workspace adapters.

create table if not exists public.project_revisions (
  id text primary key,
  project_id text not null,
  owner_user_id text not null,
  revision integer not null check (revision >= 1),
  parent_revision integer,
  design_brief_id text not null,
  design_brief_version integer not null check (design_brief_version >= 1),
  source_job_id text not null,
  payload_json jsonb not null,
  created_at text not null,
  constraint project_revisions_parent_valid check (
    (revision = 1 and parent_revision is null)
    or (revision > 1 and parent_revision = revision - 1)
  ),
  constraint project_revisions_project_revision_unique unique (project_id, revision),
  constraint project_revisions_project_source_job_unique unique (project_id, source_job_id)
);

create index if not exists idx_project_revisions_owner_project_revision
  on public.project_revisions (owner_user_id, project_id, revision desc);

create index if not exists idx_project_revisions_design_brief
  on public.project_revisions (design_brief_id, design_brief_version);

create or replace function public.insert_initial_project_revision(
  p_revision jsonb
) returns jsonb
language plpgsql
set search_path = public
as $$
declare
  saved_revision public.project_revisions%rowtype;
begin
  if (p_revision->>'revision')::integer <> 1
    or nullif(p_revision->>'parent_revision', '') is not null then
    return null;
  end if;

  perform 1
  from public.project_revisions
  where project_id = p_revision->>'project_id'
  for update;
  if found then
    return null;
  end if;

  insert into public.project_revisions (
    id, project_id, owner_user_id, revision, parent_revision, design_brief_id,
    design_brief_version, source_job_id, payload_json, created_at
  ) values (
    p_revision->>'id', p_revision->>'project_id', p_revision->>'owner_user_id',
    (p_revision->>'revision')::integer, null, p_revision->>'design_brief_id',
    (p_revision->>'design_brief_version')::integer, p_revision->>'source_job_id',
    p_revision->'payload_json', p_revision->>'created_at'
  ) returning * into saved_revision;

  return to_jsonb(saved_revision);
exception
  when unique_violation then
    return null;
end;
$$;

alter table public.project_revisions enable row level security;

revoke all on table public.project_revisions from anon, authenticated;
grant select, insert, delete on table public.project_revisions to service_role;

revoke all on function public.insert_initial_project_revision(jsonb) from public, anon, authenticated;
grant execute on function public.insert_initial_project_revision(jsonb) to service_role;

comment on table public.project_revisions is
  'Immutable canonical project state revisions tied to exact frozen DesignBrief and source worker job identities.';
