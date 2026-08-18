-- Track whether each A2A job used the component catalog/data warehouse,
-- Firecrawl-backed Web Research, or both.

alter table public.a2a_jobs
  add column if not exists source_usage_json jsonb not null default '{}'::jsonb;

with normalized_jobs as (
  select
    job_id,
    case
      when replace(lower(coalesce(payload_json ->> 'workflow', result_summary_json ->> 'workflow', 'default')), '-', '_')
        in ('firecrawl', 'web', 'internet', 'web_research')
        then 'web_research'
      when replace(lower(coalesce(payload_json ->> 'workflow', result_summary_json ->> 'workflow', 'default')), '-', '_')
        in ('catalog', 'seed', 'seed_db', 'legacy', 'default')
        then 'default'
      else replace(lower(coalesce(payload_json ->> 'workflow', result_summary_json ->> 'workflow', 'default')), '-', '_')
    end as workflow
  from public.a2a_jobs
  where action = 'blueprint.generate_project'
    and (source_usage_json is null or source_usage_json = '{}'::jsonb)
)
update public.a2a_jobs as jobs
set source_usage_json = case
  when normalized_jobs.workflow = 'web_research' then jsonb_build_object(
    'workflow', 'web_research',
    'catalog', false,
    'web_research', true,
    'data_warehouse', false,
    'firecrawl', true,
    'sources', jsonb_build_array('web_research'),
    'source_labels', jsonb_build_array('Web Research')
  )
  when normalized_jobs.workflow = 'default' then jsonb_build_object(
    'workflow', 'default',
    'catalog', true,
    'web_research', false,
    'data_warehouse', true,
    'firecrawl', false,
    'sources', jsonb_build_array('catalog'),
    'source_labels', jsonb_build_array('Catalog')
  )
  else jsonb_build_object(
    'workflow', normalized_jobs.workflow,
    'catalog', false,
    'web_research', false,
    'data_warehouse', false,
    'firecrawl', false,
    'sources', '[]'::jsonb,
    'source_labels', '[]'::jsonb
  )
end
from normalized_jobs
where jobs.job_id = normalized_jobs.job_id;

create index if not exists idx_a2a_jobs_source_usage_gin
  on public.a2a_jobs
  using gin (source_usage_json);
