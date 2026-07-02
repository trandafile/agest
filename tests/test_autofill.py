"""Autofill del timesheet (8h/giorno distribuite tra le assegnazioni)."""

from __future__ import annotations

from datetime import date

from src.domain.timesheet import (
    AssegnazioneInfo,
    autofill_mese,
    giorni_del_mese,
    is_lavorativo,
    valida_griglia,
)

FESTIVI = {date(2026, 6, 2)}  # martedì festivo


def _info(aid: str, tetto: float | None = None, **kw) -> AssegnazioneInfo:
    return AssegnazioneInfo(id=aid, titolo=aid, tetto_ore_mese=tetto, **kw)


def test_due_righe_senza_tetto_split_4_4():
    ass = {"a": _info("a"), "b": _info("b")}
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    lavorativi = [g for g in giorni_del_mese(2026, 6) if is_lavorativo(g, FESTIVI)]
    # ogni giorno lavorativo pieno: 8h totali, 4+4
    for g in lavorativi:
        assert celle.get(("a", g), 0) + celle.get(("b", g), 0) == 8
        assert celle.get(("a", g), 0) == 4
    # weekend/festivi vuoti
    assert all(g in lavorativi for (_, g) in celle)


def test_riga_singola_8h_al_giorno():
    ass = {"a": _info("a")}
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    assert all(v == 8 for v in celle.values())


def test_rispetta_tetto_mensile():
    # tetto 20h sulla riga a: il resto va sulla riga b
    ass = {"a": _info("a", tetto=20), "b": _info("b")}
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    tot_a = sum(v for (aid, _), v in celle.items() if aid == "a")
    assert tot_a == 20
    # b assorbe il resto: ogni giorno lavorativo resta a 8h totali
    lavorativi = [g for g in giorni_del_mese(2026, 6) if is_lavorativo(g, FESTIVI)]
    for g in lavorativi:
        assert celle.get(("a", g), 0) + celle.get(("b", g), 0) == 8


def test_tutti_i_tetti_esauriti_giorni_parziali():
    ass = {"a": _info("a", tetto=10)}
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    assert sum(celle.values()) == 10  # niente oltre il tetto


def test_rispetta_intervallo_iniziativa():
    ass = {
        "a": _info("a", data_inizio=date(2026, 6, 15)),
        "b": _info("b", data_fine=date(2026, 6, 10)),
    }
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    assert all(g >= date(2026, 6, 15) for (aid, g) in celle if aid == "a")
    assert all(g <= date(2026, 6, 10) for (aid, g) in celle if aid == "b")


def test_autofill_passa_la_validazione():
    ass = {"a": _info("a", tetto=100), "b": _info("b")}
    celle = autofill_mese(2026, 6, ass, FESTIVI)
    esito = valida_griglia(celle, ass, FESTIVI)
    assert esito.valido, esito.errori
