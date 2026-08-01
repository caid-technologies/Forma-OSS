-- Durable dependency-aware worker execution state.

create table if not exists public.worker_execution_plans (
  id text primary key,
  project_id text not null,
  owner_user_id text not null,
  correlation_id text not null,
  status text not null check (status in ('planned', 'running', 'succeeded', 'failed')),
  max_concurrency integer not null check (max_concurrency >= 1 and max_concurrency <= 64),
  state_json jsonb not null,
  created_at text not null,
  updated_at text not null,
  completed_at text
);

create index if not exists idx_worker_execution_plans_owner_project_updated
  on public.worker_execution_plans (owner_user_id, project_id, updated_at desc);

create index if not exists idx_worker_execution_plans_correlation
  on public.worker_execution_plans (correlation_id);

alter table public.worker_execution_plans enable row level security;

revoke all on table public.worker_execution_plans from anon, authenticated;
grant select, insert, update, delete on table public.worker_execution_plans to service_role;

comment on table public.worker_execution_plans is
  'Restart-safe worker dependency graphs with durable request, progress, result, artifact, error, and aggregate state.';
