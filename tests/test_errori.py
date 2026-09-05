"""Traduzione degli errori del DB in messaggi leggibili."""

from __future__ import annotations

from src.lib.errori import GENERICO, MESSAGGI, messaggio_errore_db


class _Diag:
    def __init__(self, nome):
        self.constraint_name = nome


class _ErroreConDiag(Exception):
    def __init__(self, nome):
        super().__init__("errore oscurato")
        self.diag = _Diag(nome)


def test_riconosce_il_vincolo_dal_testo():
    exc = Exception(
        'new row for relation "iniziativa" violates check constraint '
        '"iniziativa_date_coerenti"'
    )
    assert "data di fine" in messaggio_errore_db(exc)


def test_riconosce_il_vincolo_dalla_diagnostica():
    # Streamlit Cloud oscura il testo: resta l'attributo diag di psycopg
    msg = messaggio_errore_db(_ErroreConDiag("iniziativa_codice_key"))
    assert "Identificativo" in msg


def test_messaggio_generico_se_sconosciuto():
    assert GENERICO in messaggio_errore_db(Exception("boom"))
    assert GENERICO in messaggio_errore_db(_ErroreConDiag("vincolo_ignoto"))


def test_tutti_i_messaggi_hanno_testo():
    assert all(v.strip() for v in MESSAGGI.values())
    assert messaggio_errore_db(ValueError()).startswith("⚠️")
