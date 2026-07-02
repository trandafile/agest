"""Utility per il calendario: griglia mensile ed export ICS (pure, testabili)."""

from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

TIPO_ICONA = {"task": "✅", "deliverable": "📦", "milestone": "🎯"}


def settimane_mese(anno: int, mese: int) -> list[list[date | None]]:
    """Matrice del mese (settimane lun→dom); celle fuori mese = None."""
    cal = _cal.Calendar(firstweekday=0)  # lunedì
    settimane: list[list[date | None]] = []
    for week in cal.monthdatescalendar(anno, mese):
        settimane.append([d if d.month == mese else None for d in week])
    return settimane


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(eventi: list[dict], nome_cal: str = "ANTECNICA") -> str:
    """Genera un file ICS (VCALENDAR) da eventi con `data` e `titolo`.

    Ogni evento diventa un VEVENT giornaliero (DTSTART;VALUE=DATE).
    """
    righe = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{nome_cal}//Gestionale//IT",
        "CALSCALE:GREGORIAN",
    ]
    for i, e in enumerate(eventi):
        d: date = e["data"]
        icona = TIPO_ICONA.get(e.get("tipo", ""), "")
        titolo = f"{icona} {e.get('titolo', '')}".strip()
        prog = e.get("progetto")
        summary = f"{titolo} [{prog}]" if prog else titolo
        righe += [
            "BEGIN:VEVENT",
            f"UID:agest-{e.get('tipo','x')}-{i}-{d.isoformat()}@antecnica",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(summary)}",
            "END:VEVENT",
        ]
    righe.append("END:VCALENDAR")
    return "\r\n".join(righe) + "\r\n"


def eventi_per_giorno(eventi: list[dict]) -> dict[date, list[dict]]:
    out: dict[date, list[dict]] = {}
    for e in eventi:
        out.setdefault(e["data"], []).append(e)
    return out


def link_google_calendar(titolo: str, giorno: date, descrizione: str = "") -> str:
    """URL «Aggiungi a Google Calendar» per un evento giornaliero.

    Apre il calendario dell'utente già compilato (nessuna API/chiave).
    """
    from urllib.parse import urlencode

    fine = giorno + timedelta(days=1)
    params = {
        "action": "TEMPLATE",
        "text": titolo,
        "dates": f"{giorno.strftime('%Y%m%d')}/{fine.strftime('%Y%m%d')}",
        "details": descrizione or "",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)
