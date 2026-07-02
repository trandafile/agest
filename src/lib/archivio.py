"""Salvataggio di un file in archivio: DB (persistente) + Google Drive (opz.)."""

from __future__ import annotations

import hashlib

from src.data import finanza_repo
from src.lib import gdrive


def salva_documento(
    categoria: str,
    nome: str,
    contenuto: bytes,
    mime: str | None = None,
    anno: int | None = None,
    mese: int | None = None,
    descrizione: str | None = None,
    iniziativa_id=None,
    documento_id=None,
    caricato_da: str | None = None,
) -> dict:
    """Carica il file su **Google Drive** e conserva nel DB solo il metadato +
    il link (i PDF NON vanno nel database). Ritorna
    {"salvato": bool, "gia_presente": bool, "gdrive": url|None, "errore": str|None}.
    """
    file_hash = hashlib.sha256(contenuto).hexdigest()
    if finanza_repo.file_archivio_esiste(file_hash):
        return {"salvato": False, "gia_presente": True, "gdrive": None, "errore": None}

    if not gdrive.configurato():
        return {
            "salvato": False,
            "gia_presente": False,
            "gdrive": None,
            "errore": "Google Drive non configurato (vedi istruzioni).",
        }
    url = gdrive.salva_su_drive(nome, contenuto, mime or "application/pdf")
    if not url:
        return {
            "salvato": False,
            "gia_presente": False,
            "gdrive": None,
            "errore": "Upload su Google Drive non riuscito.",
        }

    finanza_repo.salva_file_archivio(
        categoria=categoria,
        file_nome=nome,
        file_mime=mime,
        dati=None,  # niente byte nel DB
        file_hash=file_hash,
        anno=anno,
        mese=mese,
        descrizione=descrizione,
        gdrive_url=url,
        iniziativa_id=iniziativa_id,
        documento_id=documento_id,
        caricato_da=caricato_da,
    )
    return {"salvato": True, "gia_presente": False, "gdrive": url, "errore": None}
