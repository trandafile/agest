"""Import/normalizzazione finanza + export rendicontazione (spec §8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.finanza import (
    normalizza_documento,
    normalizza_movimento,
    parse_data,
    parse_importo,
    tabella_rendicontazione,
)
from src.domain.models import TariffaOraria

D = Decimal


def test_parse_importo_formati():
    assert parse_importo("1.234,56") == D("1234.56")
    assert parse_importo("€ 1.234,56") == D("1234.56")
    assert parse_importo("1,234.56") == D("1234.56")
    assert parse_importo("-500") == D("-500")
    assert parse_importo("12,5") == D("12.5")
    assert parse_importo(1234.56) == D("1234.56")
    assert parse_importo("") is None
    assert parse_importo("n/a") is None


def test_parse_data_formati():
    assert parse_data("31/12/2025") == date(2025, 12, 31)
    assert parse_data("2025-12-31") == date(2025, 12, 31)
    assert parse_data("31.12.2025") == date(2025, 12, 31)
    assert parse_data(date(2025, 1, 2)) == date(2025, 1, 2)
    assert parse_data("boh") is None


def test_normalizza_movimento_con_segno_esplicito():
    riga = {
        "Data": "05/03/2026",
        "Importo": "1.000,00",
        "E/U": "U",
        "Causale": "Acquisto",
        "Chi": "Fornitore Srl",
    }
    mappa = {
        "data": "Data",
        "importo": "Importo",
        "segno": "E/U",
        "descrizione": "Causale",
        "controparte": "Chi",
    }
    out = normalizza_movimento(riga, mappa)
    assert out == {
        "data": date(2026, 3, 5),
        "importo": D("1000.00"),
        "segno": "uscita",
        "descrizione": "Acquisto",
        "controparte": "Fornitore Srl",
    }


def test_normalizza_movimento_segno_da_importo():
    riga = {"Data": "05/03/2026", "Importo": "-250,00"}
    out = normalizza_movimento(riga, {"data": "Data", "importo": "Importo"})
    assert out["segno"] == "uscita" and out["importo"] == D("250.00")


def test_normalizza_movimento_scarta_righe_incomplete():
    assert (
        normalizza_movimento(
            {"Data": "", "Importo": "10"}, {"data": "Data", "importo": "Importo"}
        )
        is None
    )
    assert (
        normalizza_movimento(
            {"Data": "01/01/2026", "Importo": "x"},
            {"data": "Data", "importo": "Importo"},
        )
        is None
    )


def test_normalizza_documento():
    riga = {
        "Tipo": "emessa",
        "N": "FT-12",
        "Data": "10/02/2026",
        "Importo": "5.000,00",
        "Cliente": "ACME",
        "Pagata": "sì",
        "Scad": "10/04/2026",
    }
    mappa = {
        "tipo": "Tipo",
        "numero": "N",
        "data": "Data",
        "importo": "Importo",
        "controparte": "Cliente",
        "stato_incasso_pagamento": "Pagata",
        "data_scadenza": "Scad",
    }
    out = normalizza_documento(riga, mappa)
    assert out["tipo"] == "attiva"
    assert out["numero"] == "FT-12"
    assert out["stato_incasso_pagamento"] == "saldato"
    assert out["data_scadenza"] == date(2026, 4, 10)


def test_tabella_rendicontazione_tariffa_alla_data():
    tariffe = {
        "p1": [
            TariffaOraria(
                valido_da=date(2025, 1, 1),
                valido_al=date(2025, 12, 31),
                importo_orario=D("30"),
            ),
            TariffaOraria(valido_da=date(2026, 1, 1), importo_orario=D("40")),
        ]
    }
    ore = [
        {
            "persona_id": "p1",
            "persona": "Mario Rossi",
            "iniziativa": "PRJ",
            "tipo_attivita": "RI",
            "data": date(2025, 6, 2),
            "ore": 8,
        },
        {
            "persona_id": "p1",
            "persona": "Mario Rossi",
            "iniziativa": "PRJ",
            "tipo_attivita": "RI",
            "data": date(2026, 2, 2),
            "ore": 8,
        },
    ]
    tab = tabella_rendicontazione(ore, tariffe)
    assert tab[0]["Costo €"] == 240.0  # 8 x 30 (tariffa 2025)
    assert tab[1]["Costo €"] == 320.0  # 8 x 40 (tariffa 2026)


def test_tabella_rendicontazione_senza_tariffa():
    tab = tabella_rendicontazione(
        [
            {
                "persona_id": "px",
                "persona": "X",
                "iniziativa": "PRJ",
                "tipo_attivita": "SS",
                "data": date(2026, 1, 5),
                "ore": 4,
            }
        ],
        {},
    )
    assert tab[0]["Costo €"] is None and tab[0]["Tariffa €/h"] is None
