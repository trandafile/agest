"""Creazione diretta di un progetto: validazione + scrittura (spec §13.11).

Sta fuori dalla pagina perché la logica deve essere testabile senza interfaccia
(il dialog Streamlit non si può pilotare nei test automatici). La pagina
raccoglie i campi, chiama `crea_progetto` e mostra l'errore o il successo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.data import iniziativa_repo
from src.domain.models import Iniziativa
from src.domain.nuovo_progetto import valida_nuovo_progetto
from src.lib.errori import messaggio_errore_db


def crea_progetto(
    *,
    titolo: str,
    acronimo: str | None = None,
    codice: str | None = None,
    controparte: str | None = None,
    inizio: date | None = None,
    fine: date | None = None,
    finanziamento: float | Decimal | None = None,
    costo: float | Decimal | None = None,
    budget: float | Decimal | None = None,
    responsabile_id=None,
    tipo_ricavo: str = "agevolato",
    cup: str | None = None,
    monthly_report: bool = False,
) -> tuple[Iniziativa | None, str | None]:
    """Crea un progetto attivo. Ritorna (progetto, None) oppure (None, errore).

    L'errore è già in italiano: viene dalla validazione o, se il database
    rifiuta comunque la scrittura, dalla traduzione del vincolo violato.
    """
    esistenti = iniziativa_repo.list_iniziative()
    errore = valida_nuovo_progetto(
        titolo,
        acronimo,
        codice,
        inizio,
        fine,
        acronimi_esistenti=[i.acronimo for i in esistenti if i.acronimo],
        codici_esistenti=[i.codice for i in esistenti if i.codice],
    )
    if errore:
        return None, errore
    try:
        nuovo = iniziativa_repo.create_iniziativa(
            tipo="progetto",
            stato="attivo",
            titolo=titolo.strip(),
            acronimo=(acronimo or "").strip() or None,
            codice=(codice or "").strip() or None,
            controparte=(controparte or "").strip() or None,
            data_inizio=inizio,
            data_fine=fine,
            finanziamento_complessivo=finanziamento or None,
            costo_complessivo=costo or None,
            budget_totale=budget or None,
            responsabile_id=responsabile_id,
            tipo_ricavo=tipo_ricavo,
            cup=(cup or "").strip() or None,
            monthly_report=monthly_report,
        )
    except Exception as exc:  # noqa: BLE001
        return None, messaggio_errore_db(exc)
    return nuovo, None
