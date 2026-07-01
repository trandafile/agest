# ANTECNICA Gestionale

Gestionale interno di ANTECNICA SRLS (timesheet, presenze, ferie, proposte,
progetti, finanza). Stack **Streamlit + PostgreSQL (Neon)**, login Google
`@antecnica.it` (**Opzione A**: auth nativa Streamlit; l'autorizzazione per ruolo
è applicata in Python).

Fonte di verità funzionale: [`project-specifications.md`](project-specifications.md).
Guida per l'agente di coding: [`agents.md`](agents.md). Fasi: [`prompts.md`](prompts.md).

> **Nota sul backend.** Il progetto era stato impostato su Supabase; è stato
> migrato a **Neon** (PostgreSQL serverless). L'auth non cambia (è OIDC nativo
> Streamlit, indipendente dal DB). Lo schema è PostgreSQL puro; le policy RLS
> restano definite come rete di sicurezza (enforcement effettivo nelle guardie
> Python, come da Opzione A).

## Stato: Fase 1 — Fondamenta ✅

- Auth Google (Opzione A) con restrizione dominio `@antecnica.it`.
- Ruoli di sistema (`admin | pm | dipendente`) + guardie di ruolo in `src/auth/`.
- Anagrafica **persona** e **tariffa_oraria** versionata (CRUD, solo admin).
- RLS default-deny definita su ogni tabella (pronta per un ruolo ristretto).
- Test pytest (regole tariffe, guardie di ruolo) + streamlit AppTest.

---

## 1. Prerequisiti

- Python 3.11+ (testato su 3.13).
- Un account [Neon](https://neon.tech) (free tier sufficiente).
- Un account Google Workspace con dominio `antecnica.it` (admin per l'OAuth).

## 2. Setup dipendenze Python

Niente virtualenv: le dipendenze si installano direttamente e, in produzione,
Streamlit Community Cloud le legge in automatico da `requirements.txt`.

```bash
pip install -r requirements.txt
```

## 3. Creare il database Neon (passo-passo)

1. https://neon.tech → **New Project**. Scegli nome (es. `agest`) e region EU
   (es. Frankfurt). Neon crea un database e un ruolo owner.
2. **Dashboard → Connect**: copia la **connection string**. Usa quella
   **Pooled** (host con `-pooler`) per il serverless. Formato:
   `postgresql://<user>:<password>@<host>-pooler.<region>.aws.neon.tech/<db>?sslmode=require`
3. Applica schema + seed (vedi §5 per il DSN nei secrets, oppure via env):
   ```bash
   # opzione A: usa il DSN da .streamlit/secrets.toml
   python scripts/apply_schema.py --seed

   # opzione B: passa il DSN via variabile d'ambiente
   #   PowerShell:  $env:DATABASE_URL="postgresql://...sslmode=require"
   #   bash:        export DATABASE_URL="postgresql://...sslmode=require"
   python scripts/apply_schema.py --seed
   ```
   In alternativa con `psql`:
   ```bash
   psql "$DATABASE_URL" -f db/migrations/0001_fase1_fondamenta.sql
   psql "$DATABASE_URL" -f db/seed.sql
   ```

## 4. Credenziali Google OAuth (passo-passo)

1. [Google Cloud Console](https://console.cloud.google.com) → seleziona/crea il
   progetto dell'organizzazione ANTECNICA.
2. **API e servizi → Schermata consenso OAuth**: tipo utente **Internal**
   (limita l'accesso al dominio `antecnica.it`). Compila i campi richiesti.
3. **API e servizi → Credenziali → Crea credenziali → ID client OAuth**:
   - Tipo applicazione: **Applicazione web**.
   - **URI di reindirizzamento autorizzati**:
     - `http://localhost:8501/oauth2callback` (sviluppo locale)
     - l'equivalente in produzione (es. `https://<app>.streamlit.app/oauth2callback`).
   - Salva e copia **Client ID** e **Client secret**.

## 5. Configurare i segreti

Copia il template e inserisci i valori reali (il file è in `.gitignore`):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Contenuto di `.streamlit/secrets.toml` (senza valori reali):

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "<stringa-random-lunga>"          # python -c "import secrets;print(secrets.token_hex(32))"
client_id = "<google-oauth-client-id>"
client_secret = "<google-oauth-client-secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[database]
dsn = "postgresql://<user>:<password>@<host>-pooler.<region>.aws.neon.tech/<db>?sslmode=require"

[app]
allowed_email_domain = "antecnica.it"
```

> ⚠️ Il `dsn` contiene la password del DB: non mostrarlo in UI, non committarlo.
> Lo script `aggiorna_agest.bat` fa `git add -A`: `secrets.toml` è escluso da `.gitignore`.

## 6. Avvio in locale

```bash
streamlit run app.py
```

Apri http://localhost:8501, accedi con un account `@antecnica.it` presente in
anagrafica (il seed inserisce `luigi.boccia@antecnica.it` come admin).

## 6b. Deploy su Streamlit Community Cloud

1. Push del repo su GitHub (`aggiorna_agest.bat`).
2. https://share.streamlit.io → **New app** → seleziona repo/branch, main file
   `app.py`.
3. **Advanced settings → Secrets**: incolla lo stesso contenuto di
   `.streamlit/secrets.toml` (Streamlit Cloud non legge il file locale, che è in
   `.gitignore`). Aggiorna `auth.redirect_uri` con l'URL pubblico
   (`https://<app>.streamlit.app/oauth2callback`) e aggiungi quello stesso URI tra
   i redirect autorizzati in Google Cloud Console.
4. Le dipendenze vengono installate automaticamente da `requirements.txt`.

## 7. Test, lint, format

```bash
pytest                # unit + streamlit AppTest
ruff check .          # lint
black --check .       # format
```

## Struttura

```
app.py                     # entrypoint Streamlit (home + login)
pages/                     # una pagina per modulo (guardia di ruolo per pagina)
src/auth/                  # login Google, sessione, require_role()
src/data/                  # repository (psycopg) — niente query nelle pagine
src/domain/                # modelli pydantic + regole (tariffa vigente, costi)
src/ui/                    # componenti Streamlit riusabili
src/lib/                   # client DB (pool psycopg), utility date
db/migrations/             # schema versionato (SQL)
db/seed.sql                # dati di sviluppo
scripts/apply_schema.py    # applica migrazioni/seed a Neon
tests/                     # pytest + AppTest
```
