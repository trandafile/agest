"""Due livelli di visibilità: DIPENDENTE e AMMINISTRATORE (spec §13.1).

I ruoli di sistema restano tre (`admin`, `pm`, `dipendente`) perché il `pm`
serve a individuare il responsabile di un'iniziativa; ma ai fini di COSA si
vede esistono solo due livelli:

  * amministratore  = ruolo `admin`: tutto, inclusi dati economici, finanza,
                      anagrafica, report finanziari e portfolio con importi.
  * dipendente      = ruoli `pm` e `dipendente`: dati propri (timesheet,
                      presenze, ferie, missioni), task/deliverable di tutti,
                      calendario, portfolio SENZA importi/probabilità, e — solo
                      per il pm — vista OPERATIVA dei progetti di cui è
                      responsabile (milestone, deliverable, commenti, stato),
                      mai budget, costi, flussi o tariffe.

Logica pura: nessuna dipendenza da Streamlit, testabile.
"""

from __future__ import annotations

import enum
from typing import Any

from src.domain.models import RuoloSistema


class Livello(enum.StrEnum):
    amministratore = "amministratore"
    dipendente = "dipendente"


def livello(ruolo: RuoloSistema | str) -> Livello:
    """Ruolo di sistema -> livello di visibilità."""
    r = ruolo.value if isinstance(ruolo, RuoloSistema) else str(ruolo)
    return Livello.amministratore if r == "admin" else Livello.dipendente


def vede_economia(ruolo: RuoloSistema | str) -> bool:
    """Budget, costi, tariffe, flussi, finanza, KPI: solo amministratore."""
    return livello(ruolo) is Livello.amministratore


def is_responsabile(persona_id: Any, iniziativa: Any) -> bool:
    """True se `persona_id` è il responsabile dell'iniziativa."""
    return (
        bool(persona_id) and getattr(iniziativa, "responsabile_id", None) == persona_id
    )


def vede_progetto_operativo(
    ruolo: RuoloSistema | str, persona_id: Any, iniziativa: Any
) -> bool:
    """Vista operativa di un progetto (senza importi): amministratore sempre,
    pm solo se responsabile."""
    if vede_economia(ruolo):
        return True
    r = ruolo.value if isinstance(ruolo, RuoloSistema) else str(ruolo)
    return r == "pm" and is_responsabile(persona_id, iniziativa)


# Matrice di visibilità (documentazione + test): pagina -> livelli ammessi.
MATRICE_VISIBILITA: dict[str, tuple[Livello, ...]] = {
    "Dashboard": (Livello.amministratore, Livello.dipendente),
    "Timesheet": (Livello.amministratore, Livello.dipendente),
    "Presenze": (Livello.amministratore, Livello.dipendente),
    "Ferie / Permessi": (Livello.amministratore, Livello.dipendente),
    "Task": (Livello.amministratore, Livello.dipendente),
    "Calendario": (Livello.amministratore, Livello.dipendente),
    "Missioni": (Livello.amministratore, Livello.dipendente),
    "Portfolio (senza importi)": (Livello.amministratore, Livello.dipendente),
    "Presentazioni (attività)": (Livello.amministratore, Livello.dipendente),
    "Progetti (vista operativa, solo propri)": (
        Livello.amministratore,
        Livello.dipendente,
    ),
    "Progetti (vista economica)": (Livello.amministratore,),
    "Proposte": (Livello.amministratore,),
    "Portfolio (importi, probabilità, capacity)": (Livello.amministratore,),
    "Anagrafica": (Livello.amministratore,),
    "Report dipendenti": (Livello.amministratore,),
    "Finanza": (Livello.amministratore,),
    "Sostenibilità": (Livello.amministratore,),
    "Import banca": (Livello.amministratore,),
    "Presentazioni (finanziario)": (Livello.amministratore,),
}


def pagine_visibili(ruolo: RuoloSistema | str) -> list[str]:
    lv = livello(ruolo)
    return [k for k, v in MATRICE_VISIBILITA.items() if lv in v]
