"""Portfolio pluriennale: pro-rata per anno/mese, carico, saturazione, ricavi."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.portfolio import (
    RigaCarico,
    anni_portfolio,
    carico_per_anno,
    disponibilita_anno,
    giorni_per_anno,
    quota_per_anno,
    quota_per_mese,
    ricavi_per_anno,
    tabella_saturazione,
)


def test_giorni_per_anno_a_cavallo():
    g = giorni_per_anno(date(2025, 12, 30), date(2026, 1, 2))
    assert g == {2025: 2, 2026: 2}


def test_giorni_per_anno_intervallo_invalido():
    assert giorni_per_anno(None, date(2026, 1, 1)) == {}
    assert giorni_per_anno(date(2026, 2, 1), date(2026, 1, 1)) == {}


def test_quota_per_anno_somma_esatta():
    q = quota_per_anno(date(2025, 3, 1), date(2027, 3, 1), Decimal("675000"))
    assert set(q) == {2025, 2026, 2027}
    assert sum(q.values()) == Decimal("675000.00")
    # 2026 è l'anno pieno: deve pesare più del 2025 (mar-dic) e del 2027 (2 mesi)
    assert q[2026] > q[2025] > q[2027]


def test_quota_per_anno_zero():
    assert quota_per_anno(date(2026, 1, 1), date(2026, 12, 31), 0) == {
        2026: Decimal("0")
    }


def test_quota_per_mese_somma_esatta():
    q = quota_per_mese(date(2026, 1, 15), date(2026, 3, 15), Decimal("1000"))
    assert set(q) == {(2026, 1), (2026, 2), (2026, 3)}
    assert sum(q.values()) == Decimal("1000.00")


def _ass(**kw):
    base = {
        "assegnazione_id": "a1",
        "persona_id": "p1",
        "nome": "Luigi",
        "iniziativa_id": "i1",
        "etichetta": "CASCADE",
        "tipo": "progetto",
        "stato": "attivo",
        "probabilita": None,
        "data_inizio": date(2025, 1, 1),
        "data_fine": date(2026, 12, 31),
        "ore_pianificate": Decimal("2000"),
    }
    base.update(kw)
    return base


def test_carico_pro_rata_quando_manca_il_piano():
    righe = carico_per_anno([_ass()])
    assert [r.anno for r in righe] == [2025, 2026]
    assert sum(r.ore for r in righe) == Decimal("2000.0")
    assert all(not r.esplicito for r in righe)


def test_carico_piano_esplicito_vince_sul_pro_rata():
    piani = {("a1", 2025): Decimal("750"), ("a1", 2026): Decimal("1000")}
    righe = carico_per_anno([_ass()], piani)
    assert {r.anno: r.ore for r in righe} == {
        2025: Decimal("750"),
        2026: Decimal("1000"),
    }
    assert all(r.esplicito for r in righe)


def test_carico_proposta_porta_probabilita():
    righe = carico_per_anno(
        [_ass(tipo="proposta", stato="inviata", probabilita=Decimal("0.5"))]
    )
    assert all(r.probabilita == Decimal("0.5") for r in righe)


def test_disponibilita_anno_pro_rata_contratto():
    assert disponibilita_anno(1720, 2026) == Decimal("1720.0")
    # contratto che inizia a metà anno: circa metà delle ore
    mezzo = disponibilita_anno(1720, 2026, date(2026, 7, 2), None)
    assert Decimal("850") < mezzo < Decimal("870")
    # contratto scaduto prima dell'anno
    assert disponibilita_anno(1720, 2026, date(2020, 1, 1), date(2025, 12, 31)) == 0
    assert disponibilita_anno(0, 2026) == 0


def test_tabella_saturazione_distingue_impegnate_e_potenziali():
    righe = [
        RigaCarico(
            "p1",
            "Luigi",
            "i1",
            "CASCADE",
            "progetto",
            "attivo",
            Decimal(1),
            2026,
            Decimal("1000"),
            False,
        ),
        RigaCarico(
            "p1",
            "Luigi",
            "i2",
            "ESA_Ka",
            "proposta",
            "inviata",
            Decimal("0.5"),
            2026,
            Decimal("800"),
            False,
        ),
        RigaCarico(
            "p1",
            "Luigi",
            "i3",
            "CHIUSO",
            "progetto",
            "chiuso",
            Decimal(1),
            2026,
            Decimal("999"),
            False,
        ),
    ]
    persone = [{"id": "p1", "nome": "Luigi", "monte_ore_annuo": 1522}]
    tab = tabella_saturazione(righe, persone, [2026, 2027])
    r26 = next(r for r in tab if r["anno"] == 2026)
    assert r26["impegnate"] == Decimal("1000")
    assert r26["potenziali"] == Decimal("400.0")  # 800 × 0.5
    assert r26["disponibili"] == Decimal("1522.0")
    assert r26["saturazione"] == Decimal("92")
    assert not r26["sovrallocata"]
    r27 = next(r for r in tab if r["anno"] == 2027)
    assert r27["impegnate"] == 0 and r27["saturazione"] == 0


def test_tabella_saturazione_flag_sovrallocata():
    righe = [
        RigaCarico(
            "p1",
            "L",
            "i1",
            "A",
            "progetto",
            "attivo",
            Decimal(1),
            2026,
            Decimal("1800"),
            False,
        )
    ]
    tab = tabella_saturazione(
        righe, [{"id": "p1", "nome": "L", "monte_ore_annuo": 1720}], [2026]
    )
    assert tab[0]["sovrallocata"] and tab[0]["libere"] < 0


def test_ricavi_per_anno_pesa_le_proposte():
    ini = [
        {
            "id": "i1",
            "etichetta": "CASCADE",
            "tipo": "progetto",
            "stato": "attivo",
            "importo": Decimal("120000"),
            "probabilita": None,
            "data_inizio": date(2026, 1, 1),
            "data_fine": date(2026, 12, 31),
            "tipo_ricavo": "agevolato",
            "controparte": "ESA",
        },
        {
            "id": "i2",
            "etichetta": "KA",
            "tipo": "proposta",
            "stato": "inviata",
            "importo": Decimal("100000"),
            "probabilita": Decimal("0.5"),
            "data_inizio": date(2026, 1, 1),
            "data_fine": date(2026, 12, 31),
            "tipo_ricavo": "mercato",
            "controparte": "ACME",
        },
        {
            "id": "i3",
            "etichetta": "RIF",
            "tipo": "proposta",
            "stato": "rifiutata",
            "importo": Decimal("999"),
            "probabilita": Decimal("1"),
            "data_inizio": date(2026, 1, 1),
            "data_fine": date(2026, 12, 31),
        },
    ]
    righe = ricavi_per_anno(ini)
    per_id = {r["iniziativa_id"]: r for r in righe}
    assert "i3" not in per_id
    assert per_id["i1"]["importo"] == Decimal("120000.00")
    assert per_id["i2"]["importo"] == Decimal("50000.00")
    assert per_id["i2"]["importo_pieno"] == Decimal("100000.00")
    non_pesati = {r["iniziativa_id"]: r for r in ricavi_per_anno(ini, pesati=False)}
    assert non_pesati["i2"]["importo"] == Decimal("100000.00")


def test_anni_portfolio_include_anno_corrente():
    anni = anni_portfolio(
        [{"data_inizio": date(2023, 9, 1), "data_fine": date(2025, 9, 1)}],
        oggi=date(2026, 9, 5),
    )
    assert anni == [2023, 2024, 2025, 2026]
    assert anni_portfolio([], oggi=date(2026, 1, 1)) == [2026]
