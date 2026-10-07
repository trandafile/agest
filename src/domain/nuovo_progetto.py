"""Validazione della creazione diretta di un progetto (spec §13.11).

Regole pure, testabili senza DB né Streamlit. Le stesse condizioni sono
imposte anche dal database (vincoli `iniziativa_date_coerenti`,
`iniziativa_codice_key`); qui servono a dare un messaggio chiaro prima di
scrivere. L'acronimo non ha vincolo di unicità a DB, ma è la chiave con cui
l'import e la riconciliazione agganciano i movimenti bancari al progetto:
due progetti con lo stesso acronimo renderebbero ambigua la riconciliazione.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def valida_nuovo_progetto(
    titolo: str | None,
    acronimo: str | None,
    codice: str | None,
    inizio: date | None,
    fine: date | None,
    acronimi_esistenti: Iterable[str],
    codici_esistenti: Iterable[str] = (),
) -> str | None:
    """Messaggio d'errore in italiano, oppure None se i dati sono validi."""
    if not (titolo or "").strip():
        return "Il titolo è obbligatorio."
    if inizio and fine and fine < inizio:
        return "La data di fine non può precedere quella di inizio."
    acr = (acronimo or "").strip().lower()
    if acr and acr in {a.strip().lower() for a in acronimi_esistenti if a}:
        return (
            f"Esiste già un'iniziativa con acronimo «{acronimo.strip()}»: "
            "l'acronimo serve a riconciliare i movimenti bancari, usane uno diverso."
        )
    cod = (codice or "").strip().lower()
    if cod and cod in {c.strip().lower() for c in codici_esistenti if c}:
        return (
            f"Esiste già un'iniziativa con identificativo «{codice.strip()}»: "
            "usane uno diverso o lascia il campo vuoto."
        )
    return None
