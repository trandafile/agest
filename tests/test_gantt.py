"""Cronoprogramma (src/domain/gantt.py): parsing, mesi↔date, avanzamento."""

from __future__ import annotations

import io
from datetime import date

from src.domain.gantt import (
    infer_kind,
    infer_parent,
    month_end,
    month_of,
    month_start,
    parse_file,
    parse_msproject_xml,
    parse_text,
    progress,
    resolve,
)


def test_mesi_di_progetto():
    s = date(2026, 3, 1)
    assert month_start(s, 1) == date(2026, 3, 1)
    assert month_end(s, 1) == date(2026, 3, 31)
    assert month_end(s, 12) == date(2027, 2, 28)
    assert month_of(s, date(2027, 2, 28)) == 12
    s2 = date(2026, 1, 31)
    assert month_end(s2, 1) == date(2026, 2, 27)
    assert month_start(s2, 2) == date(2026, 2, 28)


def test_kind_e_padre():
    assert infer_kind("WP2") == "wp"
    assert infer_kind("T2.1") == "task"
    assert infer_kind("D3.4") == "deliverable"
    assert infer_kind("MS1") == "milestone"
    assert infer_kind("X", explicit="Milestone") == "milestone"
    known = {"WP1", "T1.1", "1", "1.2"}
    assert infer_parent("T1.2", "task", known) == "WP1"
    assert infer_parent("T1.1.3", "task", known) == "T1.1"
    assert infer_parent("1.2.3", "task", known) == "1.2"
    assert infer_parent("WP1", "wp", known) is None


def test_incolla_da_excel_con_mesi():
    testo = (
        "Codice\tTitolo\tMese inizio\tMese fine\tResponsabile\n"
        "WP1\tGestione\tM1\tM24\tANTECNICA\n"
        "T1.1\tCoordinamento\t1\t24\t\n"
        "D1.1\tPiano di gestione\t\tM3\t\n"
        "WP2\tProgettazione\t\t\t\n"
        "T2.1\tAntenna\tM2\tM10\tMario Rossi\n"
    )
    r = parse_text(testo)
    assert r.ok, r.errors
    by = {x.code: x for x in r.rows}
    assert by["T1.1"].parent_code == "WP1" and by["D1.1"].kind == "deliverable"
    assert by["D1.1"].start_month == 3 == by["D1.1"].end_month
    resolve(r, date(2026, 1, 1))
    # deliverable: consegna alla fine di M3
    assert by["D1.1"].start == by["D1.1"].end == date(2026, 3, 31)
    assert by["T2.1"].start == date(2026, 2, 1) and by["T2.1"].end == date(2026, 10, 31)
    # WP senza periodo: deriva dai figli
    assert by["WP2"].start == date(2026, 2, 1) and by["WP2"].end == date(2026, 10, 31)
    assert not r.errors


def test_csv_con_date_e_errori():
    csv_txt = (
        "code;name;start;finish\n"
        "T1;Uno;2026-01-10;2026-02-10\n"
        "T1;Doppio;2026-01-10;2026-02-10\n"
        "T2;Rovescio;10/05/2026;01/05/2026\n"
    )
    r = resolve(parse_text(csv_txt), None)
    assert any("ripetuto" in e for e in r.errors)
    assert any("precede" in e for e in r.errors)


def test_mesi_senza_inizio_progetto_avvisa():
    r = resolve(parse_text("code,title,start month,end month\nT1,A,1,3\n"), None)
    assert any("data di inizio" in w for w in r.warnings)


def test_xlsx_con_intestazione_spostata():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Cronoprogramma progetto X"])
    ws.append([])
    ws.append(["WBS", "Task Name", "Start", "Finish", "Type"])
    ws.append(["WP1", "Management", date(2026, 1, 1), date(2026, 12, 31), "WP"])
    ws.append(["T1.1", "Kick-off", date(2026, 1, 1), date(2026, 1, 31), None])
    ws.append(["MS1", "Review", date(2026, 6, 30), None, "Milestone"])
    buf = io.BytesIO()
    wb.save(buf)
    r = resolve(parse_file("piano.xlsx", buf.getvalue()), date(2026, 1, 1))
    assert r.ok, r.errors
    by = {x.code: x for x in r.rows}
    assert by["MS1"].kind == "milestone" and by["MS1"].end == date(2026, 6, 30)
    assert by["T1.1"].parent_code == "WP1"


def test_ms_project_xml():
    xml = b"""<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/project">
 <Tasks>
  <Task><UID>0</UID><Name>Progetto</Name></Task>
  <Task><UID>1</UID><Name>Analisi</Name><WBS>1</WBS><OutlineNumber>1</OutlineNumber>
   <OutlineLevel>1</OutlineLevel><Summary>1</Summary>
   <Start>2026-01-05T08:00:00</Start><Finish>2026-03-31T17:00:00</Finish></Task>
  <Task><UID>2</UID><Name>Requisiti</Name><WBS>1.1</WBS><OutlineNumber>1.1</OutlineNumber>
   <OutlineLevel>2</OutlineLevel><Start>2026-01-05T08:00:00</Start>
   <Finish>2026-02-13T17:00:00</Finish></Task>
  <Task><UID>3</UID><Name>Fine analisi</Name><WBS>1.2</WBS><OutlineNumber>1.2</OutlineNumber>
   <OutlineLevel>2</OutlineLevel><Milestone>1</Milestone>
   <Start>2026-03-31T17:00:00</Start><Finish>2026-03-31T17:00:00</Finish></Task>
 </Tasks>
</Project>"""
    r = parse_msproject_xml(xml)
    assert r.ok, r.errors
    assert [x.kind for x in r.rows] == ["wp", "task", "milestone"]
    assert r.rows[1].parent_code == "1" and r.rows[1].end == date(2026, 2, 13)


def test_avanzamento_aggregato_e_ritardi():
    items = [
        {"id": "wp", "parent_id": None, "end": date(2026, 12, 31)},
        {"id": "t1", "parent_id": "wp", "end": date(2026, 3, 31)},
        {"id": "t2", "parent_id": "wp", "end": date(2026, 12, 31)},
    ]
    linked = [
        {"gantt_id": "t1", "status": "completato", "due": None},
        {"gantt_id": "t1", "status": "in_corso", "due": date(2026, 3, 1)},
        {"gantt_id": "t2", "status": "da_fare", "due": date(2027, 2, 1)},
        {"gantt_id": "t2", "status": "annullato", "due": None},
    ]
    p = progress(items, linked, today=date(2026, 6, 1))
    assert p["t1"] == {"n": 2, "done": 1, "pct": 0.5, "late": True, "slip": False}
    assert p["t2"]["slip"] and not p["t2"]["late"]
    assert p["wp"]["n"] == 3 and p["wp"]["done"] == 1
