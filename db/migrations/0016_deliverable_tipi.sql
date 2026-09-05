-- =====================================================================
-- 0016 — Tipi di deliverable normalizzati (09/2026).
--   I deliverable di un progetto sono: prototipo | report | paper
--   (+ 'altro' come valvola di sfogo). Prima `tipo` era testo libero.
-- =====================================================================

-- Normalizza i valori già presenti (sinonimi italiani/inglesi -> canonici)
update public.deliverable set tipo = lower(trim(tipo)) where tipo is not null;

update public.deliverable set tipo = 'prototipo'
 where tipo in ('prototype', 'proto', 'prototipo', 'demonstrator', 'demo');
update public.deliverable set tipo = 'report'
 where tipo in ('report', 'rapporto', 'relazione', 'documento', 'deliverable');
update public.deliverable set tipo = 'paper'
 where tipo in ('paper', 'articolo', 'pubblicazione', 'publication', 'journal');
update public.deliverable set tipo = 'altro'
 where tipo is not null and tipo not in ('prototipo', 'report', 'paper');

alter table public.deliverable drop constraint if exists deliverable_tipo_chk;
alter table public.deliverable add constraint deliverable_tipo_chk
  check (tipo is null or tipo in ('prototipo', 'report', 'paper', 'altro'));

create index if not exists deliverable_owner_idx on public.deliverable (owner_id);
create index if not exists deliverable_scadenza_idx on public.deliverable (scadenza);
