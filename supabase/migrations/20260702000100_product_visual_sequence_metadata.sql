-- Support multi-view product image metadata stored inside generated_projects.hardware_ir.
-- The app stores per-view renders under assembly_metadata.product_visual_sequence plus
-- direct product_case_image_* / product_inside_image_* storage metadata.

create or replace function public.generated_project_visual_sequence_keys_match_project_id(
  input_hardware_ir jsonb,
  input_project_id text
)
returns boolean
language sql
immutable
as $$
  select not exists (
    select 1
    from jsonb_array_elements(
      case
        when jsonb_typeof(input_hardware_ir #> '{assembly_metadata,product_visual_sequence}') = 'array'
          then input_hardware_ir #> '{assembly_metadata,product_visual_sequence}'
        else '[]'::jsonb
      end
    ) as visual_item(value)
    where nullif(visual_item.value ->> 's3_key', '') is not null
      and visual_item.value ->> 's3_key' not like ('images/' || input_project_id || '/%')
  );
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'generated_projects_view_image_keys_match_project_id'
      and conrelid = 'public.generated_projects'::regclass
  ) then
    alter table public.generated_projects
      add constraint generated_projects_view_image_keys_match_project_id
      check (
        (
          hardware_ir #>> '{assembly_metadata,product_case_image_s3_key}' is null
          or hardware_ir #>> '{assembly_metadata,product_case_image_s3_key}' like ('images/' || project_id || '/%')
        )
        and (
          hardware_ir #>> '{assembly_metadata,product_inside_image_s3_key}' is null
          or hardware_ir #>> '{assembly_metadata,product_inside_image_s3_key}' like ('images/' || project_id || '/%')
        )
        and (
          hardware_ir #>> '{assembly_metadata,product_diagram_image_s3_key}' is null
          or hardware_ir #>> '{assembly_metadata,product_diagram_image_s3_key}' like ('images/' || project_id || '/%')
        )
      )
      not valid;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'generated_projects_product_visual_sequence_shape'
      and conrelid = 'public.generated_projects'::regclass
  ) then
    alter table public.generated_projects
      add constraint generated_projects_product_visual_sequence_shape
      check (
        hardware_ir #> '{assembly_metadata,product_visual_sequence}' is null
        or jsonb_typeof(hardware_ir #> '{assembly_metadata,product_visual_sequence}') = 'array'
      )
      not valid;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'generated_projects_product_visual_spec_shape'
      and conrelid = 'public.generated_projects'::regclass
  ) then
    alter table public.generated_projects
      add constraint generated_projects_product_visual_spec_shape
      check (
        hardware_ir #> '{assembly_metadata,product_visual_spec}' is null
        or jsonb_typeof(hardware_ir #> '{assembly_metadata,product_visual_spec}') = 'object'
      )
      not valid;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'generated_projects_visual_sequence_keys_match_project_id'
      and conrelid = 'public.generated_projects'::regclass
  ) then
    alter table public.generated_projects
      add constraint generated_projects_visual_sequence_keys_match_project_id
      check (
        public.generated_project_visual_sequence_keys_match_project_id(hardware_ir, project_id)
      )
      not valid;
  end if;
end $$;

create index if not exists idx_generated_projects_assembly_metadata_gin
  on public.generated_projects
  using gin ((hardware_ir -> 'assembly_metadata'));

create index if not exists idx_generated_projects_product_visual_sequence_gin
  on public.generated_projects
  using gin ((hardware_ir #> '{assembly_metadata,product_visual_sequence}'));

create index if not exists idx_generated_projects_product_visual_spec_gin
  on public.generated_projects
  using gin ((hardware_ir #> '{assembly_metadata,product_visual_spec}'));

create index if not exists idx_generated_projects_product_case_image_s3_key
  on public.generated_projects ((hardware_ir #>> '{assembly_metadata,product_case_image_s3_key}'))
  where hardware_ir #>> '{assembly_metadata,product_case_image_s3_key}' is not null;

create index if not exists idx_generated_projects_product_inside_image_s3_key
  on public.generated_projects ((hardware_ir #>> '{assembly_metadata,product_inside_image_s3_key}'))
  where hardware_ir #>> '{assembly_metadata,product_inside_image_s3_key}' is not null;
