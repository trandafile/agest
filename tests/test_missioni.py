"""Missioni: totali automatici, scostamento, transizioni di stato, modelli."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.models import Commento, Missione, MissioneSpesa
from src.lib.missioni import (
    puo_autorizzare,
    puo_inviare_richiesta,
    puo_richiedere_rimborso,
    riepilogo,
    scostamento,
    spese_per_categoria,
    totale_spese,
)


def _missione(**kw) -> Missione:
    base = dict(
        persona_id=uuid4(),
        destinazione="Milano",
        data_inizio=date(2026, 9, 1),
        data_fine=date(2026, 9, 3),
        spesa_prevista=Decimal("500.00"),
    )
    base.update(kw)
    return Missione(**base)


def _spesa(importo, categoria="altro", giorno=1) -> MissioneSpesa:
    return MissioneSpesa(
        missione_id=uuid4(),
        data=date(2026, 9, giorno),
        categoria=categoria,
        importo=Decimal(str(importo)),
    )


# --- Modello ----------------------------------------------------------------


def test_periodo_e_giorni():
    m = _missione()
    assert m.giorni == 3
    assert m.periodo == "01/09/2026 → 03/09/2026"


def test_periodo_di_un_solo_giorno():
    m = _missione(data_fine=date(2026, 9, 1))
    assert m.giorni == 1 and m.periodo == "01/09/2026"


def test_data_fine_non_puo_precedere_inizio():
    with pytest.raises(ValidationError):
        _missione(data_fine=date(2026, 8, 30))


def test_modificabile_solo_in_bozza_o_respinta():
    assert _missione(stato="bozza").modificabile
    assert _missione(stato="respinta").modificabile
    assert not _missione(stato="richiesta").modificabile
    assert not _missione(stato="autorizzata").modificabile


def test_autorizzata_include_conclusa():
    assert _missione(stato="autorizzata").autorizzata
    assert _missione(stato="conclusa").autorizzata
    assert not _missione(stato="richiesta").autorizzata


# --- Totali -----------------------------------------------------------------


def test_totale_spese_vuoto():
    assert totale_spese([]) == Decimal("0.00")


def test_totale_spese_somma_automatica():
    spese = [_spesa("120.50"), _spesa("79.50"), _spesa("300")]
    assert totale_spese(spese) == Decimal("500.00")


def test_spese_per_categoria():
    spese = [
        _spesa("100", "viaggio"),
        _spesa("50", "viaggio"),
        _spesa("80", "vitto"),
    ]
    per_cat = spese_per_categoria(spese)
    assert per_cat == {"viaggio": Decimal("150.00"), "vitto": Decimal("80.00")}


def test_scostamento_positivo_e_negativo():
    assert scostamento(Decimal("500"), Decimal("620.00")) == Decimal("120.00")
    assert scostamento(Decimal("500"), Decimal("430.00")) == Decimal("-70.00")


def test_scostamento_none_senza_preventivo():
    assert scostamento(None, Decimal("100.00")) is None


# --- Transizioni ------------------------------------------------------------


def test_puo_inviare_richiesta():
    assert puo_inviare_richiesta(_missione(stato="bozza"))
    assert puo_inviare_richiesta(_missione(stato="respinta"))
    assert not puo_inviare_richiesta(_missione(stato="autorizzata"))


def test_puo_autorizzare_solo_se_richiesta():
    assert puo_autorizzare(_missione(stato="richiesta"))
    assert not puo_autorizzare(_missione(stato="bozza"))
    assert not puo_autorizzare(_missione(stato="autorizzata"))


def test_rimborso_richiedibile_solo_se_autorizzata_e_con_spese():
    m = _missione(stato="autorizzata")
    assert puo_richiedere_rimborso(m, Decimal("120.00"))
    assert not puo_richiedere_rimborso(m, Decimal("0.00"))  # nessuna spesa
    assert not puo_richiedere_rimborso(
        _missione(stato="bozza"), Decimal("120.00")
    )  # non autorizzata


def test_rimborso_non_richiedibile_due_volte():
    m = _missione(stato="autorizzata", rimborso_stato="richiesto")
    assert not puo_richiedere_rimborso(m, Decimal("120.00"))


def test_riepilogo_completo():
    m = _missione(stato="autorizzata")
    spese = [_spesa("400", "viaggio"), _spesa("180", "alloggio")]
    r = riepilogo(m, spese)
    assert r["totale"] == Decimal("580.00")
    assert r["n_spese"] == 2
    assert r["scostamento"] == Decimal("80.00")
    assert r["rimborsabile"] is True
    assert r["per_categoria"]["viaggio"] == Decimal("400.00")


# --- Commenti ---------------------------------------------------------------


def test_commento_modificato_falso_appena_creato():
    from datetime import datetime

    t = datetime(2026, 7, 2, 10, 0, 0)
    c = Commento(
        entita="task", entita_id=uuid4(), testo="ciao", created_at=t, updated_at=t
    )
    assert c.modificato is False


def test_commento_modificato_vero_dopo_update():
    from datetime import datetime

    c = Commento(
        entita="task",
        entita_id=uuid4(),
        testo="ciao",
        created_at=datetime(2026, 7, 2, 10, 0, 0),
        updated_at=datetime(2026, 7, 2, 10, 5, 0),
    )
    assert c.modificato is True
