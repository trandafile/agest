"""Traduzione degli errori del database in messaggi leggibili (v3).

I vincoli sono definiti nelle migrazioni: quando il DB rifiuta una scrittura,
psycopg solleva un'eccezione il cui testo cita il nome del vincolo. Streamlit
Cloud però **oscura** il messaggio originale, quindi l'utente vede solo
«CheckViolation». Qui il nome del vincolo viene mappato sulla spiegazione in
italiano, da mostrare nella UI al posto del traceback.
"""

from __future__ import annotations

MESSAGGI: dict[str, str] = {
    # iniziativa (proposte / progetti)
    "iniziativa_date_coerenti": ("La data di fine non può precedere quella di inizio."),
    "iniziativa_stato_coerente": (
        "Stato non ammesso per questo tipo di iniziativa: le proposte possono "
        "essere bozza/inviata/approvata/rifiutata, i progetti attivo/chiuso."
    ),
    "iniziativa_probabilita_successo_check": (
        "La probabilità di successo deve essere compresa fra 0 e 100 %."
    ),
    "iniziativa_tipo_ricavo_chk": (
        "Tipo di ricavo non valido: ammessi agevolato, mercato, ricorrente."
    ),
    "iniziativa_tipo_check": "Tipo non valido: ammessi proposta e progetto.",
    "iniziativa_codice_key": (
        "Esiste già un'iniziativa con questo Identificativo / Codice: "
        "usane uno diverso (o lascialo vuoto)."
    ),
    # persone e tariffe
    "persona_contratto_fine_chk": (
        "La data di fine contratto è ammessa solo per il tempo determinato, "
        "e deve seguire la data di inizio."
    ),
    "persona_email_key": "Esiste già una persona con questa email.",
    "tariffa_no_overlap": (
        "Le tariffe di una persona non possono sovrapporsi nel tempo: chiudi "
        "il periodo precedente prima di aprirne uno nuovo."
    ),
    # timesheet
    "timesheet_mese_persona_anno_mese_key": (
        "Esiste già il timesheet di questa persona per il mese indicato."
    ),
    "timesheet_ora_ore_check": "Le ore di una singola cella devono essere fra 0 e 8.",
    # task e attività
    "task_stato_check": "Stato del task non valido.",
    "task_priorita_check": "Priorità del task non valida.",
    "task_dipendenza_no_self": "Un task non può dipendere da sé stesso.",
    # finanza
    "movimento_bancario_segno_check": (
        "Il segno del movimento deve essere entrata o uscita."
    ),
    "movimento_previsto_segno_check": (
        "Il segno del movimento deve essere entrata o uscita."
    ),
    "parametri_finanziari_aliquota_fiscale_check": (
        "L'aliquota fiscale deve essere compresa fra 0 e 1."
    ),
    "piano_ore_anno_ore_check": "Le ore del piano annuale non possono essere negative.",
}

GENERICO = (
    "Il database ha rifiutato l'operazione: controlla i dati inseriti "
    "(date coerenti, valori ammessi, codici non duplicati)."
)


def messaggio_errore_db(exc: BaseException) -> str:
    """Messaggio in italiano per un'eccezione del database.

    Cerca nel testo dell'eccezione il nome di un vincolo noto; se non lo trova
    ritorna un messaggio generico. Non espone mai il traceback all'utente.
    """
    testo = str(exc) or exc.__class__.__name__
    for vincolo, messaggio in MESSAGGI.items():
        if vincolo in testo:
            return f"⚠️ {messaggio}"
    # psycopg espone il nome del vincolo anche come attributo diagnostico
    nome = getattr(getattr(exc, "diag", None), "constraint_name", None)
    if nome and nome in MESSAGGI:
        return f"⚠️ {MESSAGGI[nome]}"
    return f"⚠️ {GENERICO}"
