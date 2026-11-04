"""Permessi operativi su task e deliverable — logica pura (testabile).

Tre livelli per il lavoro operativo (ortogonali alla visibilità economica di
`visibilita.py`, che resta a due livelli):

  * dipendente      — vede tutto; crea task; modifica/archivia solo i task e
                      i deliverable di cui è owner o supervisor.
  * gestore task    — livello gestionale INTERMEDIO (flag
                      `persona.gestore_task`, migrazione 0019): crea, modifica,
                      archivia ed ELIMINA task e deliverable di chiunque e li
                      importa da YAML/JSON. Nessun accesso ai dati economici.
  * amministratore  — tutto (incluso il Gantt di progetto, solo admin).

Il pm conserva la creazione/eliminazione dei deliverable che aveva già.
"""

from __future__ import annotations

from typing import Any

from src.domain.models import RuoloSistema


def _ruolo(persona: Any) -> str:
    r = getattr(persona, "ruolo_sistema", None)
    return getattr(r, "value", None) or str(r or "")


def is_admin(persona: Any) -> bool:
    return _ruolo(persona) == RuoloSistema.admin.value


def is_gestore_task(persona: Any) -> bool:
    """Admin oppure persona con il flag `gestore_task`."""
    return is_admin(persona) or bool(getattr(persona, "gestore_task", False))


def puo_modificare_task(task: Any, persona: Any) -> bool:
    """Owner/supervisor del task, oppure gestore task/admin."""
    if is_gestore_task(persona):
        return True
    pid = getattr(persona, "id", None)
    return bool(pid) and pid in (
        getattr(task, "owner_id", None),
        getattr(task, "supervisor_id", None),
    )


def puo_eliminare_task(persona: Any) -> bool:
    """Eliminazione definitiva di un task: gestore task/admin."""
    return is_gestore_task(persona)


def puo_importare_task(persona: Any) -> bool:
    """Import YAML/JSON di deliverable, task e subtask: gestore task/admin."""
    return is_gestore_task(persona)


def puo_gestire_deliverable(persona: Any) -> bool:
    """Creare/eliminare deliverable: admin, pm (come prima) e gestore task."""
    return is_gestore_task(persona) or _ruolo(persona) == RuoloSistema.pm.value


def puo_modificare_deliverable(deliverable: Any, persona: Any) -> bool:
    """Owner/supervisor del deliverable, oppure gestore task/admin."""
    return puo_modificare_task(deliverable, persona)


def puo_archiviare_deliverable(persona: Any) -> bool:
    """Archiviazione di un deliverable dall'albero dei task."""
    return is_gestore_task(persona)


def descrizione_livello(persona: Any) -> str:
    """Etichetta per la sidebar: «amministratore», «dipendente · gestore task»…"""
    if is_admin(persona):
        return "amministratore"
    return "dipendente · gestore task" if is_gestore_task(persona) else "dipendente"
