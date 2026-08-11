-- Record the human anonymization review required before a sanitized
-- contribution snapshot can be included in a dataset export.

alter table public.project_contribution_snapshots
  add column if not exists anonymization_review_status text not null default 'pending',
  add column if not exists reviewed_at text,
  add column if not exists reviewed_by_user_id text;

alter table public.project_contribution_snapshots
  drop constraint if exists project_contribution_snapshots_review_status_valid;

alter table public.project_contribution_snapshots
  add constraint project_contribution_snapshots_review_status_valid
  check (anonymization_review_status in ('pending', 'approved', 'rejected'));

create index if not exists idx_project_contribution_snapshots_review_status
  on public.project_contribution_snapshots (anonymization_review_status);

comment on column public.project_contribution_snapshots.anonymization_review_status is
  'Human anonymization review gate. Only approved anonymized snapshots may be exported.';
