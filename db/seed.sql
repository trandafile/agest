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

-- ---------------------------------------------------------------------
-- Festivita' nazionali italiane 2026 (per la validazione del timesheet)
-- ---------------------------------------------------------------------
insert into public.calendario_festivita (data, descrizione) values
  ('2026-01-01', 'Capodanno'),
  ('2026-01-06', 'Epifania'),
  ('2026-04-06', 'Lunedì dell''Angelo'),
  ('2026-04-25', 'Liberazione'),
  ('2026-05-01', 'Festa del Lavoro'),
  ('2026-06-02', 'Festa della Repubblica'),
  ('2026-08-15', 'Ferragosto'),
  ('2026-11-01', 'Ognissanti'),
  ('2026-12-08', 'Immacolata'),
  ('2026-12-25', 'Natale'),
  ('2026-12-26', 'Santo Stefano')
on conflict (data) do nothing;

-- ---------------------------------------------------------------------
-- Progetto demo con assegnazioni (per avere righe reali nel timesheet)
-- ---------------------------------------------------------------------
insert into public.iniziativa
  (tipo, stato, codice, titolo, controparte, data_inizio, data_fine,
   ore_totali, budget_totale, responsabile_id)
select 'progetto', 'attivo', 'DEMO-01', 'Progetto dimostrativo',
       'Cliente Demo', date '2026-01-01', date '2026-12-31',
       800, 60000, p.id
from public.persona p where p.email = 'luigi.boccia@antecnica.it'
on conflict (codice) do nothing;

insert into public.assegnazione
  (iniziativa_id, persona_id, tipo_attivita, ore_pianificate, tetto_ore_mese)
select i.id, p.id, 'RI', 300, 60
from public.iniziativa i, public.persona p
where i.codice = 'DEMO-01' and p.email = 'mario.rossi@antecnica.it'
on conflict do nothing;

insert into public.assegnazione
  (iniziativa_id, persona_id, tipo_attivita, ore_pianificate, tetto_ore_mese)
select i.id, p.id, 'SS', 200, 40
from public.iniziativa i, public.persona p
where i.codice = 'DEMO-01' and p.email = 'anna.verdi@antecnica.it'
on conflict do nothing;
