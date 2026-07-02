# prompts.md — ANTECNICA Gestionale

Prompt sequenziali da passare a Claude Code, una fase alla volta.
Prima di iniziare: fornire al modello `project-specifications.md` e `agents.md`, e attendere la fine (con test verdi) di ogni fase prima di lanciare la successiva.

---

## Prompt 0 — Bootstrap

```
Leggi project-specifications.md e agents.md in questo repository: sono la fonte di verità.
Stack: app Streamlit (Python) + Supabase, login Google @antecnica.it (Opzione A).
Non scrivere ancora codice applicativo. Fai solo:
1. Proponi la struttura di cartelle esatta secondo agents.md (Streamlit multipage).
2. Elenca le dipendenze (requirements.txt: streamlit, supabase, pydantic, pandas, openpyxl, ecc.) e la Supabase CLI.
3. Elenca le tabelle e le policy RLS che creerai in Fase 1.
4. Indica cosa deve contenere .streamlit/secrets.toml (senza valori reali).
Fermati e aspetta la mia conferma prima di procedere.
```

---

## Prompt 1 — Fase 1: Fondamenta

```
Implementa la Fase 1 (Fondamenta) come da project-specifications.md §10. Stack Streamlit + Supabase.

Backend (supabase/migrations):
- Tabelle: persona, tariffa_oraria (versionata con valido_da/valido_al).
- Enum ruolo_sistema: admin | pm | dipendente.
- RLS su entrambe, default deny. Policy: admin accede a tutto; dipendente vede solo la propria persona; pm come dipendente + lettura persone assegnate (placeholder finché non esistono le assegnazioni).
- seed.sql con: 1 admin (luigi.boccia@antecnica.it), 2 dipendenti, tariffe orarie di esempio con validità temporale.

App (Streamlit):
- Scaffold multipage secondo agents.md (app.py + /pages, /src/auth, /src/data, /src/domain, /src/ui, /src/lib).
- Client Supabase in src/lib (usa la service_role key da .streamlit/secrets.toml, solo server-side).
- Auth Opzione A: login Google via OIDC nativo Streamlit (st.login/st.user/st.logout); consenti solo email che termina con @antecnica.it; mappa l'email a persona.ruolo_sistema.
- Guardie di ruolo riusabili in src/auth (es. require_role("admin")).
- Pagina "Anagrafica personale" (CRUD persona + gestione tariffe versionate) visibile solo ad admin.

Test (pytest):
- Funzione che restituisce la tariffa vigente a una data.
- Guardia di ruolo: un dipendente non accede alle pagine admin.

Rispetta la Definition of Done in agents.md. Al termine mostrami cosa mettere in .streamlit/secrets.toml (senza valori) e come avviare il progetto in locale (streamlit run app.py + supabase CLI).
```

---

## Prompt 2 — Fase 2: Timesheet, Presenze, Ferie

```
Implementa la Fase 2 (Operatività personale) come da project-specifications.md §5 e §10.
Priorità: il TIMESHEET, che deve replicare lo schema mensile richiesto.

Modello:
- iniziativa (minima, per ora solo tipo='progetto', per avere righe reali nel timesheet), assegnazione (con tetto_ore_mese), timesheet_mese (lock), timesheet_ora.
- presenza, assenza, calendario_festivita. Migrazioni + RLS (il dipendente vede/scrive solo i propri dati).

Timesheet UI (griglia mensile):
- Selettore mese/anno e persona (dipendente = solo sé stesso).
- Colonne = giorni del mese con giorno settimana; weekend e festività evidenziati.
- Una riga per ASSEGNAZIONE (progetto + tipo_attivita RI/SS); mostra titolo, tipo, intervallo date, totale mese riga, "Max mese" (tetto_ore_mese), indicatore di validità.
- Riga Totale con somma giornaliera.
- Contatore annuale ore progettuali in testata.
- Pulsante CONFERMA: salva SOLO alla conferma e blocca il mese (timesheet_mese.stato='confermato').
- NON includere l'attività didattica.

Regole (server-side + UX client), da project-specifications.md §5:
1. somma giornaliera su tutte le righe ≤ 8 ore;
2. somma mensile per riga ≤ tetto_ore_mese;
3. niente ore su weekend/festività salvo flag;
4. editabile solo se mese in stato 'bozza';
5. ore entro l'intervallo date dell'iniziativa.
Implementa queste regole anche come constraint/funzione RPC lato DB, non solo nel client.

Presenze: registrazione ingresso/uscita e ore giornaliere.
Ferie/Permessi: richiesta dipendente + approvazione admin/pm, con stato.

Test:
- Unit: tetto 8h/giorno, tetto mese, blocco su mese confermato, esclusione weekend.
- e2e: compilazione e CONFERMA di un mese.

Rispetta la Definition of Done in agents.md.
```

---

## Prompt 3 — Fase 3: Proposte & Progetti

```
Implementa la Fase 3 (Proposte & Progetti) come da project-specifications.md §6 e §7.
Ricorda: Proposte e Progetti sono la stessa entità `iniziativa` in stati diversi. WP OPZIONALI ovunque.

Modello (estendi):
- iniziativa completa (tipo proposta|progetto, stati, probabilita_successo, budget_totale, ore_totali).
- work_package (nullable in tutte le FK), voce_budget (categorie da spec), milestone.
- Estendi assegnazione con ore_pianificate.

Proposte (pianificazione):
- Builder: aggiungi assegnazioni (persona + tipo + ore pianificate) → costo = ore × tariffa vigente; roll-up per persona / WP (se usato) / totale.
- Voci di budget non-personale (materiali, missioni, attrezzature, subcontratti, overhead) → costo pieno.
- Stato + probabilità → pipeline pesata (valore atteso).
- Capacity check: ore pianificate per persona su tutte proposte+progetti attivi, con alert sovrallocazione.

Conversione:
- Azione "approva proposta" → crea/aggiorna a progetto portando WP, assegnazioni, budget come baseline.

Progetti (esecuzione):
- Vista budget baseline vs consuntivo.
- Consuntivo personale dai timesheet (ore × tariffa vigente).
- Quote rimanenti = budget − impegnato − speso, per iniziativa/WP/categoria.
- Milestone con scadenze e stato.

Accesso: Proposte/Progetti (vista economica) riservati ad admin/pm secondo RLS.

Test:
- Unit: roll-up costi proposta, valore atteso pipeline, capacity per persona, calcolo quote rimanenti.
- Verifica che una proposta approvata generi un progetto coerente.

Rispetta la Definition of Done in agents.md.
```

---

## Prompt 4 — Fase 4: Finanza & Reporting

```
Implementa la Fase 4 (Finanza & Reporting) come da project-specifications.md §8.
Tutto il modulo Finanza è riservato ad admin (RLS).

Modello:
- movimento_bancario, documento_fiscale (attiva/passiva), spesa. FK iniziativa_id nullable per la riconciliazione per commessa.

Import:
- Funzione di import/normalizzazione da CSV/XLSX esportato dal Google Sheet finanziario esistente
  (ti fornirò il tracciato colonne). Mappa le colonne su movimento_bancario e documento_fiscale.

Riconciliazione:
- UI per associare movimenti/documenti a una iniziativa → alimenta il consuntivo dei Progetti.

Dashboard:
- Cash flow, P&L per progetto, scadenzario.

Export rendicontazione:
- Funzione server-side (Python) che genera, per iniziativa/persona/periodo, la tabella
  ore × tariffa vigente, esportabile in CSV/XLSX per i rendiconti dei finanziatori.

Test:
- Unit: parsing/mapping import, coerenza consuntivo dopo riconciliazione, correttezza export rendicontazione.

Rispetta la Definition of Done in agents.md.
```

---

## Nota per le fasi

- Non anticipare fasi: ogni prompt presuppone la fase precedente completata e testata.
- Per la Fase 4 servirà il tracciato colonne reale del Google Sheet: fornirlo prima di lanciare il prompt.
- L'integrazione con il MAIC LAB task manager sarà una fase separata; qui va solo preservata la compatibilità del modello (task → iniziativa/WP/persona, log tempo → timesheet_ora).
