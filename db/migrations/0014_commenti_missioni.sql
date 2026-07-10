-- =====================================================================
-- 0014 — Commenti (generici, su qualunque modulo, stile MAIC tasks) +
--        Gestione missioni (trasferte) con spese e rimborso.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Commenti: polimorfici su (entita, entita_id).
--   entita in ('task','deliverable','milestone','iniziativa','missione')
-- Niente FK: l'integrita' e' garantita dalle delete_* nei repo.
-- ---------------------------------------------------------------------
create table if not exists public.commento (
  id         uuid primary key default gen_random_uuid(),
  entita     text not null check (entita in
             ('task','deliverable','milestone','iniziativa','missione')),
  entita_id  uuid not null,
  autore_id  uuid references public.persona(id) on delete set null,
  testo      text not null check (length(btrim(testo)) > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists commento_entita_idx
  on public.commento (entita, entita_id, created_at);

drop trigger if exists commento_set_updated_at on public.commento;
create trigger commento_set_updated_at
  before update on public.commento
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Missioni (trasferte)
-- ---------------------------------------------------------------------
create table if not exists public.missione (
  id             uuid primary key default gen_random_uuid(),
  iniziativa_id  uuid references public.iniziativa(id) on delete set null,
  persona_id     uuid not null references public.persona(id) on delete cascade,
  destinazione   text not null,
  data_inizio    date not null,
  data_fine      date not null,
  obiettivo      text,
  spesa_prevista numeric(12,2) check (spesa_prevista >= 0),
  stato          text not null default 'bozza' check (stato in
                 ('bozza','richiesta','autorizzata','respinta','conclusa')),
  autorizzata_da uuid references public.persona(id) on delete set null,
  autorizzata_il timestamptz,
  note_autorizzazione text,
  rimborso_stato text not null default 'non_richiesto' check (rimborso_stato in
                 ('non_richiesto','richiesto','liquidato')),
  rimborso_richiesto_il timestamptz,
  rimborso_liquidato_il timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint missione_periodo_ok check (data_fine >= data_inizio)
);

create index if not exists missione_ini_idx     on public.missione (iniziativa_id);
create index if not exists missione_persona_idx on public.missione (persona_id);

drop trigger if exists missione_set_updated_at on public.missione;
create trigger missione_set_updated_at
  before update on public.missione
  for each row execute function public.set_updated_at();

-- Spese effettivamente sostenute durante la missione
create table if not exists public.missione_spesa (
  id          uuid primary key default gen_random_uuid(),
  missione_id uuid not null references public.missione(id) on delete cascade,
  data        date not null,
  categoria   text not null check (categoria in
              ('viaggio','vitto','alloggio','iscrizione','altro')),
  descrizione text,
  importo     numeric(12,2) not null check (importo >= 0),
  created_at  timestamptz not null default now()
);

create index if not exists missione_spesa_idx
  on public.missione_spesa (missione_id);

-- ---------------------------------------------------------------------
-- RLS (rete di sicurezza; enforcement effettivo nelle pagine, Opzione A)
-- ---------------------------------------------------------------------
alter table public.commento       enable row level security;
alter table public.missione       enable row level security;
alter table public.missione_spesa enable row level security;

-- Commenti: tutti gli autenticati leggono e scrivono; modifica/cancella
-- solo l'autore o un admin.
drop policy if exists commento_sel on public.commento;
drop policy if exists commento_ins on public.commento;
drop policy if exists commento_own on public.commento;
drop policy if exists commento_adm on public.commento;
create policy commento_sel on public.commento
  for select using (public.current_persona_id() is not null);
create policy commento_ins on public.commento
  for insert with check (public.current_persona_id() is not null);
create policy commento_own on public.commento
  for all using (autore_id = public.current_persona_id())
  with check (autore_id = public.current_persona_id());
create policy commento_adm on public.commento
  for all using (public.is_admin()) with check (public.is_admin());

-- Missioni: lettura a tutti gli autenticati; scrittura al titolare o admin.
drop policy if exists missione_sel on public.missione;
drop policy if exists missione_own on public.missione;
drop policy if exists missione_adm on public.missione;
create policy missione_sel on public.missione
  for select using (public.current_persona_id() is not null);
create policy missione_own on public.missione
  for all using (persona_id = public.current_persona_id())
  with check (persona_id = public.current_persona_id());
create policy missione_adm on public.missione
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists missione_spesa_sel on public.missione_spesa;
drop policy if exists missione_spesa_wr  on public.missione_spesa;
create policy missione_spesa_sel on public.missione_spesa
  for select using (public.current_persona_id() is not null);
create policy missione_spesa_wr on public.missione_spesa
  for all using (public.current_persona_id() is not null)
  with check (public.current_persona_id() is not null);
