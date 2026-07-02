"""Descrizione del contratto sulla Persona (logica di dominio)."""

from __future__ import annotations

from datetime import date

from src.domain.models import Persona, RuoloSistema, TipoContratto


def _p(**kw) -> Persona:
    base = dict(
        nome="Mario",
        cognome="Rossi",
        email="m@antecnica.it",
        ruolo_sistema=RuoloSistema.dipendente,
    )
    base.update(kw)
    return Persona(**base)


def test_nessun_contratto():
    assert _p().contratto_descr == "—"


def test_determinato_con_intervallo():
    p = _p(
        tipo_contratto=TipoContratto.tempo_determinato,
        contratto_data_inizio=date(2026, 1, 1),
        contratto_data_fine=date(2026, 12, 31),
    )
    assert p.contratto_descr == "Tempo determinato (01/01/2026→31/12/2026)"


def test_indeterminato_solo_inizio():
    p = _p(
        tipo_contratto=TipoContratto.tempo_indeterminato,
        contratto_data_inizio=date(2025, 3, 1),
    )
    assert p.contratto_descr == "Tempo indeterminato (dal 01/03/2025)"


def test_socio_senza_date():
    assert _p(tipo_contratto=TipoContratto.socio).contratto_descr == "Socio"
