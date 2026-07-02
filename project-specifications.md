# ANTECNICA Gestionale — Project Specifications

> Sistema gestionale interno di ANTECNICA SRLS. Copre timesheet, presenze e assenze
> del personale, un quadro di pianificazione (Proposte), un quadro di esecuzione
> (Progetti) e un quadro finanziario riservato all'amministrazione.
> Fatturazione elettronica **fuori scope** (già gestita da sistema esterno).

---

## 1. Obiettivi

- Dare al personale uno strumento semplice per **timesheet, presenze e ferie/permessi**.
- Dare all'admin un **quadro Proposte** per pianificare ore e costi di progetti non ancora approvati.
- Dare all'admin un **quadro Progetti** per seguire budget, spese e quote rimanenti dei progetti attivi.
- Dare all'admin un **quadro Finanziario** con i dati oggi tenuti su Google Sheet.
- Produrre **export di rendicontazione** (ore per progetto/persona/periodo) per i progetti finanziati.
- Restare **riusabile** per l'integrazione futura con il MAIC LAB task manager.

Principio architetturale portante: **Proposte e Progetti sono la stessa entità (`iniziativa`) in due stati diversi.** Questo rende la conversione proposta→progetto automatica e permette il riuso del backbone (persone, ore, budget) sia per l'esecuzione sia, in futuro, per i task.

> **Terminologia UI (07/2026).** A DB l'entità resta `iniziativa` (per non
> duplicare Proposte/Progetti), ma **nell'interfaccia è etichettata «Progetto»**
> (o «Proposta»/«Commessa» a seconda del contesto). I campi sono allineati a
> MAIC tasks `projects` per una futura integrazione: `acronimo`=acronym,
> `codice`=identifier, `controparte`=funding_agency (ente finanziatore/cliente),
> `titolo`=name. L'**acronimo** è anche la chiave di riconciliazione automatica
> dei movimenti bancari (colonna «Progetto» del Google Sheet finanziario).

---

## 2. Stack tecnico

- **App**: **Streamlit (Python)** — applicazione unica server-side, multipage.
- **Backend / DB**: **Neon** (PostgreSQL serverless — Row-Level Security, funzioni SQL/RPC). *(Il progetto era stato impostato su Supabase; migrato a Neon. L'auth è indipendente dal DB.)*
- **Accesso dati**: `psycopg` (v3) con connection pool, incapsulato in un layer `src/data/` (niente query sparse nelle pagine). Il pool vive in `src/lib/db.py`.
- **Validazione dominio**: `pydantic` per modelli e regole; regole di dominio in `src/domain/`.
- **Grafici/tabelle/export**: componenti nativi Streamlit + Plotly/Altair; export CSV/XLSX con `pandas`/`openpyxl`.
- **Logica sensibile** (validazioni forti timesheet, export rendicontazione, ricalcolo consuntivi): funzioni SQL/RPC lato DB o funzioni Python server-side, mai affidate al solo widget.
- **Deploy**: Streamlit Community Cloud; DB su Neon (usare l'endpoint **pooled** a runtime). Migrazioni versionate come SQL in `db/migrations/`, applicate con `scripts/apply_schema.py` (endpoint **diretto**) o `psql`.

### Autenticazione (login con Google aziendale)

Login con **Google account aziendale `@antecnica.it`** via OIDC. Due opzioni:

- **Opzione A (default)** — **OAuth manuale stile MAIC tasks**: bottone `st.link_button` verso l'URL di autorizzazione Google, callback con `?code=` sull'URL base dell'app, scambio code→token e lettura userinfo via `requests` (niente `st.login`). Streamlit è il server fidato e si connette a Neon con il ruolo owner (DSN); l'**autorizzazione per ruolo** è applicata in Python leggendo `persona.ruolo_sistema`. La restrizione al dominio si ottiene con la OAuth consent screen **Internal** + check `email endswith @antecnica.it`.
- **Opzione B** (difesa in profondità sui dati finanziari) — l'app si connette con un **ruolo DB ristretto** (non-owner, che *non* bypassa la RLS) e imposta a ogni richiesta la GUC `app.current_email` (`SET app.current_email = ...`); le policy RLS filtrano in base a quella. Non richiede un provider di Auth esterno.

In entrambi i casi il DSN (con la password del DB) resta **solo lato server** (mai esposto al browser). Con l'Opzione A la RLS è definita ma il ruolo owner la bypassa: l'enforcement effettivo è nel layer Python `src/auth/` (guardie per ruolo su ogni pagina/azione); con l'Opzione B l'enforcement è nativo via RLS + ruolo ristretto.

---

## 3. Ruoli e accessi

Tre ruoli di sistema, applicati via **RLS** (non solo lato UI):

| Ruolo        | Può vedere/fare |
|--------------|-----------------|
| `admin`      | Tutto: personale, tariffe, proposte, progetti, finanza, export. |
| `pm`         | Le iniziative di cui è responsabile (proposte/progetti), i relativi budget e consuntivi; i timesheet delle persone assegnate (sola lettura). |
| `dipendente` | Solo i **propri** timesheet, presenze, ferie/permessi e le proprie assegnazioni. |

I quadri **Finanza**, **Proposte** e **Progetti** (vista economica completa) sono di norma riservati ad `admin`. Ogni tabella ha policy RLS esplicite; il default è "deny".

---

## 4. Modello dati (bozza)

Nomi di dominio in italiano, codice in inglese dove naturale. Chiavi surrogate `uuid`.
`work_package_id` è **sempre nullable**: l'uso dei WP non è obbligatorio.

### Anagrafica e tariffe
- **persona** — `id, nome, cognome, matricola, email, ruolo_sistema, attivo,
  codice_fiscale, monte_ore_annuo, tipo_contratto['tempo_determinato'|
  'tempo_indeterminato'|'socio'], contratto_data_inizio, contratto_data_fine`
  - `contratto_data_fine` ammessa **solo** per tempo determinato (check DB).
  - Eliminazione persona: funzione DB `elimina_persona()` atomica — azzera i
    riferimenti RESTRICT (responsabile progetti, approvatore assenze), traccia
    in audit e rimuove i dati propri (cascade). La UI mostra il riepilogo dei
    dati collegati e sconsiglia l'eliminazione se ci sono mesi confermati
    (meglio disattivare con `attivo=false`).
- **tariffa_oraria** — `id, persona_id, valido_da, valido_al (null=aperto), importo_orario`
  - Tariffe **versionate nel tempo**: il costo delle ore va sempre calcolato con la tariffa vigente alla data dell'attività (requisito di rendicontazione).

### Backbone iniziative
- **iniziativa** — `id, tipo['proposta'|'progetto'], stato, codice, titolo, controparte (ente finanziatore/cliente), tipo_attivita_default, data_inizio, data_fine, ore_totali, budget_totale, probabilita_successo (solo proposte), note`
  - Stati proposta: `bozza → inviata → approvata → rifiutata`.
  - Alla `approvata`, conversione in `progetto` (vedi §6).
  - Stati progetto: `attivo → chiuso`.
- **work_package** *(opzionale)* — `id, iniziativa_id, codice, titolo, budget_ore, budget_costo`
- **assegnazione** — `id, iniziativa_id, persona_id, work_package_id?, tipo_attivita['RI'|'SS'|'altro'], ore_pianificate, tetto_ore_mese?`
  - È l'oggetto che unifica pianificazione ed esecuzione: `ore_pianificate` serve alle proposte; `tetto_ore_mese` è il "Max mese" del timesheet.
  - Una persona può avere più assegnazioni sulla stessa iniziativa con `tipo_attivita` diverso (es. Ricerca Industriale e Sviluppo Sperimentale) → nel timesheet sono **righe distinte**.
- **voce_budget** — `id, iniziativa_id, work_package_id?, categoria['personale'|'materiali'|'missioni'|'attrezzature'|'subcontratti'|'overhead'], importo`
- **milestone** — `id, iniziativa_id, work_package_id?, titolo, data_prevista, stato`

### Timesheet, presenze, assenze
- **timesheet_mese** — `id, persona_id, anno, mese, stato['bozza'|'confermato'], confermato_il`
  - Il record di "lock": finché è `bozza` è editabile; alla CONFERMA passa a `confermato` e le ore del mese si bloccano.
  - Unique su `(persona_id, anno, mese)`.
- **timesheet_ora** — `id, persona_id, assegnazione_id, data, ore`
  - Una riga per (assegnazione, giorno). Le celle vuote non generano record.
- **presenza** — `id, persona_id, data, ora_ingresso, ora_uscita, ore_totali, tipo, note`
- **assenza** — `id, persona_id, tipo['ferie'|'permesso'|'malattia'], data_inizio, data_fine, ore_o_giorni, stato['richiesta'|'approvata'|'rifiutata'], approvato_da, note`
- **calendario_festivita** — `id, data, descrizione` (per la validazione dei giorni non lavorativi)

### Spese e finanza
- **spesa** — `id, iniziativa_id, work_package_id?, categoria, importo, data, riferimento_documento, descrizione`
- **movimento_bancario** — `id, data, importo, segno['entrata'|'uscita'], descrizione, controparte, iniziativa_id? (riconciliazione per commessa)`
- **documento_fiscale** — `id, tipo['attiva'|'passiva'], numero, data, importo, controparte, iniziativa_id?, stato_incasso_pagamento`
  - Popolato importando/normalizzando l'attuale Google Sheet finanziario.

---

## 5. Modulo Timesheet (dettaglio, dal modello richiesto)

Vista mensile a griglia, un mese e una persona alla volta.

**Struttura**
- Selettore **mese/anno** e **persona** (per admin/pm; il dipendente vede solo sé stesso).
- Contatori annuali in testata: totale ore di attività progettuali inserite nell'anno.
- Colonne = giorni del mese (1..31) con giorno della settimana; sabati/domeniche e festività evidenziati.
- **Righe = assegnazioni progetto** della persona attive in quel mese (una riga per assegnazione = progetto + tipo attività). Ogni riga mostra: titolo iniziativa, tipo attività (RI/SS), intervallo date, ore totali del progetto, totale ore mese della riga, **tetto "Max mese"**, indicatore di validità.
- Riga **Totale** in fondo: somma giornaliera su tutte le righe.
- Pulsante **CONFERMA**: i dati si salvano solo alla conferma; la conferma blocca il mese.

**La didattica NON va inclusa** (è un contesto universitario, estraneo ad ANTECNICA).

**Regole di validazione (server-side, non solo UI)**
1. `ore` per singola cella: intero ≥ 0.
2. **Somma giornaliera ≤ 8 ore** su tutte le righe della persona (tetto giornaliero).
3. **Somma mensile per riga ≤ `tetto_ore_mese`** dell'assegnazione ("Max mese").
4. Nessuna ora su giorni non lavorativi (weekend/festività) salvo flag esplicito.
5. Editabile solo se `timesheet_mese.stato = 'bozza'`.
6. Le ore devono cadere nell'intervallo date dell'iniziativa.
7. Indicatore di validità per riga = verde se somma mese entro il tetto.

**Derivati**
- Costo consuntivo personale = Σ(`ore` × `tariffa_oraria` vigente alla `data`).
- Alimenta il consuntivo di Progetto (§7) e gli export di rendicontazione (§8).

---

## 6. Modulo Proposte (pianificazione, pre-award)

Serve a stimare ore/costi di iniziative che potrebbero non partire e a fare capacity planning.

**Funzionalità**
- Builder: aggiungi assegnazioni (persona + tipo attività + ore pianificate); il costo si calcola da ore × tariffa vigente, con roll-up per persona / (WP se usato) / totale.
- Voci di budget oltre al personale: materiali, missioni, attrezzature, subcontratti, overhead → **costo pieno**.
- Stato + **probabilità di successo** → pipeline pesata (valore atteso = budget × probabilità).
- **Capacity check**: somma ore pianificate per persona su tutte le proposte + progetti attivi, con alert di sovrallocazione.
- WP **facoltativi**: una proposta può avere assegnazioni e budget direttamente sull'iniziativa.
- **Conversione**: alla `approvata`, la proposta diventa `progetto` portandosi WP (se presenti), assegnazioni e budget come **baseline**.

---

## 7. Modulo Progetti (esecuzione, post-award)

Confronto **baseline vs consuntivo**.

**Funzionalità**
- Budget baseline (ereditato o inserito): per iniziativa, per WP (se usati), per categoria, ore per persona.
- Consuntivo automatico da: timesheet (costo personale reale), spese, dati finanziari.
- **Quote rimanenti** = budget − impegnato − speso, per iniziativa / WP / categoria.
- Milestone/deliverable con scadenze e stato.
- Avanzamento: % speso vs % avanzamento (per intercettare overrun).
- Cash del progetto: incassi previsti (per milestone) vs incassati.
- WP **facoltativi**: se non usati, tutto è aggregato a livello iniziativa.

---

## 8. Modulo Finanza (solo admin) + Reporting

- Import/normalizzazione dell'attuale Google Sheet finanziario in `movimento_bancario` e `documento_fiscale`.
- Riconciliazione **per commessa** (`iniziativa_id` su movimenti/documenti) → alimenta il consuntivo dei Progetti.
- Dashboard: cash flow, P&L per progetto, scadenzario.
- **Export rendicontazione**: ore per iniziativa / persona / periodo con tariffe applicate, in formato tabellare (CSV/XLSX) coerente con i rendiconti dei finanziatori.

---

## 9. Riuso per MAIC LAB task (fuori scope ora, previsto)

Il backbone è progettato perché un task del MAIC LAB task manager possa agganciarsi a `iniziativa` (e opzionalmente `work_package`) e a `persona`, e il log del tempo su un task possa generare righe `timesheet_ora`. L'integrazione è una fase successiva: qui va solo **preservata la compatibilità del modello** (niente scelte che impediscano l'aggancio).

---

## 10. Fasi

Poche fasi, incrementali. Ogni fase è rilasciabile e testabile.

### Fase 1 — Fondamenta
Setup Neon (progetto, migrazioni SQL applicate via `scripts/apply_schema.py`). Auth + ruoli + RLS di base. Anagrafica **persona** e **tariffa_oraria** versionata. Scaffold frontend (routing, layout, autenticazione, tema). Seed di dati minimi.

### Fase 2 — Operatività personale
**Timesheet** (griglia mensile con tutte le regole del §5, CONFERMA e lock), **Presenze**, **Ferie/Permessi** (richiesta + approvazione). Calendario festività.

### Fase 3 — Proposte & Progetti
Backbone `iniziativa` con WP opzionali, assegnazioni, voci di budget. Builder proposte + pipeline + capacity check. Conversione proposta→progetto. Vista progetto con budget/consuntivo/quote rimanenti alimentato dai timesheet.

### Fase 4 — Finanza & Reporting
Import del Google Sheet → tabelle finanza. Riconciliazione per commessa. Dashboard (cash flow, P&L per progetto, scadenzario). Export rendicontazione.

*(Integrazione MAIC LAB task: fase futura, non inclusa.)*

---

## 11. Estensioni v2 (07/2026)

- **Dashboard personale** (stile MAIC tasks): metriche personali (task attivi,
  in ritardo, completati 30g, puntualità, ritardo medio) + tab "I miei task" /
  "Supervisionati" raggruppati per iniziativa e ordinati per urgenza.
- **Modulo Task** (struttura copiata da MAIC tasks): task con owner/supervisor,
  stati (da_fare/in_corso/bloccato/completato/annullato), priorità, scadenza,
  subtask (`parent_task_id`), collegati opzionalmente a `iniziativa`.
  Visibilità come MAIC tasks: tutti vedono tutto; modifica owner/supervisor/admin.
- **Menu a blocchi** (`st.navigation`): Dashboard · Personale (Timesheet,
  Presenze, Ferie) · Attività (Task, Proposte) · Gestione (Progetti, Anagrafica)
  · Finanza (Finanza, Import banca — solo admin). Voci filtrate per ruolo.
- **Timesheet**: bottone **Autofill** (riempie i giorni lavorativi con 8h
  distribuite in round-robin tra le assegnazioni, rispettando tetti e intervalli);
  **export XLSX** per progetto nel formato SAL/MIUR (CUP, CF, monte ore annuo,
  righe RI/SS/Altri progetti/Didattica/Altro, firme, logo progetto).
- **Progetti**: tab Rendicontazione con CUP, tipo progetto e **logo** (usato
  nell'export XLSX). Anagrafica estesa con codice fiscale e monte ore annuo.
- **Presenze v2**: foglio mensile con UNA riga per giorno (ingresso/uscita/
  ore/tipo/note) + selezione via pop-up dei **task lavorati** (informativo:
  NON fa fede per i timesheet).
- **Sistema «Libro Cassa»** (dal Google Sheet ANTECNICA gestito via Apps
  Script): import automatico del workbook (`src/lib/import_contabile.py`) che
  riconosce i fogli «Libro Cassa <anno>» (header non in prima riga), i fogli
  per-progetto (INFO GENERALI + CALENDARIO MOVIMENTI) e «Spese periodiche».
  L'import è una-tantum, con richiesta esplicita di cancellare i dati
  precedenti. Ogni progetto porta `costo_complessivo`, `finanziamento_
  complessivo`, ente finanziatore, e i **movimenti previsti**
  (`movimento_previsto`) che alimentano la proiezione di cassa. Export nel
  medesimo formato XLSX (`src/lib/export_contabile.py`) per il round-trip col
  foglio Google; `movimento_bancario.anno_riferimento` conserva l'anno del
  foglio d'origine. Export diretto sul Google Sheet: predisposto, richiede un
  service account Google (istruzioni nel tab Export della pagina Finanza).
- **Finanza v2**: import del Google Sheet finanziario con **tracciato preset**
  (Data/Descrizione/N. Fattura/Tipo/Importo/Categoria/Progetto/Persona/Note,
  auto-riconciliazione per etichetta progetto); pagina **Import banca**
  (XML CAMT.053, CSV, PDF best-effort; anteprima editabile; log anti-duplicati
  per hash; archivio copia nella cartella Drive «Estratti conto bancari pdf -
  xml» quando montata); dashboard con saldo, uscite per categoria, autonomia
  stimata e **proiezione del flusso di cassa** (incassi programmati da documenti
  aperti + milestone, uscite programmate + ricorrenti stimate su media 3 mesi).

## 12. Requisiti non funzionali

- **Sicurezza**: RLS definita su ogni tabella, default deny; il DSN/password del DB resta solo lato server (mai nel client); audit su modifiche a timesheet confermati e a dati finanziari.
- **Integrità**: vincoli DB (check su ore, foreign key, unique su (persona, anno, mese) per `timesheet_mese`, esclusione anti-sovrapposizione per le tariffe versionate).
- **UX**: la griglia timesheet deve funzionare fluida con input rapido da tastiera; salvataggio solo su CONFERMA.
- **i18n**: interfaccia in italiano.
- **Testing**: unit test (pytest) sulle regole di dominio (timesheet, capacity, quote rimanenti), test sulle policy/enforcement dei ruoli, test dei flussi principali (es. `streamlit.testing` / AppTest).
- **Manutenibilità**: migrazioni SQL versionate in `db/migrations/`; modelli `pydantic` allineati allo schema; dipendenze bloccate (`requirements.txt`/`pyproject.toml`).
