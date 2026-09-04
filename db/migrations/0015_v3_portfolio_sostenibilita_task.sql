-- =====================================================================
-- 0015 — Estensioni v3 (09/2026): portfolio pluriennale, sostenibilità
-- economica, task v3 (ore effettive, storico stati, reminder).
--
--   * piano_ore_anno       — ore pianificate per assegnazione e ANNO
--                            (fonte: foglio «impegno ore»); se assente, la UI
--                            distribuisce `assegnazione.ore_pianificate`
--                            pro-rata sui giorni dell'iniziativa.
--   * iniziativa.tipo_ricavo — 'agevolato' | 'mercato' | 'ricorrente'
--                            (KPI «quota ricavi da mercato/ricorrenti»
--                            del Piano strategico 2026-2030, §6).
--   * parametri_finanziari — parametri annuali per il cruscotto di
--                            sostenibilità (costi fissi, costo pieno FTE,
--                            aliquota fiscale stimata).
--   * task.ore_effettive, task.last_reminder_sent, persona.last_reminder_sent
--   * task_storico         — storico dei cambi di stato (trigger), usato dal
--                            report «cosa è cambiato» e dai briefing.
-- Tutto idempotente (if not exists / drop-create).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Piano ore per anno
-- ---------------------------------------------------------------------
create table if not exists public.piano_ore_anno (
  id              uuid primary key default gen_random_uuid(),
  assegnazione_id uuid not null references public.assegnazione(id) on delete cascade,
  anno            int  not null check (anno between 2000 and 2100),
  ore             numeric(8,1) not null check (ore >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (assegnazione_id, anno)
);

create index if not exists piano_ore_anno_ass_idx
  on public.piano_ore_anno (assegnazione_id);

drop trigger if exists piano_ore_anno_set_updated_at on public.piano_ore_anno;
create trigger piano_ore_anno_set_updated_at
  before update on public.piano_ore_anno
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Tipo di ricavo dell'iniziativa (per i KPI di sostenibilità)
-- ---------------------------------------------------------------------
alter table public.iniziativa
  add column if not exists tipo_ricavo text not null default 'agevolato';
alter table public.iniziativa drop constraint if exists iniziativa_tipo_ricavo_chk;
alter table public.iniziativa add constraint iniziativa_tipo_ricavo_chk
  check (tipo_ricavo in ('agevolato', 'mercato', 'ricorrente'));

-- ---------------------------------------------------------------------
-- Parametri finanziari annuali (cruscotto sostenibilità, solo admin)
-- ---------------------------------------------------------------------
create table if not exists public.parametri_finanziari (
  anno                  int primary key check (anno between 2000 and 2100),
  costi_fissi_mensili   numeric(14,2) check (costi_fissi_mensili is null or costi_fissi_mensili >= 0),
  costo_personale_annuo numeric(14,2) check (costo_personale_annuo is null or costo_personale_annuo >= 0),
  costi_indiretti_annui numeric(14,2) check (costi_indiretti_annui is null or costi_indiretti_annui >= 0),
  teste_dirette         numeric(6,2)  check (teste_dirette is null or teste_dirette >= 0),
  ore_vendibili_fte     int not null default 1620 check (ore_vendibili_fte > 0),
  aliquota_fiscale      numeric(5,4) not null default 0.2790
                        check (aliquota_fiscale >= 0 and aliquota_fiscale <= 1),
  saldo_iniziale        numeric(14,2),
  note                  text,
  updated_at            timestamptz not null default now()
);

drop trigger if exists parametri_finanziari_set_updated_at on public.parametri_finanziari;
create trigger parametri_finanziari_set_updated_at
  before update on public.parametri_finanziari
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Task v3
-- ---------------------------------------------------------------------
alter table public.task
  add column if not exists ore_effettive numeric(7,1)
    check (ore_effettive is null or ore_effettive >= 0);
alter table public.task add column if not exists last_reminder_sent date;
alter table public.persona add column if not exists last_reminder_sent date;

create table if not exists public.task_storico (
  id          uuid primary key default gen_random_uuid(),
  task_id     uuid not null references public.task(id) on delete cascade,
  stato_prec  text,
  stato_nuovo text not null,
  cambiato_da text,
  cambiato_il timestamptz not null default now()
);

create index if not exists task_storico_task_idx on public.task_storico (task_id);
create index if not exists task_storico_quando_idx on public.task_storico (cambiato_il);

create or replace function public.fn_task_storico()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    insert into public.task_storico (task_id, stato_prec, stato_nuovo, cambiato_da)
    values (new.id, null, new.stato,
            nullif(current_setting('app.current_email', true), ''));
  elsif old.stato is distinct from new.stato then
    insert into public.task_storico (task_id, stato_prec, stato_nuovo, cambiato_da)
    values (new.id, old.stato, new.stato,
            nullif(current_setting('app.current_email', true), ''));
  end if;
  return new;
end;
$$;

drop trigger if exists task_storico_trg on public.task;
create trigger task_storico_trg
  after insert or update of stato on public.task
  for each row execute function public.fn_task_storico();

-- ---------------------------------------------------------------------
-- RLS (rete di sicurezza; enforcement effettivo in Python, Opzione A)
-- ---------------------------------------------------------------------
alter table public.piano_ore_anno        enable row level security;
alter table public.parametri_finanziari  enable row level security;
alter table public.task_storico          enable row level security;

drop policy if exists poa_sel on public.piano_ore_anno;
drop policy if exists poa_adm on public.piano_ore_anno;
create policy poa_sel on public.piano_ore_anno
  for select using (public.current_persona_id() is not null);
create policy poa_adm on public.piano_ore_anno
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists pf_adm on public.parametri_finanziari;
create policy pf_adm on public.parametri_finanziari
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists ts_sel on public.task_storico;
drop policy if exists ts_ins on public.task_storico;
create policy ts_sel on public.task_storico
  for select using (public.current_persona_id() is not null);
create policy ts_ins on public.task_storico
  for insert with check (public.current_persona_id() is not null);
