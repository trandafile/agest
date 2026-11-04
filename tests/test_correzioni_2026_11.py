"""Regressioni corrette nella revisione 11/2026."""

from datetime import date
from decimal import Decimal

from src.domain.finanza import parse_importo
from src.lib.import_contabile import _vero, parse_spese_periodiche
from src.lib.notifiche import scaduti_ieri


def test_importi_con_separatore_migliaia():
    assert parse_importo("1.500") == Decimal("1500")
    assert parse_importo("1.234.567") == Decimal("1234567")
    assert parse_importo("1.234,56") == Decimal("1234.56")
    assert parse_importo("0.500") == Decimal("0.500")
    assert parse_importo("1.5") == Decimal("1.5")


def test_spese_periodiche_colonna_al_non_confusa_con_dal():
    r = parse_spese_periodiche([
        ["Descrizione", "Importo", "Periodicità", "Dal", "Al"],
        ["Affitto", "1.000", "mensile", "2025-01-01", "2027-12-31"],
    ])
    assert r[0]["dal"] == date(2025, 1, 1) and r[0]["al"] == date(2027, 12, 31)


def test_cella_completata_testuale():
    assert not _vero("No") and not _vero("FALSE") and not _vero(0)
    assert _vero("Sì") and _vero("x") and _vero(True)


def test_promemoria_scadenza_spostata_e_di_nuovo_mancata():
    oggi = date(2026, 11, 4)
    ieri = date(2026, 11, 3)
    mai = {"stato": "in_corso", "scadenza": ieri, "last_reminder_sent": None}
    vecchio = {"stato": "in_corso", "scadenza": ieri,
               "last_reminder_sent": date(2026, 10, 2)}
    gia = {"stato": "in_corso", "scadenza": ieri, "last_reminder_sent": oggi}
    out = scaduti_ieri([mai, vecchio, gia], oggi)
    assert mai in out and vecchio in out and gia not in out
