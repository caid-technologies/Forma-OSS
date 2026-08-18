-- Backfill the public generated-project gallery from canonical worker revisions.
-- New conversational builds maintain this projection in application code.

with latest_revisions as (
  select distinct on (project_id)
    project_id,
    owner_user_id,
    revision,
    design_brief_id,
    design_brief_version,
    payload_json,
    created_at
  from public.project_revisions
  order by project_id, revision desc
), canonical_projects as (
  select
    revision.project_id,
    brief.conversation_id as chat_id,
    revision.owner_user_id,
    coalesce(
      nullif(revision.payload_json #>> '{state,overview,title}', ''),
      nullif(brief.payload_json->>'summary', ''),
      'Untitled Forma Project'
    ) as title,
    coalesce(brief.payload_json->>'summary', '') as prompt,
    jsonb_set(
      jsonb_set(
        jsonb_set(
          revision.payload_json->'state',
          '{assembly_metadata,project_id}',
          to_jsonb(revision.project_id),
          true
        ),
        '{assembly_metadata,chat_id}',
        to_jsonb(brief.conversation_id),
        true
      ),
      '{assembly_metadata,project_revision}',
      to_jsonb(revision.revision),
      true
    ) as hardware_ir,
    revision.created_at
  from latest_revisions revision
  join public.design_briefs brief
    on brief.project_id = revision.project_id
   and brief.owner_user_id = revision.owner_user_id
   and brief.design_brief_id = revision.design_brief_id
   and brief.brief_version = revision.design_brief_version
)
insert into public.generated_projects (
  project_id,
  chat_id,
  owner_user_id,
  visibility,
  title,
  prompt,
  hardware_ir,
  created_at,
  status
)
select
  project_id,
  chat_id,
  owner_user_id,
  'public',
  title,
  prompt,
  hardware_ir,
  created_at,
  'active'
from canonical_projects
on conflict (project_id) do nothing;
