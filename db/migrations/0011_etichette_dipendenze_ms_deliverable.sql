-- =====================================================================
-- 0011 — Elementi MAIC tasks: etichette (label), dipendenze tra task,
-- associazione milestone <-> deliverable.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Etichette (label) riusabili + associazione ai task (m2m)
-- ---------------------------------------------------------------------
create table if not exists public.etichetta (
  id     uuid primary key default gen_random_uuid(),
  nome   text not null unique,
  colore text default '#888888'
);

create table if not exists public.task_etichetta (
  task_id      uuid not null references public.task(id) on delete cascade,
  etichetta_id uuid not null references public.etichetta(id) on delete cascade,
  primary key (task_id, etichetta_id)
);

-- ---------------------------------------------------------------------
-- Dipendenze tra task (il task dipende_da un altro)
-- ---------------------------------------------------------------------
create table if not exists public.task_dipendenza (
  task_id    uuid not null references public.task(id) on delete cascade,
  dipende_da uuid not null references public.task(id) on delete cascade,
  primary key (task_id, dipende_da),
  constraint task_dipendenza_no_self check (task_id <> dipende_da)
);

-- ---------------------------------------------------------------------
-- Milestone <-> Deliverable (m2m): quali deliverable una milestone raccoglie
-- ---------------------------------------------------------------------
create table if not exists public.milestone_deliverable (
  milestone_id   uuid not null references public.milestone(id) on delete cascade,
  deliverable_id uuid not null references public.deliverable(id) on delete cascade,
  primary key (milestone_id, deliverable_id)
);

-- ---------------------------------------------------------------------
-- RLS: lettura per autenticati, scrittura admin (rete di sicurezza;
-- enforcement effettivo nelle pagine, Opzione A).
-- ---------------------------------------------------------------------
alter table public.etichetta            enable row level security;
alter table public.task_etichetta       enable row level security;
alter table public.task_dipendenza      enable row level security;
alter table public.milestone_deliverable enable row level security;

drop policy if exists etichetta_sel on public.etichetta;
drop policy if exists etichetta_adm on public.etichetta;
create policy etichetta_sel on public.etichetta
  for select using (public.current_persona_id() is not null);
create policy etichetta_adm on public.etichetta
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists te_sel on public.task_etichetta;
drop policy if exists te_wr  on public.task_etichetta;
create policy te_sel on public.task_etichetta
  for select using (public.current_persona_id() is not null);
create policy te_wr on public.task_etichetta
  for all using (public.current_persona_id() is not null)
  with check (public.current_persona_id() is not null);

drop policy if exists td_sel on public.task_dipendenza;
drop policy if exists td_wr  on public.task_dipendenza;
create policy td_sel on public.task_dipendenza
  for select using (public.current_persona_id() is not null);
create policy td_wr on public.task_dipendenza
  for all using (public.current_persona_id() is not null)
  with check (public.current_persona_id() is not null);

drop policy if exists md_sel on public.milestone_deliverable;
drop policy if exists md_adm on public.milestone_deliverable;
create policy md_sel on public.milestone_deliverable
  for select using (public.current_persona_id() is not null);
create policy md_adm on public.milestone_deliverable
  for all using (public.is_admin()) with check (public.is_admin());

-- Seed etichette di default
insert into public.etichetta (nome, colore) values
  ('urgente', '#D93025'),
  ('in attesa', '#BA7517'),
  ('review', '#1565C0'),
  ('documentazione', '#188038')
on conflict (nome) do nothing;
