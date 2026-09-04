"""Due livelli di visibilità (spec §13.1)."""

from __future__ import annotations

from types import SimpleNamespace

from src.auth.visibilita import (
    MATRICE_VISIBILITA,
    Livello,
    livello,
    pagine_visibili,
    vede_economia,
    vede_progetto_operativo,
)
from src.domain.models import RuoloSistema


def test_livelli():
    assert livello(RuoloSistema.admin) is Livello.amministratore
    assert livello(RuoloSistema.pm) is Livello.dipendente
    assert livello(RuoloSistema.dipendente) is Livello.dipendente
    assert livello("admin") is Livello.amministratore


def test_economia_solo_amministratore():
    assert vede_economia(RuoloSistema.admin)
    assert not vede_economia(RuoloSistema.pm)
    assert not vede_economia(RuoloSistema.dipendente)


def test_vista_operativa_pm_solo_se_responsabile():
    ini = SimpleNamespace(responsabile_id="p1")
    assert vede_progetto_operativo(RuoloSistema.admin, "x", ini)
    assert vede_progetto_operativo(RuoloSistema.pm, "p1", ini)
    assert not vede_progetto_operativo(RuoloSistema.pm, "p2", ini)
    assert not vede_progetto_operativo(RuoloSistema.dipendente, "p1", ini)


def test_matrice_finanza_riservata():
    dip = set(pagine_visibili(RuoloSistema.dipendente))
    adm = set(pagine_visibili(RuoloSistema.admin))
    assert adm == set(MATRICE_VISIBILITA)
    for riservata in (
        "Finanza",
        "Sostenibilità",
        "Proposte",
        "Anagrafica",
        "Import banca",
    ):
        assert riservata not in dip
    assert {"Dashboard", "Task", "Timesheet", "Portfolio (senza importi)"} <= dip
