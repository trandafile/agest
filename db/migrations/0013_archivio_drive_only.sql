-- =====================================================================
-- 0013 — I PDF NON si conservano più nel database (per restare nel piano
-- gratuito di Neon): vengono caricati su Google Drive e nel DB resta solo
-- il metadato + il link (`gdrive_url`). `file_dati` diventa opzionale.
-- =====================================================================

alter table public.archivio_file alter column file_dati drop not null;
