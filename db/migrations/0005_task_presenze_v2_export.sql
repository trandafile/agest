-- =====================================================================
-- 0005 — Task (stile MAIC tasks), Presenze v2 (riga per giorno + task),
-- colonne per export rendicontazione XLSX (CUP, logo, CF, monte ore),
-- estensione movimenti bancari (tracciato Google Sheet) e log import banca.
-- =====================================================================

-- ---------------------------------------------------------------------
-- task — struttura copiata da MAIC tasks (owner+supervisor, stati,
-- priorita', scadenze); i subtask sono task con parent_task_id.
-- Collegato (opzionalmente) al backbone `iniziativa`, non a progetti separati.
-- ---------------------------------------------------------------------
create table if not exists public.task (
  id             uuid primary key default gen_random_uuid(),
  iniziativa_id  uuid references public.iniziativa(id) on delete cascade,
  parent_task_id uuid references public.task(id) on delete cascade,
  titolo         text not null,
  descrizione    text,
  owner_id       uuid references public.persona(id) on delete set null,
  supervisor_id  uuid references public.persona(id) on delete set null,
  stato          text not null default 'da_fare' check (stato in
                 ('da_fare','in_corso','bloccato','completato','annullato')),
  priorita       text not null default 'nessuna' check (priorita in
                 ('urgente','alta','media','bassa','nessuna')),
  ore_stimate    numeric(6,1) check (ore_stimate is null or ore_stimate >= 0),
  scadenza       date,
  completato_il  date,
  archiviato     boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists task_owner_idx      on public.task (owner_id);
create index if not exists task_supervisor_idx on public.task (supervisor_id);
create index if not exists task_iniziativa_idx on public.task (iniziativa_id);
create index if not exists task_parent_idx     on public.task (parent_task_id);

drop trigger if exists task_set_updated_at on public.task;
create trigger task_set_updated_at
  before update on public.task
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Presenze v2: una riga per giorno (dedup + unique), collegamento ai task
-- lavorati (informativo: NON alimenta i timesheet).
-- ---------------------------------------------------------------------
delete from public.presenza p
using public.presenza p2
where p.persona_id = p2.persona_id and p.data = p2.data
  and p.created_at > p2.created_at;

create unique index if not exists presenza_persona_giorno_uq
  on public.presenza (persona_id, data);

create table if not exists public.presenza_task (
  presenza_id uuid not null references public.presenza(id) on delete cascade,
  task_id     uuid not null references public.task(id) on delete cascade,
  primary key (presenza_id, task_id)
);

-- ---------------------------------------------------------------------
-- Colonne per l'export XLSX di rendicontazione (formato Amendola)
-- ---------------------------------------------------------------------
alter table public.iniziativa add column if not exists cup text;
alter table public.iniziativa add column if not exists tipo_progetto_desc text;
alter table public.iniziativa add column if not exists logo bytea;
alter table public.iniziativa add column if not exists logo_mime text;

alter table public.persona add column if not exists codice_fiscale text;
alter table public.persona add column if not exists monte_ore_annuo int default 1720;

-- ---------------------------------------------------------------------
-- Movimenti bancari: colonne del tracciato Google Sheet finanziario
--   Data | Descrizione | N. Fattura | Tipo | Importo | Categoria |
--   Progetto | Persona/Contatto | Note
-- `progetto_label` conserva l'etichetta testuale anche quando non
-- riconciliata con una iniziativa.
-- ---------------------------------------------------------------------
alter table public.movimento_bancario add column if not exists categoria text;
alter table public.movimento_bancario add column if not exists n_fattura text;
alter table public.movimento_bancario add column if not exists persona_contatto text;
alter table public.movimento_bancario add column if not exists note text;
alter table public.movimento_bancario add column if not exists progetto_label text;

-- Log import estratti conto (anti-duplicati per hash file)
create table if not exists public.import_bancario (
  id           uuid primary key default gen_random_uuid(),
  anno         int not null,
  mese         int not null check (mese between 1 and 12),
  file_name    text not null,
  file_hash    text not null unique,
  n_movimenti  int not null default 0,
  caricato_da  text,
  caricato_il  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
alter table public.task            enable row level security;
alter table public.presenza_task   enable row level security;
alter table public.import_bancario enable row level security;

-- task: regole MAIC tasks — tutti gli autenticati vedono tutto;
-- scrive l'owner/supervisor (o admin).
drop policy if exists task_sel_all   on public.task;
drop policy if exists task_admin_all on public.task;
drop policy if exists task_own_write on public.task;
create policy task_sel_all on public.task
  for select using (public.current_persona_id() is not null);
create policy task_admin_all on public.task
  for all using (public.is_admin()) with check (public.is_admin());
create policy task_own_write on public.task
  for all using (
    owner_id = public.current_persona_id()
    or supervisor_id = public.current_persona_id()
  ) with check (
    owner_id = public.current_persona_id()
    or supervisor_id = public.current_persona_id()
  );

drop policy if exists presenza_task_self on public.presenza_task;
drop policy if exists presenza_task_admin on public.presenza_task;
create policy presenza_task_admin on public.presenza_task
  for all using (public.is_admin()) with check (public.is_admin());
create policy presenza_task_self on public.presenza_task
  for all using (exists (
    select 1 from public.presenza p
    where p.id = presenza_task.presenza_id
      and p.persona_id = public.current_persona_id()
  )) with check (exists (
    select 1 from public.presenza p
    where p.id = presenza_task.presenza_id
      and p.persona_id = public.current_persona_id()
  ));

drop policy if exists import_bancario_admin on public.import_bancario;
create policy import_bancario_admin on public.import_bancario
  for all using (public.is_admin()) with check (public.is_admin());
