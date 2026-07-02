-- =====================================================================
-- 0012 — Archivio file (PDF): estratti conto mensili, documenti fiscali,
-- altri allegati. Conservati NEL DATABASE (bytea) così sono persistenti e
-- scaricabili anche in produzione; `gdrive_url` opzionale se caricati anche
-- su Google Drive.
-- =====================================================================

create table if not exists public.archivio_file (
  id            uuid primary key default gen_random_uuid(),
  categoria     text not null default 'altro' check (categoria in
                ('estratto_conto','documento_fiscale','altro')),
  anno          int,
  mese          int check (mese is null or mese between 1 and 12),
  descrizione   text,
  file_nome     text not null,
  file_mime     text,
  file_dati     bytea not null,
  file_hash     text unique,
  gdrive_url    text,
  iniziativa_id uuid references public.iniziativa(id) on delete set null,
  documento_id  uuid references public.documento_fiscale(id) on delete set null,
  caricato_da   text,
  caricato_il   timestamptz not null default now()
);

create index if not exists archivio_categoria_idx
  on public.archivio_file (categoria, anno, mese);

-- RLS: tutto il modulo finanziario è riservato ad admin
alter table public.archivio_file enable row level security;
drop policy if exists archivio_admin on public.archivio_file;
create policy archivio_admin on public.archivio_file
  for all using (public.is_admin()) with check (public.is_admin());
