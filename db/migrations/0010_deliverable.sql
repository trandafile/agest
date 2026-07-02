-- =====================================================================
-- 0010 — Deliverable (livello tra progetto e task, come MAIC tasks) +
-- flag «genera pagamento» sulle milestone.
--   Gerarchia attività: iniziativa -> deliverable -> task -> subtask.
-- =====================================================================

create table if not exists public.deliverable (
  id            uuid primary key default gen_random_uuid(),
  iniziativa_id uuid not null references public.iniziativa(id) on delete cascade,
  titolo        text not null,
  tipo          text,                    -- es. paper, prototipo, report, layout
  stato         text not null default 'da_fare' check (stato in
                ('da_fare','in_corso','bloccato','completato','annullato')),
  scadenza      date,
  owner_id      uuid references public.persona(id) on delete set null,
  supervisor_id uuid references public.persona(id) on delete set null,
  descrizione   text,
  archiviato    boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists deliverable_ini_idx on public.deliverable (iniziativa_id);

drop trigger if exists deliverable_set_updated_at on public.deliverable;
create trigger deliverable_set_updated_at
  before update on public.deliverable
  for each row execute function public.set_updated_at();

-- task collegabile a un deliverable (opzionale)
alter table public.task
  add column if not exists deliverable_id uuid
    references public.deliverable(id) on delete set null;
create index if not exists task_deliverable_idx on public.task (deliverable_id);

-- milestone: flag pagamento (milestone che determina un incasso)
alter table public.milestone
  add column if not exists genera_pagamento boolean not null default false;

-- ---------------------------------------------------------------------
-- RLS deliverable: visibilità come i task (tutti gli autenticati leggono;
-- scrivono owner/supervisor/admin).
-- ---------------------------------------------------------------------
alter table public.deliverable enable row level security;

drop policy if exists deliverable_sel_all   on public.deliverable;
drop policy if exists deliverable_admin_all on public.deliverable;
drop policy if exists deliverable_own_write on public.deliverable;
create policy deliverable_sel_all on public.deliverable
  for select using (public.current_persona_id() is not null);
create policy deliverable_admin_all on public.deliverable
  for all using (public.is_admin()) with check (public.is_admin());
create policy deliverable_own_write on public.deliverable
  for all using (
    owner_id = public.current_persona_id()
    or supervisor_id = public.current_persona_id()
  ) with check (
    owner_id = public.current_persona_id()
    or supervisor_id = public.current_persona_id()
  );
