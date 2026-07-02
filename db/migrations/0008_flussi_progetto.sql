-- =====================================================================
-- 0008 — Sistema "Libro Cassa" per progetto (dal Google Sheet ANTECNICA):
--   * metadati finanziari sull'iniziativa (costo/finanziamento complessivo),
--   * movimenti previsti per progetto (CALENDARIO MOVIMENTI),
--   * spese periodiche ricorrenti.
-- =====================================================================

alter table public.iniziativa
  add column if not exists costo_complessivo numeric(14,2);
alter table public.iniziativa
  add column if not exists finanziamento_complessivo numeric(14,2);

-- ---------------------------------------------------------------------
-- movimento_previsto — flussi attesi per progetto (previsionale).
-- Alimenta la proiezione di cassa e la vista finanziaria del progetto.
-- ---------------------------------------------------------------------
create table if not exists public.movimento_previsto (
  id            uuid primary key default gen_random_uuid(),
  iniziativa_id uuid not null references public.iniziativa(id) on delete cascade,
  descrizione   text,
  segno         text not null check (segno in ('entrata', 'uscita')),
  importo       numeric(14,2) not null check (importo >= 0),
  data_attesa   date,
  completata    boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists movimento_previsto_ini_idx
  on public.movimento_previsto (iniziativa_id);

drop trigger if exists movimento_previsto_set_updated_at on public.movimento_previsto;
create trigger movimento_previsto_set_updated_at
  before update on public.movimento_previsto
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- spesa_periodica — costi ricorrenti (foglio «Spese periodiche»).
-- ---------------------------------------------------------------------
create table if not exists public.spesa_periodica (
  id             uuid primary key default gen_random_uuid(),
  descrizione    text not null,
  tipologia      text,
  importo        numeric(14,2),
  periodicita    text,
  iniziativa_id  uuid references public.iniziativa(id) on delete set null,
  progetto_label text,
  dal            date,
  al             date,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

drop trigger if exists spesa_periodica_set_updated_at on public.spesa_periodica;
create trigger spesa_periodica_set_updated_at
  before update on public.spesa_periodica
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
alter table public.movimento_previsto enable row level security;
alter table public.spesa_periodica    enable row level security;

drop policy if exists mp_admin_all on public.movimento_previsto;
drop policy if exists mp_pm_sel    on public.movimento_previsto;
create policy mp_admin_all on public.movimento_previsto
  for all using (public.is_admin()) with check (public.is_admin());
create policy mp_pm_sel on public.movimento_previsto
  for select using (exists (
    select 1 from public.iniziativa i
    where i.id = movimento_previsto.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));

drop policy if exists sp_admin_all on public.spesa_periodica;
create policy sp_admin_all on public.spesa_periodica
  for all using (public.is_admin()) with check (public.is_admin());
