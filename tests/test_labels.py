"""Helper etichette difensivi (tolleranti a modelli disallineati)."""

from __future__ import annotations

from src.lib.labels import etichetta_progetto, getf


class _Vecchio:
    """Simula un `models.py` deployato senza i campi recenti."""

    titolo = "Progetto Storico"


class _Nuovo:
    titolo = "Progetto Nuovo"
    acronimo = "PRJN"
    codice = "P-9"


def test_etichetta_degrada_senza_acronimo():
    # non deve sollevare AttributeError: fallback su titolo
    assert etichetta_progetto(_Vecchio()) == "Progetto Storico"


def test_etichetta_usa_acronimo_poi_codice():
    assert etichetta_progetto(_Nuovo()) == "PRJN · Progetto Nuovo"


def test_etichetta_fallback_su_codice():
    class SoloCodice:
        titolo = "T"
        codice = "C-1"

    assert etichetta_progetto(SoloCodice()) == "C-1 · T"


def test_getf_sicuro():
    v = _Vecchio()
    assert getf(v, "acronimo") is None
    assert getf(v, "costo_complessivo", 0) == 0
    assert getf(v, "titolo") == "Progetto Storico"
