-- Persist core-sourced generation pipeline progress for job observability.

alter table public.a2a_jobs
  add column if not exists progress_events_json jsonb not null default '[]'::jsonb;

create index if not exists idx_a2a_jobs_progress_events_gin
  on public.a2a_jobs
  using gin (progress_events_json);
