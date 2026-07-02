"""Regole di dominio del timesheet (spec §5)."""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.timesheet import (
    AssegnazioneInfo,
    giorni_del_mese,
    is_lavorativo,
    riga_valida,
    valida_griglia,
)

A1 = AssegnazioneInfo(
    id="a1",
    titolo="Progetto X",
    tipo_attivita="RI",
    tetto_ore_mese=40,
    data_inizio=date(2026, 1, 1),
    data_fine=date(2026, 12, 31),
)
A2 = AssegnazioneInfo(id="a2", titolo="Progetto Y", tipo_attivita="SS")
ASSEGN = {"a1": A1, "a2": A2}
FESTIVI = {date(2026, 6, 2)}  # Festa della Repubblica (martedì)


def test_griglia_valida_semplice():
    ore = {("a1", date(2026, 6, 1)): 4, ("a2", date(2026, 6, 1)): 4}
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert esito.valido


def test_tetto_giornaliero_8h():
    # 5 + 4 = 9 > 8 sullo stesso giorno (regola 2)
    ore = {("a1", date(2026, 6, 1)): 5, ("a2", date(2026, 6, 1)): 4}
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido
    assert any("tetto giornaliero" in e for e in esito.errori)


def test_tetto_mensile_riga():
    # 6 giorni x 7h = 42 > tetto 40 della riga a1 (regola 3)
    ore = {("a1", date(2026, 6, g)): 7 for g in (1, 3, 4, 5, 8, 9)}
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido
    assert any("Max mese" in e for e in esito.errori)
    assert not riga_valida(ore, A1)


def test_blocco_mese_confermato():
    ore = {("a1", date(2026, 6, 1)): 2}
    esito = valida_griglia(ore, ASSEGN, FESTIVI, stato_mese="confermato")
    assert not esito.valido
    assert any("confermato" in e for e in esito.errori)


def test_weekend_escluso_senza_flag():
    sabato = date(2026, 6, 6)
    assert sabato.isoweekday() == 6
    ore = {("a1", sabato): 3}
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido
    assert any("non lavorativo" in e for e in esito.errori)
    # con il flag esplicito passa (regola 4)
    assert valida_griglia(ore, ASSEGN, FESTIVI, forza_non_lavorativi=True).valido


def test_festivita_esclusa_senza_flag():
    ore = {("a1", date(2026, 6, 2)): 3}  # festivo infrasettimanale
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido


def test_data_fuori_intervallo_iniziativa():
    ore = {("a1", date(2027, 1, 4)): 3}  # oltre data_fine 31/12/2026
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido
    assert any("fine iniziativa" in e for e in esito.errori)


def test_ore_non_intere_rifiutate():
    ore = {("a1", date(2026, 6, 1)): 2.5}  # type: ignore[dict-item]
    esito = valida_griglia(ore, ASSEGN, FESTIVI)
    assert not esito.valido


@pytest.mark.parametrize(
    ("anno", "mese", "n"), [(2026, 2, 28), (2028, 2, 29), (2026, 6, 30)]
)
def test_giorni_del_mese(anno, mese, n):
    gg = giorni_del_mese(anno, mese)
    assert len(gg) == n
    assert gg[0].day == 1


def test_is_lavorativo():
    assert is_lavorativo(date(2026, 6, 1), FESTIVI)  # lunedì
    assert not is_lavorativo(date(2026, 6, 6), FESTIVI)  # sabato
    assert not is_lavorativo(date(2026, 6, 2), FESTIVI)  # festivo
