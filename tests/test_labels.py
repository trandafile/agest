"""Helper etichette difensivi (tolleranti a modelli disallineati)."""

from __future__ import annotations

from datetime import date

from src.lib.labels import contratto_descr, etichetta_progetto, getf


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


def test_contratto_descr_degrada_su_modello_vecchio():
    # persona "vecchia" senza campi contratto -> nessun crash
    assert contratto_descr(_Vecchio()) == "—"


def test_contratto_descr_completo():
    class P:
        tipo_contratto = "tempo_determinato"
        contratto_data_inizio = date(2026, 1, 1)
        contratto_data_fine = date(2026, 12, 31)

    assert contratto_descr(P()) == "Tempo determinato (01/01/2026→31/12/2026)"


def test_contratto_descr_solo_inizio():
    class P:
        tipo_contratto = "tempo_indeterminato"
        contratto_data_inizio = date(2025, 3, 1)
        contratto_data_fine = None

    assert contratto_descr(P()) == "Tempo indeterminato (dal 01/03/2025)"
