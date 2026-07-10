"""Logica pura delle missioni: totali, scostamenti, transizioni di stato.

Nessun accesso al DB e nessun widget: tutto qui e' testabile in isolamento.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.models import CATEGORIE_SPESA_MISSIONE

_ZERO = Decimal("0.00")


def totale_spese(spese) -> Decimal:
    """Somma degli importi delle spese sostenute (calcolo automatico)."""
    tot = sum((Decimal(str(s.importo)) for s in spese), _ZERO)
    return Decimal(tot).quantize(Decimal("0.01"))


def spese_per_categoria(spese) -> dict[str, Decimal]:
    """{categoria: totale}, solo categorie con almeno una spesa."""
    out: dict[str, Decimal] = {}
    for s in spese:
        cat = s.categoria if s.categoria in CATEGORIE_SPESA_MISSIONE else "altro"
        out[cat] = out.get(cat, _ZERO) + Decimal(str(s.importo))
    return {k: v.quantize(Decimal("0.01")) for k, v in out.items()}


def scostamento(spesa_prevista, totale: Decimal) -> Decimal | None:
    """Speso - previsto. Positivo = sforamento. None se non c'e' un preventivo."""
    if spesa_prevista is None:
        return None
    return (totale - Decimal(str(spesa_prevista))).quantize(Decimal("0.01"))


def puo_richiedere_rimborso(missione, totale: Decimal) -> bool:
    """Rimborso richiedibile solo se autorizzata, con spese e non gia' richiesto."""
    return bool(
        missione.stato in ("autorizzata", "conclusa")
        and totale > _ZERO
        and missione.rimborso_stato == "non_richiesto"
    )


def puo_autorizzare(missione) -> bool:
    """Un admin autorizza solo cio' che e' stato effettivamente richiesto."""
    return missione.stato == "richiesta"


def puo_inviare_richiesta(missione) -> bool:
    """Si invia in autorizzazione una bozza (o una respinta, dopo correzioni)."""
    return missione.stato in ("bozza", "respinta")


def riepilogo(missione, spese) -> dict:
    """Riepilogo economico della missione, pronto per la UI."""
    tot = totale_spese(spese)
    return {
        "totale": tot,
        "per_categoria": spese_per_categoria(spese),
        "scostamento": scostamento(missione.spesa_prevista, tot),
        "n_spese": len(spese),
        "rimborsabile": puo_richiedere_rimborso(missione, tot),
    }
