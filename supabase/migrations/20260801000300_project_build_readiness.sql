-- Freeze DesignBrief inputs and atomically enter the building workflow state.

create table if not exists public.project_builds (
  id text primary key,
  project_id text not null,
  owner_user_id text not null,
  design_brief_id text not null,
  brief_version integer not null check (brief_version >= 1),
  brief_snapshot_json jsonb not null,
  mode text not null check (mode in ('build', 'build_anyway')),
  readiness_result_json jsonb not null,
  introduced_assumptions_json jsonb not null default '[]'::jsonb,
  warnings_json jsonb not null default '[]'::jsonb,
  transition_id text not null unique,
  idempotency_key text not null,
  initiated_by text not null,
  created_at text not null,
  constraint project_builds_project_idempotency_unique unique (project_id, idempotency_key)
);

create index if not exists idx_project_builds_owner_project_created
  on public.project_builds (owner_user_id, project_id, created_at desc);

create or replace function public.apply_project_build_initiation(
  p_state jsonb,
  p_transition jsonb,
  p_build jsonb,
  p_expected_state text,
  p_expected_revision integer
) returns jsonb
language plpgsql
set search_path = public
as $$
declare
  current_workflow public.project_workflows%rowtype;
  saved_workflow public.project_workflows%rowtype;
  saved_transition public.project_workflow_transitions%rowtype;
  saved_build public.project_builds%rowtype;
begin
  select * into current_workflow
  from public.project_workflows
  where project_id = p_state->>'project_id'
  for update;

  if not found
    or current_workflow.owner_user_id <> p_state->>'owner_user_id'
    or current_workflow.state <> p_expected_state
    or current_workflow.revision <> p_expected_revision then
    return null;
  end if;

  update public.project_workflows
  set state = p_state->>'state',
      revision = (p_state->>'revision')::integer,
      updated_at = p_state->>'updated_at'
  where project_id = p_state->>'project_id'
  returning * into saved_workflow;

  insert into public.project_workflow_transitions (
    id, project_id, owner_user_id, from_state, to_state, actor_type, actor_id,
    reason, idempotency_key, revision, created_at
  ) values (
    p_transition->>'id', p_transition->>'project_id', p_transition->>'owner_user_id',
    nullif(p_transition->>'from_state', ''), p_transition->>'to_state', p_transition->>'actor_type',
    nullif(p_transition->>'actor_id', ''), p_transition->>'reason',
    p_transition->>'idempotency_key', (p_transition->>'revision')::integer,
    p_transition->>'created_at'
  ) returning * into saved_transition;

  insert into public.project_builds (
    id, project_id, owner_user_id, design_brief_id, brief_version, brief_snapshot_json,
    mode, readiness_result_json, introduced_assumptions_json, warnings_json,
    transition_id, idempotency_key, initiated_by, created_at
  ) values (
    p_build->>'id', p_build->>'project_id', p_build->>'owner_user_id',
    p_build->>'design_brief_id', (p_build->>'brief_version')::integer,
    p_build->'brief_snapshot_json', p_build->>'mode', p_build->'readiness_result_json',
    coalesce(p_build->'introduced_assumptions_json', '[]'::jsonb),
    coalesce(p_build->'warnings_json', '[]'::jsonb), p_build->>'transition_id',
    p_build->>'idempotency_key', p_build->>'initiated_by', p_build->>'created_at'
  ) returning * into saved_build;

  return jsonb_build_object(
    'workflow', to_jsonb(saved_workflow),
    'transition', to_jsonb(saved_transition),
    'build', to_jsonb(saved_build)
  );
exception
  when unique_violation then
    return null;
end;
$$;

alter table public.project_builds enable row level security;

revoke all on table public.project_builds from anon, authenticated;
grant select, insert, delete on table public.project_builds to service_role;

revoke all on function public.apply_project_build_initiation(jsonb, jsonb, jsonb, text, integer)
  from public, anon, authenticated;
grant execute on function public.apply_project_build_initiation(jsonb, jsonb, jsonb, text, integer)
  to service_role;

comment on table public.project_builds is
  'Immutable build initiation records containing the exact frozen DesignBrief and readiness decision.';
