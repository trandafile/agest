"""Calcoli economici (spec §6/§7) — pure Python, testabili.

Regola aurea (agents.md): il costo del personale usa SEMPRE la tariffa
vigente alla data dell'attivita', mai una tariffa "corrente" fissa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.domain.models import TariffaOraria
from src.domain.tariffe import tariffa_vigente

ORE_FTE_ANNO = Decimal("1720")  # soglia capacity di default (FTE annuo)


@dataclass(frozen=True)
class PianoPersona:
    """Assegnazione pianificata (proposta): persona + ore previste."""

    persona_id: str
    nome: str
    tipo_attivita: str
    ore: Decimal
    work_package: str | None = None  # etichetta WP (opzionale)


def costo_pianificato(
    piano: PianoPersona,
    tariffe_by_persona: dict[str, list[TariffaOraria]],
    alla_data: date,
) -> Decimal | None:
    """Costo di un'assegnazione pianificata = ore x tariffa vigente alla data.

    None se la persona non ha tariffa vigente (da segnalare in UI).
    """
    t = tariffa_vigente(tariffe_by_persona.get(piano.persona_id, []), alla_data)
    if t is None:
        return None
    return piano.ore * t.importo_orario


def rollup_personale(
    piani: list[PianoPersona],
    tariffe_by_persona: dict[str, list[TariffaOraria]],
    alla_data: date,
) -> dict:
    """Roll-up costi personale: per persona, per WP (se usati), totale.

    Ritorna {"per_persona": {...}, "per_wp": {...}, "totale": Decimal,
             "senza_tariffa": [nomi]}.
    """
    per_persona: dict[str, Decimal] = {}
    per_wp: dict[str, Decimal] = {}
    senza_tariffa: list[str] = []
    totale = Decimal("0")
    for p in piani:
        costo = costo_pianificato(p, tariffe_by_persona, alla_data)
        if costo is None:
            if p.nome not in senza_tariffa:
                senza_tariffa.append(p.nome)
            continue
        per_persona[p.nome] = per_persona.get(p.nome, Decimal("0")) + costo
        chiave_wp = p.work_package or "(nessun WP)"
        per_wp[chiave_wp] = per_wp.get(chiave_wp, Decimal("0")) + costo
        totale += costo
    return {
        "per_persona": per_persona,
        "per_wp": per_wp,
        "totale": totale,
        "senza_tariffa": senza_tariffa,
    }


def valore_atteso(budget: Decimal | None, probabilita: Decimal | None) -> Decimal:
    """Pipeline pesata: valore atteso = budget x probabilita' di successo."""
    if budget is None or probabilita is None:
        return Decimal("0")
    return (budget * probabilita).quantize(Decimal("0.01"))


def capacity_per_persona(
    ore_pianificate: list[tuple[str, str, Decimal]],
    soglia: Decimal = ORE_FTE_ANNO,
) -> list[dict]:
    """Capacity check: somma ore pianificate per persona su proposte+progetti attivi.

    `ore_pianificate`: [(persona_id, nome, ore)]. Ritorna righe ordinate per
    carico decrescente con flag `sovrallocata` se oltre la soglia.
    """
    acc: dict[str, dict] = {}
    for pid, nome, ore in ore_pianificate:
        r = acc.setdefault(pid, {"persona_id": pid, "nome": nome, "ore": Decimal("0")})
        r["ore"] += ore or Decimal("0")
    out = sorted(acc.values(), key=lambda r: r["ore"], reverse=True)
    for r in out:
        r["soglia"] = soglia
        r["sovrallocata"] = r["ore"] > soglia
    return out


def consuntivo_personale(
    ore_registrate: list[tuple[str, date, int]],
    tariffe_by_persona: dict[str, list[TariffaOraria]],
) -> Decimal:
    """Costo consuntivo = Σ(ore x tariffa vigente ALLA DATA dell'attivita').

    `ore_registrate`: [(persona_id, data, ore)] dai timesheet.
    Le ore senza tariffa vigente valgono 0 (segnalarle a parte se serve).
    """
    tot = Decimal("0")
    for pid, giorno, ore in ore_registrate:
        t = tariffa_vigente(tariffe_by_persona.get(pid, []), giorno)
        if t is not None:
            tot += Decimal(ore) * t.importo_orario
    return tot


def quote_rimanenti(
    budget: dict[str, Decimal],
    impegnato: dict[str, Decimal],
    speso: dict[str, Decimal],
) -> dict[str, dict[str, Decimal]]:
    """Quote rimanenti per categoria = budget − impegnato − speso (spec §7)."""
    out: dict[str, dict[str, Decimal]] = {}
    for cat in set(budget) | set(impegnato) | set(speso):
        b = budget.get(cat, Decimal("0"))
        i = impegnato.get(cat, Decimal("0"))
        s = speso.get(cat, Decimal("0"))
        out[cat] = {
            "budget": b,
            "impegnato": i,
            "speso": s,
            "rimanente": b - i - s,
        }
    return out
