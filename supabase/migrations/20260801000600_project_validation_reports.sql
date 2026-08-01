-- Persist actionable validation findings against exact canonical project revisions.

create table if not exists public.project_validation_reports (
  id text primary key,
  project_id text not null,
  owner_user_id text not null,
  project_revision integer not null check (project_revision >= 1),
  design_brief_id text not null,
  design_brief_version integer not null check (design_brief_version >= 1),
  source_job_id text not null,
  revalidation_of_report_id text references public.project_validation_reports(id) on delete set null,
  payload_json jsonb not null,
  created_at text not null,
  constraint project_validation_reports_project_source_job_unique unique (project_id, source_job_id),
  constraint project_validation_reports_revision_fk foreign key (project_id, project_revision)
    references public.project_revisions(project_id, revision) on delete cascade
);

create index if not exists idx_project_validation_reports_owner_project_revision
  on public.project_validation_reports (owner_user_id, project_id, project_revision desc, created_at desc);

create index if not exists idx_project_validation_reports_design_brief
  on public.project_validation_reports (design_brief_id, design_brief_version);

create or replace function public.insert_project_validation_report(
  p_report jsonb
) returns jsonb
language plpgsql
set search_path = public
as $$
declare
  exact_revision public.project_revisions%rowtype;
  parent_report public.project_validation_reports%rowtype;
  saved_report public.project_validation_reports%rowtype;
begin
  select * into exact_revision
  from public.project_revisions
  where project_id = p_report->>'project_id'
    and owner_user_id = p_report->>'owner_user_id'
    and revision = (p_report->>'project_revision')::integer
    and design_brief_id = p_report->>'design_brief_id'
    and design_brief_version = (p_report->>'design_brief_version')::integer;

  if not found then
    return null;
  end if;

  if nullif(p_report->>'revalidation_of_report_id', '') is not null then
    select * into parent_report
    from public.project_validation_reports
    where id = p_report->>'revalidation_of_report_id'
      and project_id = p_report->>'project_id'
      and owner_user_id = p_report->>'owner_user_id'
      and project_revision < (p_report->>'project_revision')::integer;
    if not found then
      return null;
    end if;
  end if;

  insert into public.project_validation_reports (
    id, project_id, owner_user_id, project_revision, design_brief_id,
    design_brief_version, source_job_id, revalidation_of_report_id, payload_json, created_at
  ) values (
    p_report->>'id', p_report->>'project_id', p_report->>'owner_user_id',
    (p_report->>'project_revision')::integer, p_report->>'design_brief_id',
    (p_report->>'design_brief_version')::integer, p_report->>'source_job_id',
    nullif(p_report->>'revalidation_of_report_id', ''), p_report->'payload_json', p_report->>'created_at'
  ) returning * into saved_report;

  return to_jsonb(saved_report);
exception
  when unique_violation or foreign_key_violation then
    return null;
end;
$$;

alter table public.project_validation_reports enable row level security;

revoke all on table public.project_validation_reports from anon, authenticated;
grant select, insert, delete on table public.project_validation_reports to service_role;

revoke all on function public.insert_project_validation_report(jsonb) from public, anon, authenticated;
grant execute on function public.insert_project_validation_report(jsonb) to service_role;

comment on table public.project_validation_reports is
  'Immutable actionable validation findings bound to exact canonical project and DesignBrief revisions.';
