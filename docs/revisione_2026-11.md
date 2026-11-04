# Revisione 11/2026 — ANTECNICA Gestionale

Revisione del codice (pagine, UI, dati, dominio, migrazioni) e nuove funzioni
richieste. Branch `ccr-ea303c8f-k7no9c`. Gemello: `maic-tasks/docs/review_2026-11.md`.

## 1. Nuove funzioni

| Funzione | Dove | Note |
|---|---|---|
| Livello **gestore task** | `src/auth/permessi.py`, Anagrafica, migrazione 0019 | crea/modifica/archivia/elimina task e deliverable di tutti, importa; niente dati economici (spec §14.1) |
| **Import** deliverable/task/subtask da YAML/JSON | Task → «📥 Importa…», `src/domain/task_import.py` | schema `agest-import/v1` gemello di MAIC; prompt per LLM; una transazione (spec §14.2) |
| **Gantt di progetto** | Gestione → «Gantt di progetto» (solo admin) | import Excel/CSV/incolla/MS Project; trasferimento in task/deliverable/WP/milestone; collegamento; avanzamento reale (spec §14.3) |

**Da fare dopo il merge**: `python scripts/apply_schema.py` sul DB Neon
(0019 e il marcatore della 0018), poi spuntare «Gestore task» in Anagrafica per
chi deve averlo.

## 2. Errori corretti

Alta gravità
- Riaprire e riconfermare un mese di timesheet **cancellava le ore** dei
  progetti chiusi nel frattempo (la griglia mostrava solo i progetti attivi,
  `conferma_timesheet` sostituisce tutto il mese).
- Import spese periodiche: la colonna «Al» era letta come «Dal» → le spese
  ricorrenti sparivano dalla base costi e dalla proiezione di cassa.
- Libro Cassa reimportato: movimenti previsti raddoppiati (incassi doppi in
  cassa) e import interrotto a metà; ora rifiutato se già importato.
- Login simulato attivo in produzione se mancava `GOOGLE_CLIENT_ID` (chiunque
  poteva entrare come admin): ora serve `MOCK_LOGIN=1`.
- Presenze: primo salvataggio del mese con orari vuoti → crash.
- Timesheet: cella svuotata → crash; righe omonime → crash.

Media
- Migrazione 0018 rieseguita da `apply_schema.py` → ricollegava gli incassi
  scollegati a mano (ora gira una volta sola).
- Data di completamento dei task riportata a oggi a ogni salvataggio
  (falsava puntualità, «completati 30g», monthly report).
- «La mia settimana» andava in errore (`Task.updated_at` mancante).
- Eliminazioni: i commenti erano cancellati anche se poi l'eliminazione
  falliva; ora tutto in una transazione.
- Importi «1.500» letti come 1,5; celle «No» lette come «completata».
- Dialog task/milestone in errore se una dipendenza/deliverable era archiviato.
- Proposte: probabilità e tipo di ricavo della proposta precedente salvati
  sulla nuova; Dashboard: budget visibile ai non admin; Portfolio: NaN nel
  piano ore; import generico ripetibile due volte.
- Export MIUR: ore «altro» nella riga Sviluppo sperimentale.
- Salvataggio in Anagrafica → l'admin veniva disconnesso.

Bassa: promemoria «scaduto ieri» una sola volta per sempre; filtro Calendario
per progetto senza acronimo; «Periodo aperto» delle tariffe; nota settimanale
che si ripeteva; export timesheet senza `secrets.toml`; test AppTest con
percorso relativo.

## 3. Punti aperti (non modificati: richiedono una decisione)

- **RLS (solo Opzione B)**: il pm può leggere tabelle economiche
  (`movimento_previsto`, `voce_budget`, importi milestone); `commento_ins`
  accetta `autore_id` di altri; alcune policy di scrittura sono troppo larghe.
- **Proiezione di cassa**: possibile doppio conteggio fra fattura aperta e
  voce di calendario della stessa milestone; scaduti non incassati spariscono;
  fatture «parziali» contate per intero. Sostenibilità: mese corrente contato
  due volte.
- Bonifici CAMT: controparte letta dal creditore (spesso ANTECNICA stessa).
- Autofill timesheet ignora le ferie approvate.
- Guardia del mese bloccato aggirabile con un UPDATE che sposta la riga.
- Reimport Libro Cassa con «cancella» riscrive codice/titolo dei progetti.
- OAuth senza parametro `state`; ruolo letto solo al login (una retrocessione
  vale dal login successivo).
- Eliminazioni senza conferma: milestone, movimento previsto, monthly report,
  commento, assegnazione, file d'archivio.
- Missioni: importi visibili a tutti (la pagina dice che è voluto).

## 4. Prestazioni (analisi; codice non modificato, come richiesto)

Cause principali, in ordine di impatto:
1. **Nessuna cache** (`st.cache_data` assente): ogni clic riesegue la pagina e
   tutte le query; `list_persone` 2-3 volte per run, `list_tasks` 3 volte nella
   pagina Task.
2. **Un round-trip in più per query**: il pool usa `check=check_connection`
   (verifica la connessione a ogni prelievo) e ogni query è una transazione;
   con Neon serverless e Streamlit Cloud in regioni diverse ogni round-trip
   costa decine-centinaia di ms; dopo l'inattività Neon si sospende (avvio a
   freddo ~1 s).
3. **Lavoro fatto anche se non visibile**: export Markdown+XLSX nella pagina
   Task costruiti a ogni rerun (expander chiuso); `assicura_mese_precedente()`
   in Dashboard a ogni rerun per ogni utente; Finanza calcola tutte le 7 schede.
4. **N+1**: `list_deliverables` per progetto (albero Task, report), milestone
   per progetto (Portfolio), `get_report` per riga.
5. **Troppi widget**: un form «nuovo task» per ogni progetto e deliverable.
6. Minori: filtri `extract(year from data)` che non usano gli indici; FK senza
   indice (`assegnazione.persona_id`, `milestone.iniziativa_id`, …).

Interventi consigliati (in quest'ordine):
`st.cache_data(ttl=60)` sulle letture di riferimento con `.clear()` mirato
dopo le scritture → togliere `check_connection` (affidarsi a `max_idle` e al
retry) → export e calcoli pesanti solo al clic, `st.fragment` per le righe →
query raggruppate al posto dei cicli → stessa regione per Neon e Streamlit
Cloud, indici FK.

## 5. Allineamento con MAIC tasks e funzioni utili

Già allineati: gerarchia progetto→deliverable→task→subtask, formato di
import, logica del Gantt (`src/domain/gantt.py` = `maic-tasks/utils/gantt.py`),
pianificazione ore per anno (qui `piano_ore_anno`, in MAIC `effort_plan`).

Proposte:
1. **Codici leggibili** (E.1.2) anche qui: i ref dell'import diventerebbero
   identici fra le due app.
2. **Gantt nelle presentazioni** (slide cronoprogramma con avanzamento per
   SAL/review) e **baseline** del Gantt (piano della proposta vs ripianificato).
3. **Avviso settimanale di slittamento** al responsabile di progetto (task
   collegati con scadenza oltre la fine della voce).
4. **Import del piano ore da tabella** (persona/WP/mesi-persona dalla proposta)
   come per il Gantt.
5. Vista personale aggregata «i miei task» fra ANTECNICA e MAIC (sola lettura).
