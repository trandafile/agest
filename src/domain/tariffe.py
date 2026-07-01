"""Regole di dominio sulle tariffe orarie versionate.

Requisito di rendicontazione (project-specifications.md §4/§5, trappola in
agents.md): il costo delle ore va SEMPRE calcolato con la tariffa vigente alla
data dell'attivita', non con una tariffa "corrente" fissa.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.domain.models import TariffaOraria


def tariffa_vigente(
    tariffe: Iterable[TariffaOraria], quando: date
) -> TariffaOraria | None:
    """Ritorna la tariffa vigente alla data `quando`, o None se nessuna copre.

    Se piu' periodi coprono la data (non dovrebbe accadere: a DB c'e' il vincolo
    di non-sovrapposizione), sceglie quello con `valido_da` piu' recente.
    """
    candidate = [t for t in tariffe if t.copre(quando)]
    if not candidate:
        return None
    return max(candidate, key=lambda t: t.valido_da)


def costo_ore(
    tariffe: Iterable[TariffaOraria], quando: date, ore: Decimal | float | int
) -> Decimal | None:
    """Costo di `ore` alla data `quando` = ore x tariffa vigente.

    Ritorna None se nessuna tariffa copre la data (impossibile valorizzare).
    """
    t = tariffa_vigente(tariffe, quando)
    if t is None:
        return None
    return Decimal(str(ore)) * t.importo_orario
