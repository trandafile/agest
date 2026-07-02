"""Etichette/accessi difensivi ai modelli.

Modulo volutamente **stabile** (cambia di rado): le pagine leggono i campi
dei modelli tramite questi helper basati su `getattr`, così un deploy con un
`models.py` disallineato (campo/proprietà non ancora presente) degrada senza
schiantare la pagina, invece di sollevare AttributeError.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_VERSION_FILE = Path(__file__).resolve().parents[2] / ".upload_version.txt"


def versione_app() -> str:
    """Versione del software da `.upload_version.txt` (scritta dallo script di
    upload). Ritorna stringa vuota se il file non c'è."""
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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


def etichetta_con_tag(i: Any) -> str:
    """Come `etichetta_progetto`, ma antepone «📝 Proposta:» se è una proposta."""
    tag = "📝 Proposta: " if getattr(i, "tipo", None) == "proposta" else ""
    return tag + etichetta_progetto(i)


_TIPO_CONTRATTO_LABEL = {
    "tempo_determinato": "Tempo determinato",
    "tempo_indeterminato": "Tempo indeterminato",
    "socio": "Socio",
}


def contratto_descr(p: Any) -> str:
    """Descrizione del contratto di una persona, tollerante a modelli vecchi
    (campi contratto assenti -> «—»)."""
    tipo = getattr(p, "tipo_contratto", None)
    if not tipo:
        return "—"
    val = getattr(tipo, "value", None) or str(tipo)
    base = _TIPO_CONTRATTO_LABEL.get(val, val)
    da = getattr(p, "contratto_data_inizio", None)
    al = getattr(p, "contratto_data_fine", None)
    if da and al:
        return f"{base} ({da:%d/%m/%Y}→{al:%d/%m/%Y})"
    if da:
        return f"{base} (dal {da:%d/%m/%Y})"
    return base
