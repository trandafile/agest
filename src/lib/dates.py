"""Utility su date."""

from __future__ import annotations

from datetime import date


def oggi() -> date:
    """Data odierna (wrapper per facilitare i test / il mocking)."""
    return date.today()


def formatta_data(d: date | None) -> str:
    """Formato italiano gg/mm/aaaa; stringa vuota se None."""
    return d.strftime("%d/%m/%Y") if d else ""
