"""Notifiche task: selezione, deduplica e rendering (senza SMTP né DB)."""

from __future__ import annotations

from datetime import date

from src.lib.notifiche import (
    ConfigSMTP,
    deve_inviare_briefing,
    html_briefing,
    html_scaduto,
    invia,
    scaduti_ieri,
    seleziona_briefing,
)

OGGI = date(2026, 9, 7)  # lunedì


def _t(**kw):
    base = {
        "id": "t",
        "titolo": "Task",
        "stato": "in_corso",
        "scadenza": None,
        "owner_id": "p1",
        "supervisor_id": None,
        "completato_il": None,
        "last_reminder_sent": None,
        "progetto": "CASCADE",
    }
    base.update(kw)
    return base


def test_config_da_ambiente_e_dry_run():
    cfg = ConfigSMTP.da_ambiente({})
    assert not cfg.configurato and cfg.port == 587
    cfg = ConfigSMTP.da_ambiente(
        {"SMTP_HOST": "smtp.x", "SMTP_USER": "u", "SMTP_PASSWORD": "p"}
    )
    assert cfg.configurato and cfg.mittente == "u"
    cfg = ConfigSMTP.da_ambiente(
        {
            "SMTP_HOST": "smtp.x",
            "SMTP_USER": "u",
            "SMTP_PASSWORD": "p",
            "NOTIFICHE_ATTIVE": "0",
        }
    )
    assert not cfg.configurato
    # senza configurazione non invia e non solleva
    assert invia(ConfigSMTP(), "a@b.it", "s", "<b>x</b>", "x") is False


def test_deve_inviare_briefing_dedup_settimana_iso():
    assert deve_inviare_briefing(OGGI, None)
    assert not deve_inviare_briefing(OGGI, date(2026, 9, 7))
    assert not deve_inviare_briefing(date(2026, 9, 9), date(2026, 9, 7))
    assert deve_inviare_briefing(OGGI, date(2026, 8, 31))


def test_seleziona_briefing():
    tasks = [
        _t(id="1", titolo="Scaduto", scadenza=date(2026, 9, 1)),
        _t(id="2", titolo="Presto", scadenza=date(2026, 9, 15)),
        _t(id="3", titolo="Lontano", scadenza=date(2026, 12, 1)),
        _t(id="4", titolo="Fatto", stato="completato", completato_il=date(2026, 9, 4)),
        _t(
            id="5",
            titolo="Altrui bloccato",
            owner_id="p2",
            supervisor_id="p1",
            stato="bloccato",
        ),
        _t(id="6", titolo="Altrui", owner_id="p2"),
    ]
    s = seleziona_briefing(tasks, "p1", OGGI)
    assert [t["titolo"] for t in s["scaduti"]] == ["Scaduto"]
    assert [t["titolo"] for t in s["in_scadenza"]] == ["Presto"]
    assert [t["titolo"] for t in s["da_sbloccare"]] == ["Altrui bloccato"]
    assert [t["titolo"] for t in s["attivi"]] == ["Scaduto", "Presto", "Lontano"]
    assert [t["titolo"] for t in s["completati"]] == ["Fatto"]


def test_scaduti_ieri_dedup_per_task():
    tasks = [
        _t(id="1", scadenza=date(2026, 9, 6)),
        _t(id="2", scadenza=date(2026, 9, 6), last_reminder_sent=date(2026, 9, 7)),
        _t(id="3", scadenza=date(2026, 9, 5)),
        _t(id="4", scadenza=date(2026, 9, 6), stato="completato"),
    ]
    assert [t["id"] for t in scaduti_ieri(tasks, OGGI)] == ["1"]


def test_rendering_html_e_testo():
    sez = seleziona_briefing(
        [_t(id="1", titolo="A <b>", scadenza=date(2026, 9, 1))], "p1", OGGI
    )
    h, t = html_briefing("Luigi", sez, OGGI, "https://app")
    assert (
        "Briefing settimanale" in h and "A &lt;b&gt;" in h and "in ritardo di 6 g" in h
    )
    assert "https://app" in t and "SCADUTI (1)" in t
    h2, t2 = html_scaduto(
        "Luigi", _t(titolo="X", scadenza=date(2026, 9, 6)), OGGI, "https://app"
    )
    assert "06/09/2026" in h2 and "06/09/2026" in t2
