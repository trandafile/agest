"""Monthly report: regole pure (mese precedente, note datate, file .md)."""

from __future__ import annotations

from datetime import date, datetime

from src.lib.monthly_report import (
    ISTRUZIONI_DEFAULT,
    descrizione_senza_note,
    etichetta_mese,
    genera_md,
    intervallo_mese,
    mese_precedente,
    nome_file,
    note_datate_nel_mese,
)


def test_mese_precedente_e_intervallo():
    assert mese_precedente(date(2026, 9, 1)) == (2026, 8)
    assert mese_precedente(date(2026, 1, 15)) == (2025, 12)
    assert intervallo_mese(2026, 12) == (date(2026, 12, 1), date(2027, 1, 1))
    assert intervallo_mese(2026, 2) == (date(2026, 2, 1), date(2026, 3, 1))
    assert etichetta_mese(2026, 8) == "agosto 2026"


def test_nome_file_sicuro():
    assert nome_file("ESA Ka/2", 2026, 8) == "monthly_report_ESA_Ka_2_2026-08.md"
    assert nome_file(None, 2026, 1) == "monthly_report_progetto_2026-01.md"


def test_note_datate_filtrate_per_mese():
    desc = (
        "Descrizione libera del task.\n\n"
        "**28/08/2026** — misure completate\n"
        "**02/09/2026** — inviata bozza al PO\n"
        "**15/09/2026** - ricevuti commenti\n"
        "riga normale"
    )
    assert note_datate_nel_mese(desc, 2026, 9) == [
        "02/09/2026: inviata bozza al PO",
        "15/09/2026: ricevuti commenti",
    ]
    assert note_datate_nel_mese(desc, 2026, 8) == ["28/08/2026: misure completate"]
    assert note_datate_nel_mese(None, 2026, 9) == []
    assert (
        descrizione_senza_note(desc) == "Descrizione libera del task.\n\nriga normale"
    )


def _pack() -> dict:
    return {
        "anno": 2026,
        "mese": 8,
        "generato_il": date(2026, 9, 1),
        "progetto": {
            "acronimo": "CASCADE",
            "codice": "ESA-1234",
            "titolo": "Cascaded array",
            "controparte": "ESA",
            "cup": None,
            "inizio": date(2025, 3, 1),
            "fine": date(2027, 3, 1),
            "responsabile": "Luigi Boccia",
            "stato": "attivo",
            "istruzioni": "Lingua: inglese. Formato ESA Monthly Progress Report.",
        },
        "deliverables": [
            {
                "titolo": "D2.1 Report",
                "tipo": "Report",
                "stato": "in_corso",
                "scadenza": date(2026, 11, 30),
                "owner": "Luigi Boccia",
                "task_completati": 3,
                "task_totali": 7,
            }
        ],
        "milestone": [
            {
                "titolo": "MS2",
                "stato": "prevista",
                "data": date(2026, 8, 20),
                "nel_mese": True,
            }
        ],
        "task_attivi": [
            {
                "deliverable": "D2.1 Report",
                "task": [
                    {
                        "titolo": "Misure in camera anecoica",
                        "stato": "in_corso",
                        "owner": "Luigi Boccia",
                        "scadenza": date(2026, 10, 15),
                        "completato_il": None,
                        "ore_stimate": 16.0,
                        "ore_effettive": 6.0,
                        "descrizione": "Setup 2x2.\n**12/08/2026** — prima sessione ok",
                        "storico": [
                            {
                                "da": "da_fare",
                                "a": "in_corso",
                                "quando": datetime(2026, 8, 10, 9, 0),
                            }
                        ],
                        "commenti": [
                            {
                                "autore": "Anna Verdi",
                                "quando": datetime(2026, 8, 11),
                                "testo": "servono cavi nuovi",
                            }
                        ],
                        "subtask": [
                            {
                                "titolo": "Preparare setup",
                                "stato": "completato",
                                "owner": "Anna Verdi",
                                "scadenza": None,
                                "completato_il": date(2026, 8, 5),
                                "ore_stimate": None,
                                "ore_effettive": None,
                                "descrizione": None,
                                "storico": [],
                                "commenti": [],
                                "subtask": [],
                            }
                        ],
                    }
                ],
            }
        ],
        "task_completati": [
            {
                "titolo": "Simulazioni EM",
                "stato": "completato",
                "owner": "Luigi Boccia",
                "scadenza": date(2026, 8, 20),
                "completato_il": date(2026, 8, 18),
                "ore_stimate": None,
                "ore_effettive": None,
                "descrizione": None,
                "storico": [],
                "commenti": [],
                "subtask": [],
            }
        ],
        "ore_timesheet": [
            {"persona": "Luigi Boccia", "ore": 64},
            {"persona": "Anna Verdi", "ore": 40},
        ],
        "missioni": [
            {
                "persona": "Luigi Boccia",
                "destinazione": "ESTEC",
                "inizio": date(2026, 8, 25),
                "fine": date(2026, 8, 26),
                "obiettivo": "Progress meeting",
            }
        ],
        "commenti_progetto": [
            {
                "autore": "Luigi Boccia",
                "quando": datetime(2026, 8, 30),
                "testo": "kick-off fase 2",
            }
        ],
    }


def test_genera_md_contenuto():
    md = genera_md(_pack())
    for atteso in (
        "# Monthly report — CASCADE — agosto 2026",
        "## Istruzioni per l'assistente AI",
        "01/08/2026 – 31/08/2026",
        "Formato ESA Monthly Progress Report",
        "## Note del responsabile",
        "### Progetto",
        "- Responsabile: Luigi Boccia",
        "| D2.1 Report | Report | in corso | 30/11/2026 | Luigi Boccia | 3/7 |",
        "- MS2 — prevista · prevista 20/08/2026 · **nel mese**",
        "#### D2.1 Report",
        "- **Misure in camera anecoica** — in corso · owner Luigi Boccia · "
        "scadenza 15/10/2026 · stimate 16 h, effettive 6 h",
        "- Note del task: Setup 2x2.",
        "- Nota del 12/08/2026: prima sessione ok",
        "- Cambio di stato il 10/08/2026: da fare → in corso",
        "- Commento di Anna Verdi (11/08/2026): servono cavi nuovi",
        "  - **Preparare setup** — completato · owner Anna Verdi · "
        "completato il 05/08/2026",
        "### Task completati nel mese",
        "- **Simulazioni EM** — completato",
        "| Luigi Boccia | 64 |",
        "| **Totale** | **104** |",
        "- Luigi Boccia — ESTEC (25/08/2026 – 26/08/2026): Progress meeting",
        "kick-off fase 2",
    ):
        assert atteso in md, atteso
    assert ISTRUZIONI_DEFAULT not in md  # ci sono istruzioni specifiche


def test_genera_md_progetto_vuoto_usa_default():
    p = _pack()
    p["progetto"]["istruzioni"] = None
    for k in (
        "deliverables",
        "milestone",
        "task_attivi",
        "task_completati",
        "ore_timesheet",
        "missioni",
        "commenti_progetto",
    ):
        p[k] = []
    md = genera_md(p)
    assert ISTRUZIONI_DEFAULT in md
    assert "Nessun deliverable registrato." in md
    assert "Nessun task attivo nel mese." in md
    assert "Nessuna ora registrata" in md
