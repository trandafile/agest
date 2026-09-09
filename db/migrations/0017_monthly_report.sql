-- =====================================================================
-- 0017 — Monthly report dei progetti (09/2026).
--   * iniziativa.monthly_report            — il progetto richiede un monthly report
--   * iniziativa.monthly_report_istruzioni — istruzioni per l'assistente AI
--                                            (lingua, struttura, destinatario)
--   * monthly_report — un record per progetto/mese con il file .md generato
--                      dalla piattaforma (dati del mese + prompt), lo stato e
--                      la data di notifica al responsabile.
-- =====================================================================

alter table public.iniziativa
  add column if not exists monthly_report boolean not null default false;
alter table public.iniziativa
  add column if not exists monthly_report_istruzioni text;

create table if not exists public.monthly_report (
  id            uuid primary key default gen_random_uuid(),
  iniziativa_id uuid not null references public.iniziativa(id) on delete cascade,
  anno          int  not null check (anno between 2000 and 2100),
  mese          int  not null check (mese between 1 and 12),
  stato         text not null default 'pronto'
                check (stato in ('pronto', 'completato')),
  contenuto_md  text not null,
  generato_il   timestamptz not null default now(),
  notificato_il timestamptz,
  completato_il timestamptz,
  note          text,
  unique (iniziativa_id, anno, mese)
);

create index if not exists monthly_report_ini_idx
  on public.monthly_report (iniziativa_id, anno desc, mese desc);

-- ---------------------------------------------------------------------
-- RLS (rete di sicurezza; enforcement effettivo in Python, Opzione A)
-- ---------------------------------------------------------------------
alter table public.monthly_report enable row level security;

drop policy if exists mr_sel on public.monthly_report;
drop policy if exists mr_adm on public.monthly_report;
drop policy if exists mr_resp on public.monthly_report;
create policy mr_sel on public.monthly_report
  for select using (public.current_persona_id() is not null);
create policy mr_adm on public.monthly_report
  for all using (public.is_admin()) with check (public.is_admin());
create policy mr_resp on public.monthly_report
  for all using (exists (
    select 1 from public.iniziativa i
    where i.id = monthly_report.iniziativa_id
      and i.responsabile_id = public.current_persona_id()))
  with check (exists (
    select 1 from public.iniziativa i
    where i.id = monthly_report.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));
