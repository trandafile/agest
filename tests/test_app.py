"""Flusso principale via streamlit AppTest.

Verifica la GUARDIA di login: senza utente autenticato, la home mostra il
pulsante di accesso e non prosegue (st.stop). Non richiede il database perche'
il percorso "non loggato" si ferma prima di qualsiasi accesso ai dati.
"""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_home_richiede_login():
    at = AppTest.from_file("app.py")
    at.secrets["app"] = {"allowed_email_domain": "antecnica.it"}
    at.run()
    assert not at.exception
    # Non loggato: compare l'invito ad accedere con Google.
    testo = " ".join([i.value for i in at.info] + [b.label for b in at.button]).lower()
    assert "google" in testo
