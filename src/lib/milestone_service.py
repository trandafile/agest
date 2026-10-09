"""Milestone e incassi: collegamento esplicito e opzionale (spec §13.13).

Una milestone PUÒ determinare uno o più incassi (o pagamenti) del calendario
dei movimenti previsti; un incasso PUÒ non avere nessuna milestone. Il legame
è `movimento_previsto.milestone_id`; i campi `genera_pagamento` e
`importo_incasso` della milestone sono derivati dai movimenti collegati (li
tiene allineati un trigger del database).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from src.data import finanza_repo, progetti_repo
from src.domain.models import Milestone


def crea_milestone(
    iniziativa_id: UUID | str,
    titolo: str,
    data_prevista: date | None,
    incasso: float | None = None,
    data_incasso: date | None = None,
) -> Milestone:
    """Crea la milestone e, se `incasso` > 0, l'incasso collegato.

    L'incasso nasce nel calendario dei movimenti previsti, alla data indicata
    (altrimenti alla data della milestone). Senza `incasso` la milestone resta
    senza alcun pagamento.
    """
    ms = progetti_repo.create_milestone(iniziativa_id, titolo, data_prevista)
    if incasso and incasso > 0:
        finanza_repo.create_movimento_previsto(
            iniziativa_id,
            segno="entrata",
            importo=incasso,
            descrizione=titolo,
            data_attesa=data_incasso or data_prevista,
            milestone_id=ms.id,
        )
    return ms


def aggiungi_incasso(
    milestone: Milestone,
    importo: float,
    data_attesa: date | None = None,
    descrizione: str | None = None,
    segno: str = "entrata",
) -> None:
    """Aggiunge un movimento collegato a una milestone esistente."""
    finanza_repo.create_movimento_previsto(
        milestone.iniziativa_id,
        segno=segno,
        importo=importo,
        descrizione=descrizione or milestone.titolo,
        data_attesa=data_attesa or milestone.data_prevista,
        milestone_id=milestone.id,
    )


def collega(movimento_id: UUID | str, milestone_id: UUID | str | None) -> None:
    """Collega un movimento a una milestone (None = nessuna milestone)."""
    finanza_repo.collega_movimento_milestone(movimento_id, milestone_id)
