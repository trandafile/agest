"""Regole di dominio del timesheet (spec §5) — pure Python, testabili.

Le stesse regole sono replicate lato DB (trigger `fn_timesheet_guard` +
funzione `conferma_timesheet` nella migrazione 0002): qui servono per la UX
(feedback immediato in griglia), la' come enforcement vero.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

TETTO_GIORNALIERO = 8

GIORNI_IT = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")


@dataclass(frozen=True)
class AssegnazioneInfo:
    """Vista minimale di un'assegnazione per la validazione della griglia."""

    id: str
    titolo: str
    tipo_attivita: str = "altro"
    tetto_ore_mese: float | None = None
    data_inizio: date | None = None
    data_fine: date | None = None
    ore_totali_iniziativa: float | None = None


@dataclass
class EsitoValidazione:
    errori: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errori


def giorni_del_mese(anno: int, mese: int) -> list[date]:
    """Tutti i giorni del mese, in ordine."""
    _, n = calendar.monthrange(anno, mese)
    return [date(anno, mese, g) for g in range(1, n + 1)]


def is_lavorativo(d: date, festivita: set[date]) -> bool:
    """True se giorno feriale e non festivo."""
    return d.isoweekday() < 6 and d not in festivita


def etichetta_giorno(d: date) -> str:
    """Intestazione colonna griglia, es. '3 Mer'."""
    return f"{d.day} {GIORNI_IT[d.isoweekday() - 1]}"


def valida_griglia(
    ore: dict[tuple[str, date], int],
    assegnazioni: dict[str, AssegnazioneInfo],
    festivita: set[date],
    stato_mese: str = "bozza",
    forza_non_lavorativi: bool = False,
) -> EsitoValidazione:
    """Applica le regole 1-6 del §5 alla griglia (celle = (assegnazione, giorno)).

    `ore` contiene solo celle valorizzate (>0); celle vuote non compaiono.
    """
    esito = EsitoValidazione()

    # 5) editabile solo in bozza
    if stato_mese != "bozza":
        esito.errori.append("Il mese è confermato: non è più modificabile.")
        return esito

    tot_giorno: dict[date, int] = {}
    tot_riga: dict[str, int] = {}

    for (aid, giorno), valore in ore.items():
        info = assegnazioni.get(aid)
        if info is None:
            esito.errori.append(f"Assegnazione sconosciuta: {aid}")
            continue

        # 1) intero >= 0 (e <= 8 per cella, implicito nel tetto giornaliero)
        if not isinstance(valore, int) or valore < 0:
            esito.errori.append(
                f"{info.titolo} {giorno:%d/%m}: le ore devono essere un intero ≥ 0."
            )
            continue
        if valore == 0:
            continue

        # 6) dentro l'intervallo dell'iniziativa
        if info.data_inizio and giorno < info.data_inizio:
            esito.errori.append(
                f"{info.titolo} {giorno:%d/%m}: prima dell'inizio iniziativa "
                f"({info.data_inizio:%d/%m/%Y})."
            )
        if info.data_fine and giorno > info.data_fine:
            esito.errori.append(
                f"{info.titolo} {giorno:%d/%m}: oltre la fine iniziativa "
                f"({info.data_fine:%d/%m/%Y})."
            )

        # 4) weekend/festivi solo con flag esplicito
        if not forza_non_lavorativi and not is_lavorativo(giorno, festivita):
            esito.errori.append(
                f"{info.titolo} {giorno:%d/%m}: giorno non lavorativo "
                "(weekend/festività). Attiva il flag per forzare."
            )

        tot_giorno[giorno] = tot_giorno.get(giorno, 0) + valore
        tot_riga[aid] = tot_riga.get(aid, 0) + valore

    # 2) tetto giornaliero
    for giorno, tot in sorted(tot_giorno.items()):
        if tot > TETTO_GIORNALIERO:
            esito.errori.append(
                f"{giorno:%d/%m}: totale {tot} h supera il tetto giornaliero "
                f"di {TETTO_GIORNALIERO} h."
            )

    # 3) tetto mensile per riga
    for aid, tot in tot_riga.items():
        info = assegnazioni[aid]
        if info.tetto_ore_mese is not None and tot > info.tetto_ore_mese:
            esito.errori.append(
                f"{info.titolo}: totale mese {tot} h supera il Max mese "
                f"({info.tetto_ore_mese:g} h)."
            )

    return esito


def totale_riga(ore: dict[tuple[str, date], int], aid: str) -> int:
    return sum(v for (a, _), v in ore.items() if a == aid)


def totale_giorno(ore: dict[tuple[str, date], int], giorno: date) -> int:
    return sum(v for (_, g), v in ore.items() if g == giorno)


def riga_valida(ore: dict[tuple[str, date], int], info: AssegnazioneInfo) -> bool:
    """Indicatore verde: somma mese della riga entro il tetto (regola 7)."""
    if info.tetto_ore_mese is None:
        return True
    return totale_riga(ore, info.id) <= info.tetto_ore_mese
