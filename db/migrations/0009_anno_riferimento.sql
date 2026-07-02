-- =====================================================================
-- 0009 — Anno di riferimento del movimento bancario.
-- Serve a mantenere l'aggregazione per «Libro Cassa <anno>» anche quando
-- la data della singola riga cade in un altro anno (refusi/riporti),
-- così l'export riproduce fedelmente i fogli del Google Sheet.
-- =====================================================================

alter table public.movimento_bancario
  add column if not exists anno_riferimento int;
