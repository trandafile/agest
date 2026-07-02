-- =====================================================================
-- Fase 3 — Proposte & Progetti: work_package (OPZIONALE ovunque),
-- voce_budget, milestone. L'iniziativa completa esiste gia' (0002).
-- =====================================================================

-- ---------------------------------------------------------------------
-- work_package (opzionale: nessuna FK obbligatoria verso di esso)
-- ---------------------------------------------------------------------
create table if not exists public.work_package (
  id            uuid primary key default gen_random_uuid(),
  iniziativa_id uuid not null references public.iniziativa(id) on delete cascade,
  codice        text,
  titolo        text not null,
  budget_ore    numeric(10,1) check (budget_ore is null or budget_ore >= 0),
  budget_costo  numeric(14,2) check (budget_costo is null or budget_costo >= 0),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (iniziativa_id, codice)
);

drop trigger if exists work_package_set_updated_at on public.work_package;
create trigger work_package_set_updated_at
  before update on public.work_package
  for each row execute function public.set_updated_at();

-- FK differita di assegnazione.work_package_id (colonna creata in 0002)
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'assegnazione_wp_fk'
  ) then
    alter table public.assegnazione
      add constraint assegnazione_wp_fk
      foreign key (work_package_id) references public.work_package(id)
      on delete set null;
  end if;
end $$;

-- ---------------------------------------------------------------------
-- voce_budget — categorie non-personale a costo pieno + 'personale'
-- ---------------------------------------------------------------------
create table if not exists public.voce_budget (
  id              uuid primary key default gen_random_uuid(),
  iniziativa_id   uuid not null references public.iniziativa(id) on delete cascade,
  work_package_id uuid references public.work_package(id) on delete set null,
  categoria       text not null check (categoria in
    ('personale','materiali','missioni','attrezzature','subcontratti','overhead')),
  descrizione     text,
  importo         numeric(14,2) not null check (importo >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

drop trigger if exists voce_budget_set_updated_at on public.voce_budget;
create trigger voce_budget_set_updated_at
  before update on public.voce_budget
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- milestone
-- ---------------------------------------------------------------------
create table if not exists public.milestone (
  id              uuid primary key default gen_random_uuid(),
  iniziativa_id   uuid not null references public.iniziativa(id) on delete cascade,
  work_package_id uuid references public.work_package(id) on delete set null,
  titolo          text not null,
  data_prevista   date,
  stato           text not null default 'prevista'
                  check (stato in ('prevista','completata','slittata')),
  importo_incasso numeric(14,2) check (importo_incasso is null or importo_incasso >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

drop trigger if exists milestone_set_updated_at on public.milestone;
create trigger milestone_set_updated_at
  before update on public.milestone
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS: vista economica riservata (admin tutto; pm sulle proprie iniziative)
-- ---------------------------------------------------------------------
alter table public.work_package enable row level security;
alter table public.voce_budget  enable row level security;
alter table public.milestone    enable row level security;

drop policy if exists wp_admin_all on public.work_package;
drop policy if exists wp_pm_sel    on public.work_package;
create policy wp_admin_all on public.work_package
  for all using (public.is_admin()) with check (public.is_admin());
create policy wp_pm_sel on public.work_package
  for select using (exists (
    select 1 from public.iniziativa i
    where i.id = work_package.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));

drop policy if exists vb_admin_all on public.voce_budget;
drop policy if exists vb_pm_sel    on public.voce_budget;
create policy vb_admin_all on public.voce_budget
  for all using (public.is_admin()) with check (public.is_admin());
create policy vb_pm_sel on public.voce_budget
  for select using (exists (
    select 1 from public.iniziativa i
    where i.id = voce_budget.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));

drop policy if exists ms_admin_all on public.milestone;
drop policy if exists ms_pm_sel    on public.milestone;
create policy ms_admin_all on public.milestone
  for all using (public.is_admin()) with check (public.is_admin());
create policy ms_pm_sel on public.milestone
  for select using (exists (
    select 1 from public.iniziativa i
    where i.id = milestone.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));
