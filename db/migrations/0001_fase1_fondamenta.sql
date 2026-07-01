-- =====================================================================
-- Fase 1 — Fondamenta: anagrafica persona + tariffa_oraria versionata
-- Target: PostgreSQL puro (Neon). Ruoli, RLS default-deny, helper.
--
-- Nota (Opzione A): l'app si connette come ruolo owner e l'autorizzazione
-- effettiva e' nelle guardie Python (src/auth). Le policy RLS qui restano
-- come rete di sicurezza e sono pronte per un futuro ruolo applicativo
-- ristretto: si basano sulla GUC di sessione `app.current_email`
-- (impostabile con `SET app.current_email = '...'`), non su un JWT.
-- =====================================================================

create extension if not exists btree_gist;

-- ---------------------------------------------------------------------
-- Enum ruolo di sistema
-- ---------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'ruolo_sistema') then
    create type public.ruolo_sistema as enum ('admin', 'pm', 'dipendente');
  end if;
end $$;

-- ---------------------------------------------------------------------
-- Trigger generico: updated_at
-- ---------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------
-- persona
-- ---------------------------------------------------------------------
create table if not exists public.persona (
  id            uuid primary key default gen_random_uuid(),
  nome          text not null,
  cognome       text not null,
  matricola     text unique,
  email         text not null unique,
  ruolo_sistema public.ruolo_sistema not null default 'dipendente',
  attivo        boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

drop trigger if exists persona_set_updated_at on public.persona;
create trigger persona_set_updated_at
  before update on public.persona
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- tariffa_oraria (versionata nel tempo)
--   valido_al = null  => periodo aperto (tariffa corrente)
--   nessuna sovrapposizione di periodi per la stessa persona (integrita').
-- ---------------------------------------------------------------------
create table if not exists public.tariffa_oraria (
  id             uuid primary key default gen_random_uuid(),
  persona_id     uuid not null references public.persona(id) on delete cascade,
  valido_da      date not null,
  valido_al      date,
  importo_orario numeric(10,2) not null check (importo_orario >= 0),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint tariffa_periodo_valido check (valido_al is null or valido_al >= valido_da),
  -- Periodi non sovrapposti per persona: la "tariffa vigente" resta univoca.
  constraint tariffa_no_overlap exclude using gist (
    persona_id with =,
    daterange(valido_da, coalesce(valido_al, 'infinity'::date), '[]') with &&
  )
);

create index if not exists tariffa_persona_da_idx
  on public.tariffa_oraria (persona_id, valido_da);

drop trigger if exists tariffa_set_updated_at on public.tariffa_oraria;
create trigger tariffa_set_updated_at
  before update on public.tariffa_oraria
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Funzioni helper per RLS (basate sulla GUC `app.current_email`)
--   security definer: se in futuro un ruolo ristretto interroga le tabelle,
--   la funzione gira come owner ed evita ricorsioni sulle policy.
-- ---------------------------------------------------------------------
create or replace function public.current_app_email()
returns text
language sql stable
as $$
  select nullif(current_setting('app.current_email', true), '');
$$;

create or replace function public.current_persona_id()
returns uuid
language sql stable security definer set search_path = public
as $$
  select p.id
  from public.persona p
  where lower(p.email) = lower(coalesce(public.current_app_email(), ''))
  limit 1;
$$;

create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.persona p
    where lower(p.email) = lower(coalesce(public.current_app_email(), ''))
      and p.ruolo_sistema = 'admin'
  );
$$;

-- PLACEHOLDER (Fase 3): il pm potra' leggere le persone a lui assegnate.
-- Finche' la tabella `assegnazione` non esiste, non restituisce righe extra.
create or replace function public.pm_sees_persona(target uuid)
returns boolean
language sql stable
as $$
  select false;
$$;

-- ---------------------------------------------------------------------
-- RLS — default deny su ogni tabella (rete di sicurezza sotto Opzione A)
-- ---------------------------------------------------------------------
alter table public.persona        enable row level security;
alter table public.tariffa_oraria enable row level security;

-- persona -------------------------------------------------------------
drop policy if exists persona_admin_all   on public.persona;
drop policy if exists persona_select_self on public.persona;
drop policy if exists persona_select_pm   on public.persona;

create policy persona_admin_all on public.persona
  for all
  using (public.is_admin())
  with check (public.is_admin());

create policy persona_select_self on public.persona
  for select
  using (id = public.current_persona_id());

create policy persona_select_pm on public.persona
  for select
  using (public.pm_sees_persona(id));

-- tariffa_oraria ------------------------------------------------------
drop policy if exists tariffa_admin_all   on public.tariffa_oraria;
drop policy if exists tariffa_select_self on public.tariffa_oraria;

create policy tariffa_admin_all on public.tariffa_oraria
  for all
  using (public.is_admin())
  with check (public.is_admin());

create policy tariffa_select_self on public.tariffa_oraria
  for select
  using (persona_id = public.current_persona_id());
