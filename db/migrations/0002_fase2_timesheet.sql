-- =====================================================================
-- Fase 2 — Operativita' personale: iniziativa (backbone), assegnazione,
-- timesheet (mese+ore con regole server-side), presenze, assenze,
-- calendario festivita', audit di base.
-- =====================================================================

-- ---------------------------------------------------------------------
-- iniziativa — backbone unico Proposte/Progetti (spec §4: stessa entita')
-- ---------------------------------------------------------------------
create table if not exists public.iniziativa (
  id                    uuid primary key default gen_random_uuid(),
  tipo                  text not null check (tipo in ('proposta','progetto')),
  stato                 text not null,
  codice                text unique,
  titolo                text not null,
  controparte           text,
  responsabile_id       uuid references public.persona(id),
  tipo_attivita_default text,
  data_inizio           date,
  data_fine             date,
  ore_totali            numeric(10,1),
  budget_totale         numeric(14,2),
  probabilita_successo  numeric(3,2) check (probabilita_successo between 0 and 1),
  note                  text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint iniziativa_date_coerenti
    check (data_fine is null or data_inizio is null or data_fine >= data_inizio),
  constraint iniziativa_stato_coerente check (
    (tipo = 'proposta' and stato in ('bozza','inviata','approvata','rifiutata'))
    or
    (tipo = 'progetto' and stato in ('attivo','chiuso'))
  )
);

drop trigger if exists iniziativa_set_updated_at on public.iniziativa;
create trigger iniziativa_set_updated_at
  before update on public.iniziativa
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- assegnazione — unifica pianificazione (ore_pianificate) ed esecuzione
-- (tetto_ore_mese = "Max mese" del timesheet). WP nullable SEMPRE.
-- ---------------------------------------------------------------------
create table if not exists public.assegnazione (
  id              uuid primary key default gen_random_uuid(),
  iniziativa_id   uuid not null references public.iniziativa(id) on delete cascade,
  persona_id      uuid not null references public.persona(id) on delete cascade,
  work_package_id uuid,          -- FK aggiunta in 0003 (tabella work_package)
  tipo_attivita   text not null default 'altro'
                  check (tipo_attivita in ('RI','SS','altro')),
  ore_pianificate numeric(8,1) check (ore_pianificate is null or ore_pianificate >= 0),
  tetto_ore_mese  numeric(6,1) check (tetto_ore_mese is null or tetto_ore_mese >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique nulls not distinct (iniziativa_id, persona_id, work_package_id, tipo_attivita)
);

drop trigger if exists assegnazione_set_updated_at on public.assegnazione;
create trigger assegnazione_set_updated_at
  before update on public.assegnazione
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- timesheet_mese — record di lock: 'bozza' editabile, 'confermato' bloccato
-- ---------------------------------------------------------------------
create table if not exists public.timesheet_mese (
  id            uuid primary key default gen_random_uuid(),
  persona_id    uuid not null references public.persona(id) on delete cascade,
  anno          int  not null check (anno between 2000 and 2100),
  mese          int  not null check (mese between 1 and 12),
  stato         text not null default 'bozza' check (stato in ('bozza','confermato')),
  confermato_il timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (persona_id, anno, mese)
);

drop trigger if exists timesheet_mese_set_updated_at on public.timesheet_mese;
create trigger timesheet_mese_set_updated_at
  before update on public.timesheet_mese
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- timesheet_ora — una riga per (assegnazione, giorno); celle vuote assenti
-- ---------------------------------------------------------------------
create table if not exists public.timesheet_ora (
  id              uuid primary key default gen_random_uuid(),
  persona_id      uuid not null references public.persona(id) on delete cascade,
  assegnazione_id uuid not null references public.assegnazione(id) on delete cascade,
  data            date not null,
  ore             int  not null check (ore >= 0 and ore <= 8),
  forzato         boolean not null default false,  -- ore su weekend/festivo consentite esplicitamente
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (assegnazione_id, data)
);

create index if not exists timesheet_ora_persona_data_idx
  on public.timesheet_ora (persona_id, data);

drop trigger if exists timesheet_ora_set_updated_at on public.timesheet_ora;
create trigger timesheet_ora_set_updated_at
  before update on public.timesheet_ora
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- presenza / assenza / calendario_festivita
-- ---------------------------------------------------------------------
create table if not exists public.presenza (
  id           uuid primary key default gen_random_uuid(),
  persona_id   uuid not null references public.persona(id) on delete cascade,
  data         date not null,
  ora_ingresso time,
  ora_uscita   time,
  ore_totali   numeric(4,2) check (ore_totali is null or ore_totali >= 0),
  tipo         text not null default 'ufficio'
               check (tipo in ('ufficio','remoto','trasferta')),
  note         text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint presenza_orari_coerenti
    check (ora_uscita is null or ora_ingresso is null or ora_uscita >= ora_ingresso)
);

create index if not exists presenza_persona_data_idx
  on public.presenza (persona_id, data);

drop trigger if exists presenza_set_updated_at on public.presenza;
create trigger presenza_set_updated_at
  before update on public.presenza
  for each row execute function public.set_updated_at();

create table if not exists public.assenza (
  id           uuid primary key default gen_random_uuid(),
  persona_id   uuid not null references public.persona(id) on delete cascade,
  tipo         text not null check (tipo in ('ferie','permesso','malattia')),
  data_inizio  date not null,
  data_fine    date not null,
  ore_o_giorni numeric(6,2) check (ore_o_giorni is null or ore_o_giorni > 0),
  stato        text not null default 'richiesta'
               check (stato in ('richiesta','approvata','rifiutata')),
  approvato_da uuid references public.persona(id),
  note         text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint assenza_date_coerenti check (data_fine >= data_inizio)
);

drop trigger if exists assenza_set_updated_at on public.assenza;
create trigger assenza_set_updated_at
  before update on public.assenza
  for each row execute function public.set_updated_at();

create table if not exists public.calendario_festivita (
  id          uuid primary key default gen_random_uuid(),
  data        date not null unique,
  descrizione text not null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- audit_log — richiesto da spec §11 (timesheet confermati, dati finanziari)
-- ---------------------------------------------------------------------
create table if not exists public.audit_log (
  id          uuid primary key default gen_random_uuid(),
  tabella     text not null,
  record_id   uuid,
  azione      text not null,
  dettaglio   jsonb,
  eseguito_da text,            -- email (GUC app.current_email, se impostata)
  eseguito_il timestamptz not null default now()
);

create or replace function public.audit(
  p_tabella text, p_record uuid, p_azione text, p_dettaglio jsonb
) returns void
language sql
as $$
  insert into public.audit_log (tabella, record_id, azione, dettaglio, eseguito_da)
  values (p_tabella, p_record, p_azione, p_dettaglio, public.current_app_email());
$$;

-- ---------------------------------------------------------------------
-- REGOLE TIMESHEET lato DB (spec §5) — trigger su timesheet_ora
--  1. ore intere 0..8 (check di colonna)
--  2. somma giornaliera <= 8 su tutte le righe della persona
--  3. somma mensile per assegnazione <= tetto_ore_mese
--  4. niente ore su weekend/festivi salvo flag `forzato`
--  5. editabile solo se mese in 'bozza' (insert/update/delete)
--  6. data dentro l'intervallo dell'iniziativa
-- ---------------------------------------------------------------------
create or replace function public.fn_timesheet_guard()
returns trigger
language plpgsql
as $$
declare
  v_row        public.timesheet_ora;
  v_tot_giorno int;
  v_tot_mese   numeric;
  v_tetto      numeric;
  v_inizio     date;
  v_fine       date;
  v_festivo    boolean;
begin
  v_row := coalesce(new, old);

  -- 5) mese bloccato?
  if exists (
      select 1 from public.timesheet_mese m
      where m.persona_id = v_row.persona_id
        and m.anno = extract(year from v_row.data)::int
        and m.mese = extract(month from v_row.data)::int
        and m.stato = 'confermato'
        and coalesce(current_setting('app.unlock_timesheet', true), '') <> 'on'
  ) then
    raise exception 'Timesheet %-% confermato: mese bloccato',
      extract(year from v_row.data)::int, extract(month from v_row.data)::int
      using errcode = 'P0001';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  -- coerenza persona/assegnazione
  if not exists (
      select 1 from public.assegnazione a
      where a.id = new.assegnazione_id and a.persona_id = new.persona_id
  ) then
    raise exception 'Assegnazione non appartenente alla persona' using errcode = 'P0001';
  end if;

  -- 2) tetto giornaliero 8h sulla persona
  select coalesce(sum(t.ore), 0) into v_tot_giorno
  from public.timesheet_ora t
  where t.persona_id = new.persona_id
    and t.data = new.data
    and t.id is distinct from new.id;
  if v_tot_giorno + new.ore > 8 then
    raise exception 'Superato il tetto giornaliero di 8 ore (% + %) il %',
      v_tot_giorno, new.ore, new.data using errcode = 'P0001';
  end if;

  -- 3) tetto mensile della riga (Max mese)
  select a.tetto_ore_mese, i.data_inizio, i.data_fine
    into v_tetto, v_inizio, v_fine
  from public.assegnazione a
  join public.iniziativa i on i.id = a.iniziativa_id
  where a.id = new.assegnazione_id;

  if v_tetto is not null then
    select coalesce(sum(t.ore), 0) into v_tot_mese
    from public.timesheet_ora t
    where t.assegnazione_id = new.assegnazione_id
      and date_trunc('month', t.data) = date_trunc('month', new.data)
      and t.id is distinct from new.id;
    if v_tot_mese + new.ore > v_tetto then
      raise exception 'Superato il tetto mensile (% h) dell''assegnazione',
        v_tetto using errcode = 'P0001';
    end if;
  end if;

  -- 6) data nell'intervallo dell'iniziativa
  if (v_inizio is not null and new.data < v_inizio)
     or (v_fine is not null and new.data > v_fine) then
    raise exception 'Data % fuori dall''intervallo dell''iniziativa (% - %)',
      new.data, v_inizio, v_fine using errcode = 'P0001';
  end if;

  -- 4) weekend/festivi solo con flag
  if not new.forzato then
    v_festivo := extract(isodow from new.data) in (6, 7)
                 or exists (select 1 from public.calendario_festivita f
                            where f.data = new.data);
    if v_festivo and new.ore > 0 then
      raise exception 'Ore su giorno non lavorativo (%): usa il flag esplicito',
        new.data using errcode = 'P0001';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists timesheet_ora_guard on public.timesheet_ora;
create trigger timesheet_ora_guard
  before insert or update or delete on public.timesheet_ora
  for each row execute function public.fn_timesheet_guard();

-- ---------------------------------------------------------------------
-- conferma_timesheet — salvataggio SOLO alla conferma, atomico:
-- sostituisce le ore del mese e blocca il mese. Le righe passano dai
-- trigger (tutte le regole rivalidate lato DB).
-- p_righe: [{"assegnazione_id": "...", "data": "YYYY-MM-DD", "ore": n, "forzato": bool}]
-- ---------------------------------------------------------------------
create or replace function public.conferma_timesheet(
  p_persona uuid, p_anno int, p_mese int, p_righe jsonb
) returns void
language plpgsql
as $$
declare
  v_stato text;
begin
  select stato into v_stato
  from public.timesheet_mese
  where persona_id = p_persona and anno = p_anno and mese = p_mese;

  if v_stato = 'confermato' then
    raise exception 'Mese %-% gia'' confermato', p_anno, p_mese
      using errcode = 'P0001';
  end if;

  delete from public.timesheet_ora t
  where t.persona_id = p_persona
    and extract(year from t.data)::int = p_anno
    and extract(month from t.data)::int = p_mese;

  insert into public.timesheet_ora (persona_id, assegnazione_id, data, ore, forzato)
  select p_persona,
         (r->>'assegnazione_id')::uuid,
         (r->>'data')::date,
         (r->>'ore')::int,
         coalesce((r->>'forzato')::boolean, false)
  from jsonb_array_elements(p_righe) r
  where (r->>'ore')::int > 0;

  insert into public.timesheet_mese (persona_id, anno, mese, stato, confermato_il)
  values (p_persona, p_anno, p_mese, 'confermato', now())
  on conflict (persona_id, anno, mese)
  do update set stato = 'confermato', confermato_il = now();

  perform public.audit('timesheet_mese', null, 'conferma',
    jsonb_build_object('persona_id', p_persona, 'anno', p_anno, 'mese', p_mese,
                       'n_righe', jsonb_array_length(p_righe)));
end;
$$;

-- Riapertura (solo admin, guardia applicativa) con audit
create or replace function public.riapri_timesheet(
  p_persona uuid, p_anno int, p_mese int
) returns void
language plpgsql
as $$
begin
  update public.timesheet_mese
     set stato = 'bozza', confermato_il = null
   where persona_id = p_persona and anno = p_anno and mese = p_mese;
  perform public.audit('timesheet_mese', null, 'riapertura',
    jsonb_build_object('persona_id', p_persona, 'anno', p_anno, 'mese', p_mese));
end;
$$;

-- ---------------------------------------------------------------------
-- pm_sees_persona — ora reale: il pm vede le persone assegnate alle
-- iniziative di cui e' responsabile (sostituisce il placeholder di 0001)
-- ---------------------------------------------------------------------
create or replace function public.pm_sees_persona(target uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1
    from public.assegnazione a
    join public.iniziativa i on i.id = a.iniziativa_id
    where a.persona_id = target
      and i.responsabile_id = public.current_persona_id()
  );
$$;

-- ---------------------------------------------------------------------
-- RLS — default deny; enforcement effettivo in Python (Opzione A)
-- ---------------------------------------------------------------------
alter table public.iniziativa           enable row level security;
alter table public.assegnazione         enable row level security;
alter table public.timesheet_mese       enable row level security;
alter table public.timesheet_ora        enable row level security;
alter table public.presenza             enable row level security;
alter table public.assenza              enable row level security;
alter table public.calendario_festivita enable row level security;
alter table public.audit_log            enable row level security;

-- iniziativa: admin tutto; pm le proprie; dipendente quelle su cui e' assegnato
drop policy if exists iniziativa_admin_all  on public.iniziativa;
drop policy if exists iniziativa_pm_sel     on public.iniziativa;
drop policy if exists iniziativa_dip_sel    on public.iniziativa;
create policy iniziativa_admin_all on public.iniziativa
  for all using (public.is_admin()) with check (public.is_admin());
create policy iniziativa_pm_sel on public.iniziativa
  for select using (responsabile_id = public.current_persona_id());
create policy iniziativa_dip_sel on public.iniziativa
  for select using (exists (
    select 1 from public.assegnazione a
    where a.iniziativa_id = iniziativa.id
      and a.persona_id = public.current_persona_id()));

-- assegnazione: admin tutto; interessato e pm responsabile in lettura
drop policy if exists assegnazione_admin_all on public.assegnazione;
drop policy if exists assegnazione_self_sel  on public.assegnazione;
drop policy if exists assegnazione_pm_sel    on public.assegnazione;
create policy assegnazione_admin_all on public.assegnazione
  for all using (public.is_admin()) with check (public.is_admin());
create policy assegnazione_self_sel on public.assegnazione
  for select using (persona_id = public.current_persona_id());
create policy assegnazione_pm_sel on public.assegnazione
  for select using (exists (
    select 1 from public.iniziativa i
    where i.id = assegnazione.iniziativa_id
      and i.responsabile_id = public.current_persona_id()));

-- timesheet: il dipendente scrive/legge solo il proprio; pm legge assegnati
drop policy if exists ts_mese_admin_all on public.timesheet_mese;
drop policy if exists ts_mese_self_all  on public.timesheet_mese;
drop policy if exists ts_mese_pm_sel    on public.timesheet_mese;
create policy ts_mese_admin_all on public.timesheet_mese
  for all using (public.is_admin()) with check (public.is_admin());
create policy ts_mese_self_all on public.timesheet_mese
  for all using (persona_id = public.current_persona_id())
  with check (persona_id = public.current_persona_id());
create policy ts_mese_pm_sel on public.timesheet_mese
  for select using (public.pm_sees_persona(persona_id));

drop policy if exists ts_ora_admin_all on public.timesheet_ora;
drop policy if exists ts_ora_self_all  on public.timesheet_ora;
drop policy if exists ts_ora_pm_sel    on public.timesheet_ora;
create policy ts_ora_admin_all on public.timesheet_ora
  for all using (public.is_admin()) with check (public.is_admin());
create policy ts_ora_self_all on public.timesheet_ora
  for all using (persona_id = public.current_persona_id())
  with check (persona_id = public.current_persona_id());
create policy ts_ora_pm_sel on public.timesheet_ora
  for select using (public.pm_sees_persona(persona_id));

-- presenze/assenze: proprie; admin tutto; pm lettura assegnati
drop policy if exists presenza_admin_all on public.presenza;
drop policy if exists presenza_self_all  on public.presenza;
drop policy if exists presenza_pm_sel    on public.presenza;
create policy presenza_admin_all on public.presenza
  for all using (public.is_admin()) with check (public.is_admin());
create policy presenza_self_all on public.presenza
  for all using (persona_id = public.current_persona_id())
  with check (persona_id = public.current_persona_id());
create policy presenza_pm_sel on public.presenza
  for select using (public.pm_sees_persona(persona_id));

drop policy if exists assenza_admin_all on public.assenza;
drop policy if exists assenza_self_all  on public.assenza;
drop policy if exists assenza_pm_sel    on public.assenza;
create policy assenza_admin_all on public.assenza
  for all using (public.is_admin()) with check (public.is_admin());
create policy assenza_self_all on public.assenza
  for all using (persona_id = public.current_persona_id())
  with check (persona_id = public.current_persona_id());
create policy assenza_pm_sel on public.assenza
  for select using (public.pm_sees_persona(persona_id));

-- festivita': lettura per tutti gli autenticati, scrittura admin
drop policy if exists festivita_admin_all on public.calendario_festivita;
drop policy if exists festivita_sel_all   on public.calendario_festivita;
create policy festivita_admin_all on public.calendario_festivita
  for all using (public.is_admin()) with check (public.is_admin());
create policy festivita_sel_all on public.calendario_festivita
  for select using (public.current_persona_id() is not null);

-- audit: solo admin
drop policy if exists audit_admin_sel on public.audit_log;
create policy audit_admin_sel on public.audit_log
  for select using (public.is_admin());
