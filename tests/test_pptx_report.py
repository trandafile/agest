"""Presentazioni sul template ANTECNICA: i tre deck si costruiscono da pack
sintetici, si riaprono con python-pptx e usano solo i layout del template."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest

pptx = pytest.importorskip("pptx")
from pptx import Presentation  # noqa: E402

from src.lib.pptx_report import (  # noqa: E402
    TEMPLATE,
    Deck,
    build_report_attivita,
    build_report_finanziario,
    build_report_progetto,
)

OGGI = date(2026, 9, 5)


def _testi(prs) -> str:
    out = []
    for s in prs.slides:
        for sh in s.shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                for r in sh.table.rows:
                    out.extend(c.text for c in r.cells)
    return "\n".join(out)


def test_template_presente():
    assert TEMPLATE.exists()
    nomi = {lay.name for lay in Presentation(str(TEMPLATE)).slide_layouts}
    assert {
        "TITLE",
        "SECTION",
        "CONTENT",
        "TWO_COLUMNS",
        "TITLE_ONLY",
        "CONTENT_DARK",
        "CLOSING",
    } <= nomi


def test_deck_rimuove_slide_di_esempio_e_usa_i_layout():
    d = Deck()
    assert len(d.prs.slides) == 0
    d.titolo("T", "S", "M")
    d.sezione(1, "Sez", "sotto")
    d.contenuto("C", ["a", (1, "b")])
    d.due_colonne("D", ("L", ["x"]), ("R", ["y"]))
    d.kpi("K", [("1", "uno", "s"), ("2", "due", "")])
    d.tabella("Tab", ["A", "B"], [["1", ("2", None)] for _ in range(30)], max_righe=14)
    d.grafico("G", ["a", "b"], {"s1": [1, 2], "s2": [3, 4]}, tipo="linee")
    d.gantt(
        "Gantt",
        [
            {
                "etichetta": "P",
                "inizio": date(2025, 1, 1),
                "fine": date(2026, 6, 30),
                "categoria": "Progetto attivo",
                "milestone": [date(2025, 7, 1)],
            }
        ],
        [2025, 2026],
        oggi=OGGI,
    )
    d.chiusura("Fine")
    prs = Presentation(BytesIO(d.bytes()))
    layouts = [s.slide_layout.name for s in prs.slides]
    # la tabella da 30 righe viene paginata su 3 slide
    assert layouts.count("TITLE_ONLY") >= 5
    assert layouts[0] == "TITLE" and layouts[-1] == "CLOSING"
    testo = _testi(prs)
    assert "Tab (cont.)" in testo
    assert "Click to add" not in testo


def _pack_attivita() -> dict:
    return {
        "titolo": "Report attività",
        "sottotitolo": "Stato progetti",
        "meta": "ANTECNICA · 05/09/2026",
        "oggi": OGGI,
        "anni": [2025, 2026, 2027],
        "periodo_giorni": 30,
        "gantt": [
            {
                "etichetta": "CASCADE · Cascaded array",
                "inizio": date(2025, 3, 1),
                "fine": date(2027, 3, 1),
                "categoria": "Progetto attivo",
                "milestone": [date(2026, 3, 1)],
            },
            {
                "etichetta": "ESA_Ka · proposta",
                "inizio": date(2026, 12, 1),
                "fine": date(2028, 11, 30),
                "categoria": "Proposta inviata",
            },
        ],
        "sintesi": {
            "progetti_attivi": 2,
            "deliverable_aperti": 3,
            "task_attivi": 5,
            "in_ritardo": 1,
            "bloccati": 0,
            "completati_periodo": 4,
            "avviati_periodo": 2,
            "scadenze_30": 3,
        },
        "progetti": [
            {
                "etichetta": "CASCADE · Cascaded array",
                "controparte": "ESA",
                "stato": "attivo",
                "inizio": date(2025, 3, 1),
                "fine": date(2027, 3, 1),
                "milestone": [
                    {"titolo": "MS1", "data": date(2026, 3, 1), "stato": "completata"}
                ],
                "deliverables": [
                    {
                        "titolo": "D1 report",
                        "tipo": "report",
                        "stato": "in_corso",
                        "scadenza": date(2026, 10, 1),
                        "owner": "Luigi",
                        "tasks": [
                            {
                                "titolo": "Scrivere cap. 2",
                                "stato": "in_corso",
                                "scadenza": date(2026, 8, 1),
                                "owner": "Luigi",
                                "subtasks": [
                                    {
                                        "titolo": "Figure",
                                        "stato": "da_fare",
                                        "scadenza": None,
                                        "owner": "Anna",
                                    }
                                ],
                            }
                        ],
                    },
                ],
                "task_liberi": [
                    {
                        "titolo": "Ordine componenti",
                        "stato": "bloccato",
                        "scadenza": date(2026, 9, 30),
                        "owner": "Mario",
                        "subtasks": [],
                    }
                ],
            }
        ],
        "persone": [
            {
                "nome": "Luigi",
                "attivi": 3,
                "in_ritardo": 1,
                "bloccati": 0,
                "completati_periodo": 2,
                "puntualita": "80%",
                "completati": ["A", "B"],
                "in_corso": ["C"],
                "ritardo": ["D"],
                "bloccati_lista": [],
            }
        ],
        "scadenze": [
            {
                "data": date(2026, 9, 30),
                "tipo": "task",
                "titolo": "Ordine",
                "progetto": "CASCADE",
                "owner": "Mario",
            }
        ],
    }


def test_report_attivita():
    prs = Presentation(BytesIO(build_report_attivita(_pack_attivita())))
    testo = _testi(prs)
    for atteso in (
        "Report attività",
        "Portafoglio",
        "CASCADE",
        "Scrivere cap. 2",
        "Figure",
        "Luigi",
        "Ordine",
        "Grazie",
    ):
        assert atteso in testo
    assert len(prs.slides) >= 9


def test_report_finanziario():
    pack = {
        "anno": 2026,
        "titolo": "Report finanziario",
        "meta": "riservato",
        "kpi": [
            {
                "nome": "Autonomia",
                "valore_txt": "8.0 mesi",
                "allarme": "< 6",
                "target": "≥ 12",
                "stato": "attenzione",
                "descrizione": "saldo/costi",
            },
            {
                "nome": "Backlog",
                "valore_txt": "14.0 mesi",
                "allarme": "< 9",
                "target": "12–15",
                "stato": "ok",
                "descrizione": "…",
            },
        ],
        "saldo": 100000,
        "costi_mensili": 12500,
        "backlog": 175000,
        "pipeline_pesata": 50000,
        "cash_flow": {
            "mesi": ["01", "02", "03"],
            "entrate": [10, 20, 30],
            "uscite": [5, 25, 10],
        },
        "scenari": {
            "mesi": ["2026-09", "2026-10"],
            "firmato": [1, -2],
            "pesato": [3, 4],
            "ottimista": [5, 6],
        },
        "totali_anno": [
            {"anno": 2026, "entrate": 100, "uscite": 80, "saldo_fine": 20},
            {"anno": 2027, "entrate": 10, "uscite": 80, "saldo_fine": -50},
        ],
        "storico_anni": [{"anno": 2024, "entrate": 400, "uscite": 300}],
        "backlog_det": [
            {
                "etichetta": "CASCADE",
                "controparte": "ESA",
                "tipo_ricavo": "agevolato",
                "importo": 675000,
                "incassato": 500000,
                "residuo": 175000,
                "data_fine": date(2027, 3, 1),
            }
        ],
        "pnl": [
            {
                "progetto": "CASCADE",
                "entrate": 500000,
                "uscite": 100000,
                "saldo": 400000,
            }
        ],
        "ricavi_anno": {
            "anni": ["2026", "2027"],
            "serie": {"CASCADE": [300000, 60000], "ESA_Ka": [10000, 200000]},
        },
        "stima": {
            "entrate": 600000,
            "uscite": 400000,
            "utile_lordo": 200000,
            "tasse_stimate": 55800,
            "utile_netto": 144200,
            "aliquota": 0.279,
        },
        "scadenzario": [
            {
                "scadenza": date(2026, 10, 1),
                "tipo": "attiva",
                "numero": "12",
                "controparte": "ESA",
                "importo": 120000,
                "stato": "aperto",
            }
        ],
    }
    prs = Presentation(BytesIO(build_report_finanziario(pack)))
    testo = _testi(prs)
    for atteso in (
        "Report finanziario",
        "Autonomia",
        "Backlog",
        "CASCADE",
        "Stima utile e tasse 2026",
        "Scadenzario",
    ):
        assert atteso in testo
    grafici = sum(1 for s in prs.slides for sh in s.shapes if sh.has_chart)
    assert grafici == 4  # cash flow, scenari, storico, ricavi attesi (tutti nativi)


def test_report_progetto_senza_economia_non_mostra_importi():
    pack = {
        "etichetta": "CASCADE · Cascaded array",
        "titolo": "Cascaded array",
        "meta": "SAL",
        "oggi": OGGI,
        "economia": False,
        "budget": 675000,
        "speso": 100,
        "rimanente": 1,
        "avanzamento_pct": 10,
        "ore_timesheet": 1200,
        "deliverable_completati": 1,
        "deliverable_totali": 3,
        "task_completati": 4,
        "task_totali": 9,
        "in_ritardo": 0,
        "quote": [{"categoria": "personale", "budget": 1, "speso": 2, "rimanente": -1}],
        "milestone": [
            {
                "titolo": "MS1",
                "data": date(2026, 3, 1),
                "stato": "completata",
                "pagamento": True,
                "importo": 120000,
            }
        ],
        "deliverables": [
            {
                "titolo": "D1",
                "tipo": "report",
                "stato": "in_corso",
                "scadenza": None,
                "owner": "L",
                "tasks": [],
            }
        ],
        "flussi": [
            {
                "descrizione": "Anticipo",
                "segno": "entrata",
                "importo": 100,
                "data": None,
                "completata": True,
            }
        ],
        "ore_persone": [
            {
                "nome": "Luigi",
                "pianificate": 1000,
                "anni": {2026: 600},
                "consuntivo": 550,
            }
        ],
        "anni_ore": [2026],
    }
    testo = _testi(Presentation(BytesIO(build_report_progetto(pack))))
    assert (
        "Budget (baseline)" not in testo
        and "120" not in testo.split("Milestone")[1].split("Deliverable")[0]
    )
    assert "MS1" in testo and "Ore per persona" in testo
    pack["economia"] = True
    testo2 = _testi(Presentation(BytesIO(build_report_progetto(pack))))
    assert (
        "Budget (baseline)" in testo2 and "Calendario dei movimenti previsti" in testo2
    )
