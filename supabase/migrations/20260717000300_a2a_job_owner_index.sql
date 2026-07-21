-- Speeds up owner-scoped developer API job history queries.

create index if not exists idx_a2a_jobs_payload_owner_user_id
  on public.a2a_jobs ((payload_json->>'owner_user_id'));
