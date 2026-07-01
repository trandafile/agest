"""Guardie di ruolo (logica pura)."""

from __future__ import annotations

from src.auth.guards import can_access, is_allowed_email
from src.domain.models import RuoloSistema


def test_dipendente_non_accede_pagine_admin():
    assert can_access(RuoloSistema.dipendente, [RuoloSistema.admin]) is False


def test_admin_accede_a_tutto():
    assert can_access(RuoloSistema.admin, [RuoloSistema.admin]) is True
    assert can_access(RuoloSistema.admin, [RuoloSistema.pm]) is True
    assert can_access(RuoloSistema.admin, [RuoloSistema.dipendente]) is True


def test_pm_accede_solo_a_pagine_pm():
    assert can_access(RuoloSistema.pm, [RuoloSistema.admin, RuoloSistema.pm]) is True
    assert can_access(RuoloSistema.pm, [RuoloSistema.admin]) is False


def test_required_singolo_ruolo():
    assert can_access(RuoloSistema.dipendente, RuoloSistema.dipendente) is True
    assert can_access(RuoloSistema.dipendente, RuoloSistema.admin) is False


def test_dominio_email_consentito():
    assert is_allowed_email("Luigi.Boccia@antecnica.it", "antecnica.it") is True
    assert is_allowed_email("tizio@gmail.com", "antecnica.it") is False
    assert is_allowed_email(None, "antecnica.it") is False
    assert is_allowed_email("", "antecnica.it") is False
