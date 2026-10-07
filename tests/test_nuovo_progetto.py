"""Validazione della creazione diretta di un progetto."""

from __future__ import annotations

from datetime import date

from src.domain.nuovo_progetto import valida_nuovo_progetto

ES_ACR = ["CASCADE", "IOT", ""]
ES_COD = ["ESA-1", "SPIN CHIP"]


def _v(**kw):
    base = dict(
        titolo="Nuovo progetto",
        acronimo="NUOVO",
        codice="N-1",
        inizio=date(2026, 10, 1),
        fine=date(2027, 9, 30),
        acronimi_esistenti=ES_ACR,
        codici_esistenti=ES_COD,
    )
    base.update(kw)
    return valida_nuovo_progetto(**base)


def test_dati_validi():
    assert _v() is None
    # date e codici facoltativi
    assert _v(inizio=None, fine=None, codice=None, acronimo=None) is None


def test_titolo_obbligatorio():
    assert "titolo" in _v(titolo="   ")
    assert "titolo" in _v(titolo=None)


def test_fine_prima_dell_inizio():
    assert "data di fine" in _v(inizio=date(2026, 12, 1), fine=date(2026, 1, 1))
    # una sola data non basta a violare la regola
    assert _v(inizio=date(2026, 12, 1), fine=None) is None


def test_acronimo_duplicato_senza_distinguere_maiuscole():
    msg = _v(acronimo=" cascade ")
    assert msg and "acronimo" in msg and "cascade" in msg
    assert _v(acronimo="") is None  # vuoto non è un duplicato


def test_codice_duplicato():
    msg = _v(codice="esa-1")
    assert msg and "identificativo" in msg
