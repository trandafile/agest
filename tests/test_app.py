"""Flusso principale via streamlit AppTest.

Verifica la GUARDIA di login (stile MAIC tasks): senza sessione autenticata la
home si ferma alla schermata di accesso (st.stop) senza sollevare eccezioni e
senza mostrare contenuto riservato.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from streamlit.testing.v1 import AppTest  # noqa: E402


def _login_page(secrets: dict | None = None) -> AppTest:
    # percorso assoluto: con Streamlit recenti un percorso relativo è risolto
    # rispetto alla cartella del test (tests/app.py) e non viene trovato
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    at.run()
    return at


def test_home_richiede_login():
    at = _login_page({"GOOGLE_CLIENT_ID": "x.apps.googleusercontent.com"})
    assert not at.exception
    # Si ferma alla schermata di login: titolo + invito, nessun "Ciao".
    titoli = " ".join(t.value for t in at.title)
    assert "ANTECNICA" in titoli
    corpo = " ".join(i.value for i in at.info).lower()
    assert "google" in corpo or "accedi" in corpo
    assert not any("Ciao" in m.value for m in at.markdown)


def test_home_senza_credenziali_mostra_mock_solo_se_abilitato():
    # Senza GOOGLE_CLIENT_ID il mock login compare SOLO con MOCK_LOGIN esplicito
    # (client_id vuoto per neutralizzare l'eventuale secrets.toml locale)
    at = _login_page({"GOOGLE_CLIENT_ID": "", "MOCK_LOGIN": "1"})
    assert not at.exception
    labels = [b.label for b in at.button]
    assert any("MOCK" in lbl for lbl in labels)


def test_home_senza_credenziali_niente_mock_in_produzione():
    at = _login_page({"GOOGLE_CLIENT_ID": "", "MOCK_LOGIN": ""})
    assert not at.exception
    assert not any("MOCK" in b.label for b in at.button)
    assert any("non configurato" in e.value for e in at.error)
