"""Combinazione delle metriche di report per dipendente (logica pura)."""

from __future__ import annotations

from types import SimpleNamespace

from src.data import report_repo


def test_report_dipendenti_merge(monkeypatch):
    persone = [
        SimpleNamespace(id="p1", nome_completo="Anna Verdi"),
        SimpleNamespace(id="p2", nome_completo="Mario Rossi"),
    ]
    monkeypatch.setattr(
        report_repo,
        "task_stats",
        lambda anno: {
            "p1": {
                "attivi": 3,
                "completati_anno": 5,
                "in_ritardo": 1,
                "ore_stimate": 40.0,
                "puntualita": 80.0,
            }
        },
    )
    monkeypatch.setattr(
        report_repo,
        "ferie_permessi",
        lambda anno: {"p1": {"ferie": 12, "malattia": 2, "permessi_h": 8.0}},
    )
    monkeypatch.setattr(
        report_repo,
        "presenze_stats",
        lambda anno: {"p1": {"giorni": 200, "ore_tot": 1600.0, "ore_medie": 8.0}},
    )
    monkeypatch.setattr(report_repo, "timesheet_ore", lambda anno: {"p1": 1400.0})
    righe = report_repo.report_dipendenti(2026, persone)
    assert len(righe) == 2
    anna = next(r for r in righe if r["persona"] == "Anna Verdi")
    assert anna["task_attivi"] == 3 and anna["ferie_gg"] == 12
    assert anna["ore_medie_gg"] == 8.0 and anna["ore_progettuali"] == 1400.0
    assert anna["puntualita"] == 80.0
    # persona senza dati -> tutto a zero, nessun crash
    mario = next(r for r in righe if r["persona"] == "Mario Rossi")
    assert mario["task_attivi"] == 0 and mario["ferie_gg"] == 0
    assert mario["puntualita"] is None
