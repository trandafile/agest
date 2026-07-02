-- =====================================================================
-- 0006 — Allineamento a MAIC tasks (Mtasks): campo `acronimo`.
--
-- Mappatura iniziativa (agest) <-> projects (Mtasks) per futura integrazione:
--   Mtasks.name           -> iniziativa.titolo
--   Mtasks.acronym        -> iniziativa.acronimo        (NUOVO: mancava)
--   Mtasks.identifier     -> iniziativa.codice          (gia' presente)
--   Mtasks.funding_agency -> iniziativa.controparte     (gia' presente)
--   Mtasks.start/end_date -> iniziativa.data_inizio/fine
--   Mtasks.is_archived    -> iniziativa.stato ('chiuso')
--
-- L'acronimo e' anche la chiave usata nel Google Sheet finanziario
-- (colonna "Progetto": RUSC, SPIN CHIP, DIPLEXER, ...) per la
-- riconciliazione automatica dei movimenti.
-- =====================================================================

alter table public.iniziativa add column if not exists acronimo text;

create index if not exists iniziativa_acronimo_idx
  on public.iniziativa (lower(acronimo));
