-- =====================================================================
-- Seed di sviluppo — Fase 1
--   1 admin (luigi.boccia@antecnica.it) + 2 dipendenti
--   tariffe orarie versionate (periodo chiuso passato + periodo aperto)
-- Idempotente: `on conflict do nothing` non duplica (le tariffe hanno un
-- vincolo di ESCLUSIONE, quindi conflict target implicito: niente nome).
-- =====================================================================

insert into public.persona (nome, cognome, matricola, email, ruolo_sistema, attivo)
values
  ('Luigi', 'Boccia', 'A001', 'luigi.boccia@antecnica.it', 'admin',      true),
  ('Mario', 'Rossi',  'A002', 'mario.rossi@antecnica.it',  'dipendente', true),
  ('Anna',  'Verdi',  'A003', 'anna.verdi@antecnica.it',   'dipendente', true)
on conflict (email) do nothing;

-- Tariffe versionate per Mario Rossi: 2023 chiusa (30€), 2024→ aperta (35€)
insert into public.tariffa_oraria (persona_id, valido_da, valido_al, importo_orario)
select p.id, date '2023-01-01', date '2023-12-31', 30.00
from public.persona p where p.email = 'mario.rossi@antecnica.it'
on conflict do nothing;

insert into public.tariffa_oraria (persona_id, valido_da, valido_al, importo_orario)
select p.id, date '2024-01-01', null, 35.00
from public.persona p where p.email = 'mario.rossi@antecnica.it'
on conflict do nothing;

-- Tariffa aperta per Anna Verdi (32€ dal 2024)
insert into public.tariffa_oraria (persona_id, valido_da, valido_al, importo_orario)
select p.id, date '2024-01-01', null, 32.00
from public.persona p where p.email = 'anna.verdi@antecnica.it'
on conflict do nothing;

-- Tariffa aperta per l'admin (per completezza dei calcoli, 45€ dal 2023)
insert into public.tariffa_oraria (persona_id, valido_da, valido_al, importo_orario)
select p.id, date '2023-01-01', null, 45.00
from public.persona p where p.email = 'luigi.boccia@antecnica.it'
on conflict do nothing;
