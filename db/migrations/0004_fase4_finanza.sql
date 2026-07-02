-- =====================================================================
-- Fase 4 — Finanza & Reporting: spesa, movimento_bancario,
-- documento_fiscale (+ audit trigger sui dati finanziari, spec §11).
-- FK iniziativa_id NULLABLE per la riconciliazione per commessa.
-- =====================================================================

create table if not exists public.spesa (
  id                    uuid primary key default gen_random_uuid(),
  iniziativa_id         uuid references public.iniziativa(id) on delete set null,
  work_package_id       uuid references public.work_package(id) on delete set null,
  categoria             text not null check (categoria in
    ('personale','materiali','missioni','attrezzature','subcontratti','overhead')),
  importo               numeric(14,2) not null check (importo >= 0),
  data                  date not null,
  riferimento_documento text,
  descrizione           text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

drop trigger if exists spesa_set_updated_at on public.spesa;
create trigger spesa_set_updated_at
  before update on public.spesa
  for each row execute function public.set_updated_at();

create table if not exists public.movimento_bancario (
  id            uuid primary key default gen_random_uuid(),
  data          date not null,
  importo       numeric(14,2) not null check (importo >= 0),
  segno         text not null check (segno in ('entrata','uscita')),
  descrizione   text,
  controparte   text,
  iniziativa_id uuid references public.iniziativa(id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists movimento_data_idx on public.movimento_bancario (data);

drop trigger if exists movimento_set_updated_at on public.movimento_bancario;
create trigger movimento_set_updated_at
  before update on public.movimento_bancario
  for each row execute function public.set_updated_at();

create table if not exists public.documento_fiscale (
  id                       uuid primary key default gen_random_uuid(),
  tipo                     text not null check (tipo in ('attiva','passiva')),
  numero                   text,
  data                     date not null,
  importo                  numeric(14,2) not null check (importo >= 0),
  controparte              text,
  iniziativa_id            uuid references public.iniziativa(id) on delete set null,
  stato_incasso_pagamento  text not null default 'aperto'
                           check (stato_incasso_pagamento in
                                  ('aperto','parziale','saldato')),
  data_scadenza            date,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create index if not exists documento_data_idx on public.documento_fiscale (data);

drop trigger if exists documento_set_updated_at on public.documento_fiscale;
create trigger documento_set_updated_at
  before update on public.documento_fiscale
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------
-- Audit sui dati finanziari (spec §11): ogni I/U/D tracciato
-- ---------------------------------------------------------------------
create or replace function public.fn_audit_finanza()
returns trigger
language plpgsql
as $$
declare
  v_id uuid;
begin
  v_id := coalesce(new.id, old.id);
  perform public.audit(
    tg_table_name::text, v_id, lower(tg_op),
    case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end
  );
  return coalesce(new, old);
end;
$$;

drop trigger if exists spesa_audit on public.spesa;
create trigger spesa_audit
  after insert or update or delete on public.spesa
  for each row execute function public.fn_audit_finanza();

drop trigger if exists movimento_audit on public.movimento_bancario;
create trigger movimento_audit
  after insert or update or delete on public.movimento_bancario
  for each row execute function public.fn_audit_finanza();

drop trigger if exists documento_audit on public.documento_fiscale;
create trigger documento_audit
  after insert or update or delete on public.documento_fiscale
  for each row execute function public.fn_audit_finanza();

-- ---------------------------------------------------------------------
-- RLS: tutto il modulo Finanza e' riservato ad admin
-- ---------------------------------------------------------------------
alter table public.spesa              enable row level security;
alter table public.movimento_bancario enable row level security;
alter table public.documento_fiscale  enable row level security;

drop policy if exists spesa_admin_all on public.spesa;
create policy spesa_admin_all on public.spesa
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists movimento_admin_all on public.movimento_bancario;
create policy movimento_admin_all on public.movimento_bancario
  for all using (public.is_admin()) with check (public.is_admin());

drop policy if exists documento_admin_all on public.documento_fiscale;
create policy documento_admin_all on public.documento_fiscale
  for all using (public.is_admin()) with check (public.is_admin());
