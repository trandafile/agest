# ANTECNICA Gestionale

Gestionale interno di ANTECNICA SRLS: timesheet, presenze, ferie, Proposte
(pianificazione), Progetti (esecuzione), Finanza (admin). Stack **Streamlit +
PostgreSQL (Neon)**, login Google `@antecnica.it` (OAuth manuale stile MAIC
tasks, **Opzione A**: autorizzazione per ruolo in Python).

App pubblica: **https://antgest.streamlit.app/**

Fonte di verità funzionale: [`project-specifications.md`](project-specifications.md).
Guida per l'agente di coding: [`agents.md`](agents.md). Fasi: [`prompts.md`](prompts.md).

## Stato: TUTTE le fasi implementate ✅

| Fase | Contenuto | Stato |
|---|---|---|
| 1 — Fondamenta | Auth Google, ruoli, RLS, anagrafica + tariffe versionate | ✅ |
| 2 — Operatività | Timesheet a griglia con regole §5 + CONFERMA/lock, Presenze, Ferie | ✅ |
| 3 — Proposte & Progetti | Builder, pipeline pesata, capacity, conversione, baseline vs consuntivo, quote | ✅ |
| 4 — Finanza | Import CSV/XLSX con mapping, riconciliazione, dashboard, export rendicontazione, audit | ✅ |

Regole critiche del timesheet replicate **lato DB** (trigger `fn_timesheet_guard`
+ funzione atomica `conferma_timesheet`): tetto 8h/giorno, Max mese per
assegnazione, weekend/festivi con flag, lock del mese confermato, date entro
l'iniziativa. Verificate end-to-end su Neon (14/14 check).

---

## 1. Prerequisiti

- Python 3.11+ (testato su 3.13).
- Un database [Neon](https://neon.tech) (free tier sufficiente).
- Credenziali Google OAuth (client "Applicazione web").

## 2. Setup dipendenze

Niente virtualenv: in produzione Streamlit Community Cloud legge
`requirements.txt` in automatico.

```bash
pip install -r requirements.txt
```

## 3. Database Neon

1. https://neon.tech → **New Project** (region EU). Copia la connection string
   **Pooled** (host con `-pooler`) e quella diretta.
2. Metti i DSN in `.env` (vedi `.env.example`) e/o in
   `.streamlit/secrets.toml` (vedi §5).
3. Applica schema + seed:
   ```bash
   python scripts/apply_schema.py --seed
   ```
   Il seed carica: admin `luigi.boccia@antecnica.it`, 2 dipendenti con tariffe
   versionate, festività italiane 2026, un progetto demo con assegnazioni.

## 4. Credenziali Google OAuth

Il login usa il flusso OAuth manuale (bottone → Google → ritorno con `?code=`).

1. [Google Cloud Console](https://console.cloud.google.com) → progetto → **API
   e servizi → Credenziali → ID client OAuth** (Applicazione web).
2. **URI di reindirizzamento autorizzati** — è l'**URL base dell'app** (NON
   `/oauth2callback`):
   - `http://localhost:8501` (sviluppo)
   - `https://antgest.streamlit.app` (produzione)
3. Consent screen **Internal** se il progetto è nel Workspace ANTECNICA
   (il dominio è comunque verificato dall'app: solo `@antecnica.it`).

> In locale sono riusate le credenziali del client OAuth di MAIC tasks
> (già in `.streamlit/secrets.toml`, non committato). Per la produzione
> aggiungi `https://antgest.streamlit.app` ai redirect di quel client
> oppure crea un client dedicato.

## 5. Segreti — template TOML

Locale: copia in `.streamlit/secrets.toml`. Produzione: incolla nel pannello
**Secrets** di Streamlit Cloud (Manage app → Settings → Secrets).

```toml
# --- Google OAuth (login stile MAIC tasks) ---
GOOGLE_CLIENT_ID = "<client-id>.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "<client-secret>"
GOOGLE_REDIRECT_URI = "https://antgest.streamlit.app"   # in locale: http://localhost:8501

# --- Database PostgreSQL (Neon) — endpoint POOLED ---
[database]
dsn = "postgresql://<user>:<password>@<host>-pooler.<region>.aws.neon.tech/<db>?sslmode=require"

# --- Parametri applicativi ---
[app]
allowed_email_domain = "antecnica.it"
```

> ⚠️ Il `dsn` contiene la password del DB e il client secret è riservato:
> mai in git. `aggiorna_agest.bat` fa `git add -A`, ma `secrets.toml` e `.env`
> sono esclusi da `.gitignore`.

## 6. Avvio

```bash
streamlit run app.py          # locale, http://localhost:8501
```

Login con un account `@antecnica.it` presente in anagrafica (l'admin del seed
è `luigi.boccia@antecnica.it`). Senza credenziali Google nei secrets compare
un **mock login** di sviluppo.

## 7. Test, lint, format

```bash
pytest                # 40 test: tariffe, guardie, timesheet, economia, finanza, AppTest
ruff check .
black --check .
```

## Struttura

```
app.py                     # entrypoint (home + login)
pages/
  1_Anagrafica.py          # persone + tariffe versionate (admin)
  2_Timesheet.py           # griglia mensile con CONFERMA e lock
  3_Presenze.py            # ingresso/uscita, ore giornaliere
  4_Ferie.py               # richieste + approvazione admin/pm
  5_Proposte.py            # builder, pipeline pesata, capacity, conversione
  6_Progetti.py            # baseline vs consuntivo, quote, milestone
  7_Finanza.py             # import, riconciliazione, dashboard, export, audit
src/auth/                  # login Google (stile MAIC tasks), require_role()
src/data/                  # repository psycopg (niente query nelle pagine)
src/domain/                # regole pure: timesheet, economia, finanza, tariffe
src/ui/                    # componenti riusabili
src/lib/                   # pool psycopg (+ GUC audit), utility date
db/migrations/             # 0001 fondamenta, 0002 timesheet, 0003 proposte, 0004 finanza
db/seed.sql                # dati di sviluppo (persone, tariffe, festività, demo)
scripts/apply_schema.py    # applica migrazioni/seed a Neon
tests/                     # pytest (40) + streamlit AppTest
```
