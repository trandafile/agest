"""Sostenibilità economica: spese periodiche, scenari, KPI, utile e tasse."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.finanza import prossimi_mesi
from src.domain.models import TariffaOraria
from src.domain.sostenibilita import (
    costo_personale_mese,
    costo_pieno_orario,
    entrate_pipeline_mensili,
    espandi_spese_periodiche,
    kpi_autonomia,
    kpi_backlog_coverage,
    kpi_concentrazione_clienti,
    kpi_margine,
    kpi_quota_mercato,
    kpi_ricorrenti,
    kpi_tariffa_costo,
    mesi_periodicita,
    primo_mese_negativo,
    proiezione_scenari,
    saldo_minimo,
    stima_utile_tasse,
    tariffa_media_progetti,
    totali_per_anno,
)


def test_mesi_periodicita():
    assert mesi_periodicita("Mensile") == 1
    assert mesi_periodicita("trimestrale") == 3
    assert mesi_periodicita("Annuale") == 12
    assert mesi_periodicita("una tantum") is None
    assert mesi_periodicita(None) is None


def test_espandi_spese_periodiche_mensile_e_trimestrale():
    mesi = prossimi_mesi(date(2026, 1, 1), 6)
    spese = [
        {"descrizione": "Noleggio auto", "importo": 2700, "periodicita": "Mensile"},
        {
            "descrizione": "Commercialista",
            "importo": 900,
            "periodicita": "Trimestrale",
            "dal": date(2025, 11, 1),
            "al": date(2026, 4, 30),
        },
        {"descrizione": "Boh", "importo": 100, "periodicita": "quando capita"},
    ]
    out, ignorate = espandi_spese_periodiche(spese, mesi)
    assert [s["descrizione"] for s in ignorate] == ["Boh"]
    assert all(out[m] >= Decimal("2700") for m in mesi)
    # trimestrale da nov 2025: feb 2026 (entro `al`), maggio 2026 NO (oltre `al`)
    assert out[(2026, 2)] == Decimal("3600")
    assert out[(2026, 5)] == Decimal("2700")
    assert out[(2026, 1)] == Decimal("2700")


def test_espandi_spese_periodiche_orizzonte_vuoto():
    assert espandi_spese_periodiche([{"importo": 1, "periodicita": "mensile"}], []) == (
        {},
        [],
    )


def test_costo_personale_mese_rispetta_contratti_e_tariffe():
    persone = [
        {"id": "p1", "attivo": True, "monte_ore_annuo": 1720},
        {
            "id": "p2",
            "attivo": True,
            "monte_ore_annuo": 1200,
            "contratto_data_inizio": date(2026, 7, 1),
            "contratto_data_fine": date(2026, 12, 31),
        },
        {"id": "p3", "attivo": False, "monte_ore_annuo": 1720},
    ]
    tariffe = {
        "p1": [TariffaOraria(valido_da=date(2024, 1, 1), importo_orario=Decimal("30"))],
        "p2": [TariffaOraria(valido_da=date(2024, 1, 1), importo_orario=Decimal("20"))],
        "p3": [TariffaOraria(valido_da=date(2024, 1, 1), importo_orario=Decimal("99"))],
    }
    # marzo: solo p1 (p2 non ancora in forza, p3 inattiva)
    assert costo_personale_mese(persone, tariffe, 2026, 3) == Decimal("4300.00")
    # settembre: p1 + p2
    assert costo_personale_mese(persone, tariffe, 2026, 9) == Decimal("6300.00")


def test_entrate_pipeline_pesate_e_intere():
    mesi = prossimi_mesi(date(2026, 1, 1), 12)
    proposte = [
        {
            "importo": Decimal("120000"),
            "probabilita": Decimal("0.5"),
            "data_inizio": date(2026, 1, 1),
            "data_fine": date(2026, 12, 31),
            "stato": "inviata",
        },
        {
            "importo": 1000,
            "probabilita": 1,
            "stato": "rifiutata",
            "data_inizio": date(2026, 1, 1),
            "data_fine": date(2026, 1, 31),
        },
    ]
    pesate = entrate_pipeline_mensili(proposte, mesi)
    intere = entrate_pipeline_mensili(proposte, mesi, pesate=False)
    assert sum(pesate.values()) == Decimal("60000.00")
    assert sum(intere.values()) == Decimal("120000.00")


def test_proiezione_scenari_ordinati():
    mesi = prossimi_mesi(date(2026, 1, 1), 3)
    sc = proiezione_scenari(
        saldo_iniziale=Decimal("10000"),
        mesi=mesi,
        entrate_firmate={(2026, 2): Decimal("5000")},
        uscite_programmate={(2026, 1): Decimal("1000")},
        uscite_base=Decimal("6000"),
        pipeline_pesata={(2026, 3): Decimal("3000")},
        pipeline_intera={(2026, 3): Decimal("6000")},
    )
    assert set(sc) == {"firmato", "pesato", "ottimista"}
    f, p, o = sc["firmato"], sc["pesato"], sc["ottimista"]
    assert f[0]["saldo"] == Decimal("3000")  # 10000 - 1000 - 6000
    assert f[1]["saldo"] == Decimal("2000")  # + 5000 - 6000
    assert f[2]["saldo"] == Decimal("-4000")
    assert p[2]["saldo"] == Decimal("-1000")
    assert o[2]["saldo"] == Decimal("2000")
    assert primo_mese_negativo(f) == (2026, 3)
    assert primo_mese_negativo(o) is None
    assert saldo_minimo(p) == (Decimal("-1000"), (2026, 3))
    tot = totali_per_anno(f)
    assert tot[0]["anno"] == 2026 and tot[0]["entrate"] == Decimal("5000")
    assert tot[0]["uscite"] == Decimal("19000") and tot[0]["saldo_fine"] == Decimal(
        "-4000"
    )


def test_proiezione_scenari_uscite_base_per_mese():
    mesi = prossimi_mesi(date(2026, 1, 1), 2)
    sc = proiezione_scenari(0, mesi, {}, {}, {(2026, 1): Decimal("100")}, {}, {})
    assert sc["firmato"][0]["saldo"] == Decimal("-100")
    assert sc["firmato"][1]["saldo"] == Decimal("-100")


def test_kpi_soglie():
    assert kpi_autonomia(60000, 10000).stato == "attenzione"  # 6 mesi
    assert kpi_autonomia(30000, 10000).stato == "allarme"
    assert kpi_autonomia(130000, 10000).stato == "ok"
    assert kpi_autonomia(1, 0).stato == "nd"
    assert kpi_backlog_coverage(100000, 10000).stato == "attenzione"  # 10 mesi
    assert kpi_backlog_coverage(50000, 10000).stato == "allarme"
    assert kpi_backlog_coverage(150000, 10000).stato == "ok"
    k = kpi_concentrazione_clienti({"ESA": 800, "ASI": 100, "X": 50, "Y": 50})
    assert k.valore == Decimal("95.0") and k.stato == "allarme"
    assert (
        kpi_concentrazione_clienti({"A": 50, "B": 50, "C": 50, "D": 50, "E": 50}).stato
        == "ok"
    )
    assert (
        kpi_quota_mercato({"agevolato": 70, "mercato": 20, "ricorrente": 10}).stato
        == "allarme"
    )
    assert kpi_quota_mercato({"agevolato": 20, "mercato": 80}).stato == "ok"
    assert kpi_ricorrenti({"agevolato": 50, "ricorrente": 50}).stato == "ok"
    assert kpi_ricorrenti({}).stato == "nd"
    assert kpi_margine(100, 120).stato == "allarme"
    assert kpi_margine(100, 95).stato == "attenzione"
    assert kpi_margine(100, 80).stato == "ok"
    assert kpi_tariffa_costo(100, 80).stato == "allarme"
    assert kpi_tariffa_costo(160, 100).stato == "ok"
    assert kpi_tariffa_costo(160, 0).stato == "nd"


def test_kpi_testo_e_semaforo():
    k = kpi_autonomia(130000, 10000)
    assert k.valore_txt == "13.0 mesi" and k.semaforo == "🟢"
    assert kpi_quota_mercato({}).valore_txt == "n.d."
    assert kpi_tariffa_costo(160, 100).valore_txt == "1.60×"


def test_costo_pieno_orario_come_foglio_costo_personale():
    # Foglio 2025: (131845 + 37231) / (2.44 × 1620) ≈ 42.8 €/h  (voci semplificate)
    c = costo_pieno_orario(131845, 37231, Decimal("2.44"), 1620)
    assert Decimal("42") < c < Decimal("43")
    assert costo_pieno_orario(1000, 0, 0, 1620) is None
    assert costo_pieno_orario(0, 0, 2, 1620) is None


def test_tariffa_media_progetti():
    t = tariffa_media_progetti(
        [
            {"importo": 100000, "ore": 1000},
            {"importo": 50000, "ore": 250},
            {"importo": 999, "ore": 0},
        ]
    )
    assert t == Decimal("120.00")
    assert tariffa_media_progetti([]) is None


def test_stima_utile_tasse():
    s = stima_utile_tasse(500000, 300000, 100000, 50000, Decimal("0.279"))
    assert s["utile_lordo"] == Decimal("250000.00")
    assert s["tasse_stimate"] == Decimal("69750.00")
    assert s["utile_netto"] == Decimal("180250.00")
    perdita = stima_utile_tasse(100, 200, 0, 0, Decimal("0.279"))
    assert perdita["tasse_stimate"] == 0 and perdita["utile_netto"] == Decimal(
        "-100.00"
    )
