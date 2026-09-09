"""Notifiche e-mail «a evento» dall'app (v3, come MAIC tasks): task assegnato,
nuovo commento, monthly report pronto.

Configurazione dai secrets di Streamlit (sezione `[smtp]` oppure chiavi
SMTP_* al primo livello) con fallback alle variabili d'ambiente. Se non è
configurata, tutte le funzioni sono no-op silenziosi: l'app non deve mai
rompersi per colpa della posta. Gli invii avvengono in un thread separato
per non bloccare l'interfaccia.
"""

from __future__ import annotations

import logging
import os
import threading

from src.lib.notifiche import (
    ConfigSMTP,
    html_commento,
    html_monthly_pronto,
    html_task_assegnato,
    invia,
)

log = logging.getLogger(__name__)

_MAPPA_SEZIONE = {
    "host": "SMTP_HOST",
    "port": "SMTP_PORT",
    "user": "SMTP_USER",
    "password": "SMTP_PASSWORD",
    "from": "SMTP_FROM",
    "app_url": "APP_URL",
    "attive": "NOTIFICHE_ATTIVE",
}
_CHIAVI = tuple(_MAPPA_SEZIONE.values())


def config_smtp() -> ConfigSMTP:
    """Secrets Streamlit (se disponibili) + ambiente."""
    env = dict(os.environ)
    try:
        import streamlit as st

        sec = st.secrets
        for k in _CHIAVI:
            if k in sec:
                env[k] = str(sec[k])
        if "smtp" in sec:
            for k, v in dict(sec["smtp"]).items():
                env[_MAPPA_SEZIONE.get(k, k)] = str(v)
    except Exception:  # noqa: BLE001 — fuori da Streamlit o secrets assenti
        pass
    return ConfigSMTP.da_ambiente(env)


def _in_background(
    cfg: ConfigSMTP,
    destinatario: str,
    oggetto: str,
    corpo_html: str,
    corpo_txt: str,
    allegati=None,
) -> None:
    def _run() -> None:
        try:
            invia(cfg, destinatario, oggetto, corpo_html, corpo_txt, allegati=allegati)
        except Exception as exc:  # noqa: BLE001
            log.warning("Invio e-mail fallito a %s: %s", destinatario, exc)

    threading.Thread(target=_run, daemon=True).start()


def notifica_task_assegnato(
    task, owner, assegnato_da, progetto: str | None = None
) -> bool:
    """E-mail all'owner quando qualcun altro gli assegna un task."""
    cfg = config_smtp()
    if not cfg.configurato or owner is None or not getattr(owner, "email", None):
        return False
    if assegnato_da is not None and getattr(assegnato_da, "id", None) == owner.id:
        return False  # se lo assegno a me stesso non mi scrivo
    corpo_html, corpo_txt = html_task_assegnato(
        owner.nome,
        {"titolo": task.titolo, "scadenza": task.scadenza, "progetto": progetto},
        getattr(assegnato_da, "nome_completo", None) or "un collega",
        cfg.app_url,
    )
    _in_background(
        cfg,
        owner.email,
        f"[ANTECNICA] Nuovo task: {task.titolo}",
        corpo_html,
        corpo_txt,
    )
    return True


def notifica_commento(destinatari, titolo_entita: str, autore, testo: str) -> int:
    """E-mail a owner/supervisor (tranne l'autore) quando arriva un commento."""
    cfg = config_smtp()
    if not cfg.configurato:
        return 0
    n = 0
    visti = set()
    for p in destinatari:
        if p is None or not getattr(p, "email", None) or p.id in visti:
            continue
        if autore is not None and p.id == getattr(autore, "id", None):
            continue
        visti.add(p.id)
        corpo_html, corpo_txt = html_commento(
            p.nome,
            titolo_entita,
            getattr(autore, "nome_completo", None) or "un collega",
            testo,
            cfg.app_url,
        )
        _in_background(
            cfg,
            p.email,
            f"[ANTECNICA] Commento su: {titolo_entita}",
            corpo_html,
            corpo_txt,
        )
        n += 1
    return n


def notifica_monthly_pronto(
    cfg: ConfigSMTP,
    email: str,
    nome: str,
    etichetta: str,
    anno: int,
    mese: int,
    md: str,
    nome_file: str,
) -> bool:
    """E-mail (sincrona, usata dallo script schedulato) con il .md allegato."""
    if not cfg.configurato or not email:
        return False
    corpo_html, corpo_txt = html_monthly_pronto(
        nome, etichetta, anno, mese, cfg.app_url
    )
    return invia(
        cfg,
        email,
        f"[ANTECNICA] Monthly report {etichetta} — file pronto",
        corpo_html,
        corpo_txt,
        allegati=[(nome_file, md.encode("utf-8"), "text/markdown")],
    )
