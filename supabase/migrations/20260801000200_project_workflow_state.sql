-- Central project workflow state and append-only transition history.

create table if not exists public.project_workflows (
  project_id text primary key,
  owner_user_id text not null,
  state text not null,
  revision integer not null check (revision >= 1),
  created_at text not null,
  updated_at text not null,
  constraint project_workflows_state_valid check (
    state in ('gathering_context', 'ready_to_build', 'building', 'awaiting_feedback', 'completed', 'cancelled', 'failed')
  )
);

create index if not exists idx_project_workflows_owner_updated
  on public.project_workflows (owner_user_id, updated_at desc);

create table if not exists public.project_workflow_transitions (
  id text primary key,
  project_id text not null,
  owner_user_id text not null,
  from_state text,
  to_state text not null,
  actor_type text not null,
  actor_id text,
  reason text not null,
  idempotency_key text,
  revision integer not null check (revision >= 1),
  created_at text not null,
  constraint project_workflow_transitions_from_state_valid check (
    from_state is null or from_state in ('gathering_context', 'ready_to_build', 'building', 'awaiting_feedback', 'completed', 'cancelled', 'failed')
  ),
  constraint project_workflow_transitions_to_state_valid check (
    to_state in ('gathering_context', 'ready_to_build', 'building', 'awaiting_feedback', 'completed', 'cancelled', 'failed')
  ),
  constraint project_workflow_transitions_actor_valid check (actor_type in ('user', 'system')),
  constraint project_workflow_transitions_project_revision_unique unique (project_id, revision),
  constraint project_workflow_transitions_project_idempotency_unique unique (project_id, idempotency_key)
);

create index if not exists idx_project_workflow_transitions_owner_project
  on public.project_workflow_transitions (owner_user_id, project_id, revision);

create or replace function public.apply_project_workflow_transition(
  p_state jsonb,
  p_transition jsonb,
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
begin
  select * into current_workflow
  from public.project_workflows
  where project_id = p_state->>'project_id'
  for update;

  if p_expected_state is null then
    if found then
      return null;
    end if;
    insert into public.project_workflows (
      project_id, owner_user_id, state, revision, created_at, updated_at
    ) values (
      p_state->>'project_id', p_state->>'owner_user_id', p_state->>'state',
      (p_state->>'revision')::integer, p_state->>'created_at', p_state->>'updated_at'
    ) returning * into saved_workflow;
  else
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
  end if;

  insert into public.project_workflow_transitions (
    id, project_id, owner_user_id, from_state, to_state, actor_type, actor_id,
    reason, idempotency_key, revision, created_at
  ) values (
    p_transition->>'id', p_transition->>'project_id', p_transition->>'owner_user_id',
    nullif(p_transition->>'from_state', ''), p_transition->>'to_state', p_transition->>'actor_type',
    nullif(p_transition->>'actor_id', ''), p_transition->>'reason',
    nullif(p_transition->>'idempotency_key', ''), (p_transition->>'revision')::integer,
    p_transition->>'created_at'
  ) returning * into saved_transition;

  return jsonb_build_object(
    'workflow', to_jsonb(saved_workflow),
    'transition', to_jsonb(saved_transition)
  );
exception
  when unique_violation then
    return null;
end;
$$;

alter table public.project_workflows enable row level security;
alter table public.project_workflow_transitions enable row level security;

revoke all on table public.project_workflows from anon, authenticated;
revoke all on table public.project_workflow_transitions from anon, authenticated;
grant select, insert, update, delete on table public.project_workflows to service_role;
grant select, insert, delete on table public.project_workflow_transitions to service_role;

revoke all on function public.apply_project_workflow_transition(jsonb, jsonb, text, integer) from public, anon, authenticated;
grant execute on function public.apply_project_workflow_transition(jsonb, jsonb, text, integer) to service_role;

comment on table public.project_workflows is 'Current state for the centralized project workflow state machine.';
comment on table public.project_workflow_transitions is 'Append-only workflow state transition history.';
