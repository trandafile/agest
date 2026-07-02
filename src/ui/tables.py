"""Componenti tabellari riusabili (Streamlit)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.domain.models import Persona, TariffaOraria
from src.domain.tariffe import tariffa_vigente
from src.lib.dates import formatta_data, oggi
from src.lib.labels import contratto_descr


def persone_dataframe(persone: list[Persona]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Nome": p.nome,
                "Cognome": p.cognome,
                "Matricola": p.matricola or "",
                "Email": p.email,
                "Ruolo": getattr(p.ruolo_sistema, "value", str(p.ruolo_sistema)),
                "Contratto": contratto_descr(p),
                "Attivo": "si" if p.attivo else "no",
            }
            for p in persone
        ]
    )


def tariffe_dataframe(
    tariffe: list[TariffaOraria], riferimento: date | None = None
) -> pd.DataFrame:
    riferimento = riferimento or oggi()
    vigente = tariffa_vigente(tariffe, riferimento)
    vigente_id = vigente.id if vigente else None
    return pd.DataFrame(
        [
            {
                "Da": formatta_data(t.valido_da),
                "A": formatta_data(t.valido_al) or "aperto",
                "€/ora": f"{t.importo_orario:.2f}",
                "Vigente oggi": "●" if t.id == vigente_id else "",
            }
            for t in tariffe
        ]
    )
