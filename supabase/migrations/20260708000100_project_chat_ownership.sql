-- Attach generated project records to the chat that created them.

alter table public.generated_projects
  add column if not exists chat_id text;

update public.generated_projects
set chat_id = hardware_ir #>> '{assembly_metadata,chat_id}'
where chat_id is null
  and hardware_ir #>> '{assembly_metadata,chat_id}' is not null;

create index if not exists idx_generated_projects_chat_id
  on public.generated_projects (chat_id);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'generated_projects_hardware_ir_chat_id_matches'
      and conrelid = 'public.generated_projects'::regclass
  ) then
    alter table public.generated_projects
      add constraint generated_projects_hardware_ir_chat_id_matches
      check (
        hardware_ir #>> '{assembly_metadata,chat_id}' is null
        or chat_id is null
        or hardware_ir #>> '{assembly_metadata,chat_id}' = chat_id
      )
      not valid;
  end if;
end $$;
