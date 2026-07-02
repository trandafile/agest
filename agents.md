# AGENTS.md — ANTECNICA Gestionale

Guida operativa per l'agente di coding (Claude Code) su questo repository.
Leggere sempre `project-specifications.md` prima di scrivere codice: è la fonte di verità funzionale.

---

## Contesto

Gestionale interno di ANTECNICA SRLS: timesheet, presenze, ferie, Proposte (pianificazione), Progetti (esecuzione), Finanza (admin). Fatturazione elettronica fuori scope. Il modello dati deve restare compatibile con una futura integrazione del MAIC LAB task manager.

Regola aurea: **Proposte e Progetti sono la stessa entità `iniziativa` in stati diversi.** Non duplicare tabelle o logica tra i due.

---

## Stack e vincoli tecnici

- **App**: **Streamlit (Python 3.11+)**, multipage. Codice tipizzato (type hints) e `ruff`/`black` per lint/format.
- **DB/Backend**: **Neon** (PostgreSQL serverless — RLS, funzioni SQL/RPC). *(Migrato da Supabase; l'auth non dipende dal DB.)*
- **Data**: `psycopg` (v3) con connection pool in `src/lib/db.py`. **Niente query sparse nelle pagine**: incapsulare l'accesso dati in un layer `src/data/`.
- **Validazione**: `pydantic`. Le regole di dominio stanno in `src/domain/` (pure Python, testabili) e, dove critiche, sono replicate come constraint/funzioni RPC lato DB.
- **Auth**: login Google `@antecnica.it` via **OAuth manuale stile MAIC tasks** (`st.link_button` + callback `?code=` + `requests`; niente `st.login`). Default **Opzione A** (connessione Neon come owner via DSN + guardie di ruolo in `src/auth/`). L'Opzione B (ruolo DB ristretto + GUC `app.current_email` + RLS) è alternativa per difesa in profondità sui dati finanziari. Vedi `project-specifications.md` §2/§3.
- **Migrazioni**: SQL versionato in `db/migrations/`, applicato con `scripts/apply_schema.py` (endpoint diretto Neon) o `psql`. Mai modifiche manuali allo schema fuori dalle migrazioni.
- **Segreti**: in `.streamlit/secrets.toml` (locale) o nel pannello Secrets di Streamlit Cloud; in sviluppo anche `.env` (`DATABASE_URL`). Tutti fuori da git. Il DSN (con password DB) sta solo lì, mai stampato in UI né loggato.

---

## Struttura repo attesa

```
/db
  /migrations        # schema versionato (SQL)
  seed.sql           # dati di seed per sviluppo
/scripts
  apply_schema.py    # applica migrazioni/seed a Neon (sostituisce la CLI)
/.streamlit
  config.toml
  secrets.toml       # NON in git (auth Google + DSN Neon)
.env                 # NON in git (DATABASE_URL per sviluppo locale)
app.py               # entrypoint Streamlit
/pages               # pagine Streamlit (una per modulo)
  1_Timesheet.py
  2_Presenze.py
  3_Ferie.py
  4_Proposte.py
  5_Progetti.py
  6_Finanza.py
/src
  /auth              # login Google, sessione, guardie per ruolo
  /data              # accesso dati (repository su psycopg)
  /domain            # regole di dominio (pydantic, calcoli: costi, quote, capacity)
  /ui                # componenti Streamlit riusabili (es. griglia timesheet)
  /lib               # utility (date, formattazione, client DB = pool psycopg)
/tests               # pytest (unit) + streamlit AppTest
requirements.txt     # oppure pyproject.toml
project-specifications.md
agents.md
prompts.md
```

---

## Principi di sicurezza (non negoziabili)

- **RLS su ogni tabella**, default deny. Ogni migrazione che crea una tabella crea anche le sue policy (valide sia per l'Opzione B via ruolo ristretto + GUC `app.current_email`, sia come rete di sicurezza in Opzione A — dove il ruolo owner la bypassa e l'enforcement è in Python).
- Il **DSN** (con la password del DB) sta **solo** nei segreti lato server (`.streamlit/secrets.toml` / Secrets di Streamlit Cloud / `.env` locale); mai mostrato in UI, mai committato.
- **Autorizzazione**: ogni pagina/azione passa da una guardia di ruolo in `src/auth/` (Opzione A) o dalla RLS (Opzione B). Finanza, Proposte e Progetti (vista economica) → solo `admin`.
- Le validazioni critiche (tetto 8h/giorno, tetto mese, lock del mese confermato, quote rimanenti, import finanza) vanno **replicate lato DB** (constraint/funzioni RPC): la validazione nel widget è solo UX.
- Audit trail su: modifiche a timesheet confermati, modifiche a dati finanziari.

---

## Convenzioni

- **Lingua**: dominio in italiano (`persona`, `iniziativa`, `assegnazione`, `tetto_ore_mese`), codice in inglese. UI in italiano.
- **DB**: snake_case, chiavi `uuid` con default `gen_random_uuid()`, timestamp `created_at`/`updated_at`. `work_package_id` sempre nullable.
- **Python**: type hints ovunque, `ruff` + `black`, modelli `pydantic` per i dati che attraversano il confine DB/UI.
- **Commit**: Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`), una fase = uno o più commit tematici.
- **Stato**: usare `st.session_state` per la sessione utente/UI; il dato "vero" vive sul DB (Neon), non nello stato della UI.

---

## Workflow per l'agente

1. Leggere `project-specifications.md` e la sezione della fase corrente in `prompts.md`.
2. Se qualcosa è ambiguo o rischioso, **fermarsi e chiedere** invece di indovinare (specialmente su regole timesheet, RLS, calcoli economici).
3. Lavorare **una fase alla volta**; non anticipare fasi successive.
4. Per ogni cambiamento di schema: nuova migrazione in `db/migrations/` + policy RLS + allineamento dei modelli `pydantic`.
5. Scrivere test per le regole di dominio prima di considerare la feature conclusa.
6. Aggiornare `project-specifications.md` se una decisione implementativa cambia il contratto funzionale.

---

## Definition of Done (per feature)

- [ ] Migrazioni applicate e reversibili; policy RLS presenti e testate.
- [ ] Type hints completi; `ruff`/`black` puliti.
- [ ] Regole di dominio coperte da unit test pytest (in particolare: 8h/giorno, tetto mese, lock conferma, quote rimanenti, capacity).
- [ ] Validazione replicata lato DB dove critica.
- [ ] UI in italiano; guardia di ruolo attiva sulla pagina; login limitato a `@antecnica.it`.
- [ ] Nessuna chiave/DSN sensibile committata: solo in `.streamlit/secrets.toml`, `.env` (locale) o Secrets di Streamlit Cloud.
- [ ] Flusso principale coperto da un test (streamlit AppTest).

---

## Trappole note da evitare

- Non rendere obbligatori i **Work Package**: sono opzionali ovunque.
- Non includere l'**attività didattica** nel timesheet.
- Non salvare il timesheet a ogni cella: salvataggio solo su **CONFERMA**, e blocco del mese confermato.
- Non calcolare i costi con una tariffa "corrente" fissa: usare sempre la **tariffa vigente alla data** dell'attività.
- Non duplicare Proposte e Progetti: sono la stessa `iniziativa`.
