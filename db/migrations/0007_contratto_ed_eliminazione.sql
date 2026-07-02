-- =====================================================================
-- 0007 — Tipologia di contratto sulle persone + eliminazione sicura.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Tipo di contratto
--   tempo_determinato -> data_inizio + data_fine
--   tempo_indeterminato -> data_inizio
--   socio -> (date facoltative)
-- ---------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'tipo_contratto') then
    create type public.tipo_contratto as enum
      ('tempo_determinato', 'tempo_indeterminato', 'socio');
  end if;
end $$;

alter table public.persona add column if not exists tipo_contratto public.tipo_contratto;
alter table public.persona add column if not exists contratto_data_inizio date;
alter table public.persona add column if not exists contratto_data_fine date;

-- La data di fine ha senso SOLO per il tempo determinato, e >= inizio.
alter table public.persona drop constraint if exists persona_contratto_fine_chk;
alter table public.persona add constraint persona_contratto_fine_chk check (
  contratto_data_fine is null
  or (
    tipo_contratto = 'tempo_determinato'
    and contratto_data_inizio is not null
    and contratto_data_fine >= contratto_data_inizio
  )
);

-- ---------------------------------------------------------------------
-- Eliminazione sicura di una persona (atomica).
--   Azzera i riferimenti RESTRICT (responsabile progetti, approvatore
--   assenze), traccia l'evento in audit, poi elimina la persona: le
--   tabelle collegate con ON DELETE CASCADE (tariffe, assegnazioni,
--   timesheet, presenze, assenze proprie) vengono rimosse di conseguenza.
-- ---------------------------------------------------------------------
create or replace function public.elimina_persona(p_id uuid)
returns void
language plpgsql
as $$
begin
  perform public.audit('persona', p_id, 'eliminazione', null);
  update public.iniziativa set responsabile_id = null where responsabile_id = p_id;
  update public.assenza    set approvato_da   = null where approvato_da   = p_id;
  delete from public.persona where id = p_id;
end;
$$;
