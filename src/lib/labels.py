"""Etichette/accessi difensivi ai modelli.

Modulo volutamente **stabile** (cambia di rado): le pagine leggono i campi
dei modelli tramite questi helper basati su `getattr`, così un deploy con un
`models.py` disallineato (campo/proprietà non ancora presente) degrada senza
schiantare la pagina, invece di sollevare AttributeError.
"""

from __future__ import annotations

from typing import Any


def getf(obj: Any, name: str, default: Any = None) -> Any:
    """`getattr` sicuro: ritorna `default` se l'attributo non esiste."""
    return getattr(obj, name, default)


def etichetta_progetto(i: Any) -> str:
    """Etichetta breve di un'iniziativa/progetto: «ACRONIMO · Titolo».

    Tollerante a modelli privi di `acronimo`/`codice` (fallback su `titolo`).
    """
    prefisso = getattr(i, "acronimo", None) or getattr(i, "codice", None)
    titolo = getattr(i, "titolo", "") or ""
    return f"{prefisso} · {titolo}" if prefisso else titolo
