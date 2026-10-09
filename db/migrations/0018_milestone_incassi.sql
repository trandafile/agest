-- =====================================================================
-- 0018 — Collegamento ESPLICITO fra milestone e movimenti previsti.
--
--   * movimento_previsto.milestone_id (opzionale): un incasso (o un
--     pagamento) può dipendere da una milestone; una milestone può non
--     avere alcun incasso; un incasso può non avere alcuna milestone.
--   * milestone.genera_pagamento / importo_incasso diventano DERIVATI dai
--     movimenti collegati (trigger): restano per compatibilità con
--     calendario e report, ma non sono più un dato separato.
--   * I movimenti già presenti vengono collegati alle milestone di
--     pagamento corrispondenti (stesso progetto, importo e mese) e le
--     milestone di pagamento prive di movimento ne ricevono uno: da qui
--     la proiezione di cassa legge solo il calendario, senza doppi conteggi.
-- Idempotente.
-- =====================================================================

alter table public.movimento_previsto
  add column if not exists milestone_id uuid
    references public.milestone(id) on delete set null;

create index if not exists movimento_previsto_ms_idx
  on public.movimento_previsto (milestone_id);

-- ---------------------------------------------------------------------
-- Sincronizzazione dei campi derivati della milestone
-- ---------------------------------------------------------------------
create or replace function public.sync_milestone_incasso(p_milestone uuid)
returns void
language plpgsql
as $$
begin
  if p_milestone is null then
    return;
  end if;
  update public.milestone m
     set genera_pagamento = exists (
           select 1 from public.movimento_previsto p
            where p.milestone_id = m.id and p.segno = 'entrata'),
         importo_incasso = (
           select sum(p.importo) from public.movimento_previsto p
            where p.milestone_id = m.id and p.segno = 'entrata')
   where m.id = p_milestone;
end;
$$;

create or replace function public.fn_sync_milestone_incasso()
returns trigger
language plpgsql
as $$
begin
  if tg_op in ('INSERT', 'UPDATE') then
    perform public.sync_milestone_incasso(new.milestone_id);
  end if;
  if tg_op in ('UPDATE', 'DELETE') then
    perform public.sync_milestone_incasso(old.milestone_id);
  end if;
  return null;
end;
$$;

drop trigger if exists movimento_previsto_sync_ms on public.movimento_previsto;
create trigger movimento_previsto_sync_ms
  after insert or delete
     or update of milestone_id, importo, segno
  on public.movimento_previsto
  for each row execute function public.fn_sync_milestone_incasso();

-- ---------------------------------------------------------------------
-- Dati esistenti
-- ---------------------------------------------------------------------
-- 1) movimenti già inseriti -> milestone di pagamento corrispondente
update public.movimento_previsto p
   set milestone_id = (
         select m.id from public.milestone m
          where m.iniziativa_id = p.iniziativa_id
            and m.genera_pagamento
            and m.importo_incasso = p.importo
            and date_trunc('month', m.data_prevista)
                = date_trunc('month', p.data_attesa)
          order by m.data_prevista, m.created_at
          limit 1)
 where p.segno = 'entrata'
   and p.milestone_id is null
   and p.data_attesa is not null;

-- 2) milestone di pagamento senza movimento -> creo il movimento collegato
insert into public.movimento_previsto
       (iniziativa_id, milestone_id, descrizione, segno, importo, data_attesa,
        completata)
select m.iniziativa_id, m.id, m.titolo, 'entrata', m.importo_incasso,
       m.data_prevista, (m.stato = 'completata')
  from public.milestone m
 where m.genera_pagamento
   and m.importo_incasso is not null and m.importo_incasso > 0
   and not exists (
         select 1 from public.movimento_previsto p where p.milestone_id = m.id);

-- 3) flag «pagamento» senza alcun importo/movimento: non ha più significato
update public.milestone m
   set genera_pagamento = false
 where m.genera_pagamento
   and not exists (
         select 1 from public.movimento_previsto p
          where p.milestone_id = m.id and p.segno = 'entrata');

-- 4) allinea i campi derivati delle milestone con movimenti collegati
select public.sync_milestone_incasso(m.id)
  from public.milestone m
 where exists (select 1 from public.movimento_previsto p where p.milestone_id = m.id);
