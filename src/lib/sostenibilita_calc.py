"""Calcolo completo del cruscotto di sostenibilità (v3) — condiviso fra la
pagina «Sostenibilità» e il report finanziario .pptx.

Legge dai repository e applica le regole pure di `src/domain/sostenibilita`.
Ritorna un dizionario con tutte le grandezze già pronte per la resa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.data import finanza_repo, progetti_repo, sostenibilita_repo
from src.domain.finanza import prossimi_mesi
from src.domain.sostenibilita import (
    costo_personale_mese,
    costo_pieno_orario,
    entrate_pipeline_mensili,
    espandi_spese_periodiche,
    kpi_autonomia,
    kpi_backlog_coverage,
    kpi_concentrazione_clienti,
    kpi_margine,
    kpi_quota_mercato,
    kpi_ricorrenti,
    kpi_tariffa_costo,
    proiezione_scenari,
    stima_utile_tasse,
    tariffa_media_progetti,
    totali_per_anno,
)

BASI = ("parametro", "storica", "analitica")


def calcola(
    anno: int,
    n_mesi: int = 24,
    base_scelta: str | None = None,
    oggi: date | None = None,
) -> dict:
    """Tutte le grandezze del cruscotto per `anno` e un orizzonte di `n_mesi`.

    `base_scelta`: 'parametro' | 'storica' | 'analitica' | None (automatica:
    parametro se impostato, altrimenti analitica se calcolabile, altrimenti
    stima storica).
    """
    oggi = oggi or date.today()
    par = sostenibilita_repo.get_parametri(anno)

    saldo_mov = Decimal(str(finanza_repo.saldo_attuale()))
    saldo = Decimal(par["saldo_iniziale"]) if par["saldo_iniziale"] else saldo_mov
    stima_storica = Decimal(str(round(finanza_repo.uscite_ricorrenti_stima(3), 2)))

    persone = sostenibilita_repo.persone_costo()
    tariffe = progetti_repo.tariffe_by_persona([p["id"] for p in persone] or None)
    spese_per = finanza_repo.list_spese_periodiche()

    mesi = prossimi_mesi(oggi, n_mesi)
    per_mese, ignorate = espandi_spese_periodiche(spese_per, mesi)
    personale_mese = {
        k: costo_personale_mese(persone, tariffe, k[0], k[1]) for k in mesi
    }
    analitica = {
        k: per_mese.get(k, Decimal("0")) + personale_mese.get(k, Decimal("0"))
        for k in mesi
    }

    opzioni_base = {
        "parametro": (
            f"Parametro fisso ({float(par['costi_fissi_mensili'] or 0):,.0f} €/mese)"
        ),
        "storica": f"Stima storica ultimi 3 mesi ({float(stima_storica):,.0f} €/mese)",
        "analitica": (
            "Analitica: personale previsto + spese periodiche "
            f"({float(analitica[mesi[0]]):,.0f} €/mese nel primo mese)"
        ),
    }
    if base_scelta not in BASI:
        base_scelta = (
            "parametro"
            if par["costi_fissi_mensili"]
            else ("analitica" if analitica[mesi[0]] > 0 else "storica")
        )
    if base_scelta == "parametro":
        uscite_base: dict | Decimal = Decimal(par["costi_fissi_mensili"] or 0)
    elif base_scelta == "storica":
        uscite_base = stima_storica
    else:
        uscite_base = analitica
    costi_mensili = (
        uscite_base if isinstance(uscite_base, Decimal) else analitica[mesi[0]]
    )

    entrate_firmate: dict = {}
    uscite_prog: dict = {}
    for r in finanza_repo.entrate_programmate_mensili():
        entrate_firmate[(r["anno"], r["mese"])] = Decimal(r["tot"])
    for r in finanza_repo.uscite_programmate_mensili():
        uscite_prog[(r["anno"], r["mese"])] = Decimal(r["tot"])
    for r in finanza_repo.previsti_programmati_mensili():
        k = (r["anno"], r["mese"])
        tgt = entrate_firmate if r["segno"] == "entrata" else uscite_prog
        tgt[k] = tgt.get(k, Decimal("0")) + Decimal(r["tot"])

    pipeline = sostenibilita_repo.iniziative_pipeline()
    pipe_pesata = entrate_pipeline_mensili(pipeline, mesi, pesate=True)
    pipe_intera = entrate_pipeline_mensili(pipeline, mesi, pesate=False)
    scenari = proiezione_scenari(
        saldo, mesi, entrate_firmate, uscite_prog, uscite_base, pipe_pesata, pipe_intera
    )

    backlog_tot, backlog_det = sostenibilita_repo.residuo_contratti_firmati()
    cons = sostenibilita_repo.entrate_uscite_anno(anno)
    costo_pieno = costo_pieno_orario(
        par["costo_personale_annuo"],
        par["costi_indiretti_annui"],
        par["teste_dirette"],
        par["ore_vendibili_fte"],
    )
    tariffa_media = tariffa_media_progetti(
        sostenibilita_repo.progetti_tariffa_implicita()
    )
    ricavi_tipo = sostenibilita_repo.ricavi_per_tipo(anno)
    kpis = [
        kpi_autonomia(saldo, costi_mensili),
        kpi_backlog_coverage(backlog_tot, costi_mensili),
        kpi_margine(cons["entrate"], cons["uscite"]),
        kpi_concentrazione_clienti(sostenibilita_repo.ricavi_per_controparte(anno)),
        kpi_quota_mercato(ricavi_tipo),
        kpi_ricorrenti(ricavi_tipo),
        kpi_tariffa_costo(tariffa_media, costo_pieno),
    ]

    uscite_res = {(r["anno"], r["mese"]): r["uscite"] for r in scenari["pesato"]}
    entrate_res = {
        k: entrate_firmate.get(k, Decimal("0")) + pipe_pesata.get(k, Decimal("0"))
        for k in mesi
    }
    residuo = sostenibilita_repo.uscite_previste_residuo_anno(
        anno, uscite_res, entrate_res
    )
    stima = stima_utile_tasse(
        cons["entrate"],
        cons["uscite"],
        residuo["entrate"],
        residuo["uscite"],
        par["aliquota_fiscale"],
    )

    return {
        "anno": anno,
        "oggi": oggi,
        "par": par,
        "saldo": saldo,
        "saldo_mov": saldo_mov,
        "saldo_verificato": bool(par["saldo_iniziale"]),
        "stima_storica": stima_storica,
        "analitica": analitica,
        "spese_periodiche_mese": per_mese,
        "personale_mese": personale_mese,
        "ignorate": ignorate,
        "opzioni_base": opzioni_base,
        "base_scelta": base_scelta,
        "uscite_base": uscite_base,
        "costi_mensili": costi_mensili,
        "mesi": mesi,
        "entrate_firmate": entrate_firmate,
        "uscite_prog": uscite_prog,
        "pipeline": pipeline,
        "pipe_pesata": pipe_pesata,
        "pipe_intera": pipe_intera,
        "scenari": scenari,
        "totali_anno": totali_per_anno(scenari["pesato"]),
        "backlog_tot": backlog_tot,
        "backlog_det": backlog_det,
        "cons": cons,
        "costo_pieno": costo_pieno,
        "tariffa_media": tariffa_media,
        "kpis": kpis,
        "residuo": residuo,
        "stima": stima,
    }
