-- =====================================================================
-- 0019 — Livello «gestore task» e cronoprogramma (Gantt) di progetto.
--
--   * persona.gestore_task — livello gestionale INTERMEDIO, ortogonale al
--     ruolo di sistema: chi lo ha può creare, modificare, archiviare ed
--     eliminare task e deliverable di chiunque e importarli da YAML/JSON.
--     Non dà accesso ai dati economici (resta livello «dipendente»).
--   * gantt_voce — voci del cronoprogramma di un'iniziativa (WP, task,
--     deliverable, milestone), importate da Excel/CSV/MS Project.
--     Coordinate in date e, se note, in mesi di progetto (M1..Mn).
--   * task.gantt_voce_id / deliverable.gantt_voce_id — associazione
--     (facoltativa) del lavoro operativo alla voce di Gantt: il Gantt
--     mostra l'avanzamento reale calcolato dai task collegati.
-- Tutto idempotente.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Livello gestore task
-- ---------------------------------------------------------------------
alter table public.persona
  add column if not exists gestore_task boolean not null default false;

create or replace function public.is_gestore_task()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.persona p
    where lower(p.email) = lower(coalesce(public.current_app_email(), ''))
      and (p.ruolo_sistema = 'admin' or p.gestore_task)
  );
$$;

-- task e deliverable: il gestore scrive su tutti (rete di sicurezza RLS,
-- Opzione B; in Opzione A l'enforcement è in src/auth/permessi.py)
drop policy if exists task_gestore_all on public.task;
create policy task_gestore_all on public.task
  for all using (public.is_gestore_task()) with check (public.is_gestore_task());

drop policy if exists deliverable_gestore_all on public.deliverable;
create policy deliverable_gestore_all on public.deliverable
  for all using (public.is_gestore_task())
  with check (public.is_gestore_task());

-- ---------------------------------------------------------------------
-- Cronoprogramma (Gantt)
-- ---------------------------------------------------------------------
create table if not exists public.gantt_voce (
  id              uuid primary key default gen_random_uuid(),
  iniziativa_id   uuid not null references public.iniziativa(id) on delete cascade,
  parent_id       uuid references public.gantt_voce(id) on delete set null,
  codice          text not null,
  titolo          text not null,
  tipo            text not null default 'task'
                  check (tipo in ('wp', 'task', 'deliverable', 'milestone')),
  data_inizio     date,
  data_fine       date,
  mese_inizio     int check (mese_inizio is null or mese_inizio >= 1),
  mese_fine       int check (mese_fine is null or mese_fine >= 1),
  responsabile    text,
  ordine          int not null default 0,
  work_package_id uuid references public.work_package(id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (iniziativa_id, codice),
  constraint gantt_voce_date_chk check (
    data_inizio is null or data_fine is null or data_fine >= data_inizio
  ),
  constraint gantt_voce_mesi_chk check (
    mese_inizio is null or mese_fine is null or mese_fine >= mese_inizio
  )
);

create index if not exists gantt_voce_ini_idx on public.gantt_voce (iniziativa_id);

drop trigger if exists gantt_voce_set_updated_at on public.gantt_voce;
create trigger gantt_voce_set_updated_at
  before update on public.gantt_voce
  for each row execute function public.set_updated_at();

alter table public.task
  add column if not exists gantt_voce_id uuid
    references public.gantt_voce(id) on delete set null;
create index if not exists task_gantt_idx on public.task (gantt_voce_id);

alter table public.deliverable
  add column if not exists gantt_voce_id uuid
    references public.gantt_voce(id) on delete set null;
create index if not exists deliverable_gantt_idx on public.deliverable (gantt_voce_id);

-- ---------------------------------------------------------------------
-- RLS gantt_voce: lettura a tutti gli autenticati, scrittura solo admin
-- (la pagina Gantt è riservata all'amministratore).
-- ---------------------------------------------------------------------
alter table public.gantt_voce enable row level security;

drop policy if exists gantt_voce_sel on public.gantt_voce;
drop policy if exists gantt_voce_adm on public.gantt_voce;
create policy gantt_voce_sel on public.gantt_voce
  for select using (public.current_persona_id() is not null);
create policy gantt_voce_adm on public.gantt_voce
  for all using (public.is_admin()) with check (public.is_admin());
