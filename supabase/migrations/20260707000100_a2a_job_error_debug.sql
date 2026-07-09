-- Store optional debug traces for failed A2A/API generation jobs.

alter table public.a2a_jobs
  add column if not exists error_debug_json jsonb;
