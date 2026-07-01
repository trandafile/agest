"""Regole di dominio sulle tariffe versionate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.domain.models import TariffaOraria
from src.domain.tariffe import costo_ore, tariffa_vigente


def _t(da: str, al: str | None, imp: str) -> TariffaOraria:
    return TariffaOraria(
        valido_da=date.fromisoformat(da),
        valido_al=date.fromisoformat(al) if al else None,
        importo_orario=Decimal(imp),
    )


@pytest.fixture
def tariffe() -> list[TariffaOraria]:
    # 2023 chiusa (30), 2024-> aperta (35)
    return [_t("2023-01-01", "2023-12-31", "30.00"), _t("2024-01-01", None, "35.00")]


def test_vigente_nel_periodo_chiuso(tariffe):
    t = tariffa_vigente(tariffe, date(2023, 6, 15))
    assert t is not None and t.importo_orario == Decimal("30.00")


def test_vigente_nel_periodo_aperto(tariffe):
    t = tariffa_vigente(tariffe, date(2025, 3, 1))
    assert t is not None and t.importo_orario == Decimal("35.00")


def test_confine_inclusi(tariffe):
    fine_2023 = tariffa_vigente(tariffe, date(2023, 12, 31))
    inizio_2024 = tariffa_vigente(tariffe, date(2024, 1, 1))
    assert fine_2023.importo_orario == Decimal("30.00")
    assert inizio_2024.importo_orario == Decimal("35.00")


def test_prima_di_ogni_tariffa_none(tariffe):
    assert tariffa_vigente(tariffe, date(2022, 12, 31)) is None


def test_buco_temporale_none():
    tariffe = [_t("2023-01-01", "2023-06-30", "30.00"), _t("2024-01-01", None, "35.00")]
    assert tariffa_vigente(tariffe, date(2023, 9, 1)) is None


def test_costo_ore_usa_tariffa_vigente(tariffe):
    # 10 ore nel 2023 -> 300 ; 10 ore nel 2025 -> 350
    assert costo_ore(tariffe, date(2023, 5, 1), 10) == Decimal("300.00")
    assert costo_ore(tariffe, date(2025, 5, 1), 10) == Decimal("350.00")


def test_costo_ore_senza_tariffa_none(tariffe):
    assert costo_ore(tariffe, date(2000, 1, 1), 8) is None
