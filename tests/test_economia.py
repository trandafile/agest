"""Calcoli economici (spec §6/§7): roll-up, pipeline, capacity, quote."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.economia import (
    PianoPersona,
    capacity_per_persona,
    consuntivo_personale,
    quote_rimanenti,
    rollup_personale,
    valore_atteso,
)
from src.domain.models import TariffaOraria

D = Decimal
ALLA_DATA = date(2026, 3, 1)

TARIFFE = {
    "p1": [TariffaOraria(valido_da=date(2024, 1, 1), importo_orario=D("35"))],
    "p2": [
        TariffaOraria(
            valido_da=date(2023, 1, 1),
            valido_al=date(2025, 12, 31),
            importo_orario=D("30"),
        ),
        TariffaOraria(valido_da=date(2026, 1, 1), importo_orario=D("40")),
    ],
}


def _piani() -> list[PianoPersona]:
    return [
        PianoPersona("p1", "Mario Rossi", "RI", D("100"), "WP1"),
        PianoPersona("p1", "Mario Rossi", "SS", D("50"), "WP2"),
        PianoPersona("p2", "Anna Verdi", "RI", D("80"), None),
    ]


def test_rollup_per_persona_wp_totale():
    roll = rollup_personale(_piani(), TARIFFE, ALLA_DATA)
    # Mario: 150h x 35 = 5250 ; Anna: 80h x 40 (tariffa 2026!) = 3200
    assert roll["per_persona"]["Mario Rossi"] == D("5250")
    assert roll["per_persona"]["Anna Verdi"] == D("3200")
    assert roll["per_wp"]["WP1"] == D("3500")
    assert roll["per_wp"]["WP2"] == D("1750")
    assert roll["per_wp"]["(nessun WP)"] == D("3200")
    assert roll["totale"] == D("8450")
    assert roll["senza_tariffa"] == []


def test_rollup_segnala_persona_senza_tariffa():
    piani = [PianoPersona("px", "Zeta Kappa", "RI", D("10"))]
    roll = rollup_personale(piani, TARIFFE, ALLA_DATA)
    assert roll["totale"] == D("0")
    assert roll["senza_tariffa"] == ["Zeta Kappa"]


def test_valore_atteso_pipeline():
    assert valore_atteso(D("100000"), D("0.6")) == D("60000.00")
    assert valore_atteso(None, D("0.6")) == D("0")
    assert valore_atteso(D("100000"), None) == D("0")


def test_capacity_somma_e_sovrallocazione():
    righe = [
        ("p1", "Mario Rossi", D("900")),
        ("p1", "Mario Rossi", D("900")),  # 1800 > 1720 -> sovrallocata
        ("p2", "Anna Verdi", D("500")),
    ]
    cap = capacity_per_persona(righe)
    mario = next(r for r in cap if r["persona_id"] == "p1")
    anna = next(r for r in cap if r["persona_id"] == "p2")
    assert mario["ore"] == D("1800") and mario["sovrallocata"]
    assert anna["ore"] == D("500") and not anna["sovrallocata"]
    assert cap[0]["persona_id"] == "p1"  # ordinato per carico


def test_consuntivo_usa_tariffa_vigente_alla_data():
    ore = [
        ("p2", date(2025, 6, 1), 8),  # tariffa 30 -> 240
        ("p2", date(2026, 2, 2), 8),  # tariffa 40 -> 320
    ]
    assert consuntivo_personale(ore, TARIFFE) == D("560")


def test_quote_rimanenti():
    quote = quote_rimanenti(
        budget={"personale": D("10000"), "materiali": D("2000")},
        impegnato={"personale": D("4000")},
        speso={"personale": D("3000"), "missioni": D("500")},
    )
    assert quote["personale"]["rimanente"] == D("3000")
    assert quote["materiali"]["rimanente"] == D("2000")
    # categoria solo a consuntivo: budget 0 -> rimanente negativo (overrun)
    assert quote["missioni"]["rimanente"] == D("-500")
