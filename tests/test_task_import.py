"""Import YAML/JSON di deliverable/task/subtask (src/domain/task_import.py)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.task_import import (
    Persone,
    costruisci_prompt,
    parse_payload,
    ref_breve,
    righe_anteprima,
    validate,
)

INI = {"id": "11111111-1111-1111-1111-111111111111", "acronimo": "SHIFT",
       "codice": None, "titolo": "Satellite Hub"}
MARIO = UUID("aaaaaaaa-0000-0000-0000-000000000001")
ANNA = UUID("bbbbbbbb-0000-0000-0000-000000000002")
LUIGI = UUID("cccccccc-0000-0000-0000-000000000003")
PERSONE = [
    {"id": MARIO, "nome": "Mario", "cognome": "Rossi", "email": "mario.rossi@antecnica.it"},
    {"id": ANNA, "nome": "Anna", "cognome": "Verdi", "email": "anna.verdi@antecnica.it"},
    {"id": LUIGI, "nome": "Luigi", "cognome": "Boccia", "email": "luigi.boccia@antecnica.it"},
]
D1 = UUID("d1d1d1d1-0000-0000-0000-000000000001")
T1 = UUID("e1e1e1e1-0000-0000-0000-000000000001")
T2 = UUID("e2e2e2e2-0000-0000-0000-000000000002")
S1 = UUID("f1f1f1f1-0000-0000-0000-000000000001")


def _snap():
    return {
        "deliverables": [
            {"id": D1, "titolo": "Report finale", "tipo": "report", "stato": "da_fare",
             "scadenza": date(2027, 1, 31), "owner_id": MARIO, "supervisor_id": None,
             "descrizione": None, "archiviato": False},
        ],
        "tasks": [
            {"id": T1, "deliverable_id": D1, "parent_task_id": None,
             "titolo": "Stesura capitolo 1", "stato": "in_corso", "priorita": "media",
             "owner_id": MARIO, "supervisor_id": LUIGI, "scadenza": None,
             "ore_stimate": Decimal("10"), "descrizione": "bozza", "archiviato": False},
            {"id": S1, "deliverable_id": D1, "parent_task_id": T1,
             "titolo": "Figure", "stato": "da_fare", "priorita": "media",
             "owner_id": ANNA, "supervisor_id": None, "scadenza": None,
             "ore_stimate": None, "descrizione": None, "archiviato": False},
            {"id": T2, "deliverable_id": None, "parent_task_id": None,
             "titolo": "Riunione kick-off", "stato": "da_fare", "priorita": "nessuna",
             "owner_id": LUIGI, "supervisor_id": None, "scadenza": None,
             "ore_stimate": None, "descrizione": None, "archiviato": False},
        ],
    }


def _val(yaml_text, **kw):
    data, err = parse_payload(yaml_text)
    assert err is None, err
    return validate(data, INI, _snap(), PERSONE, me=str(LUIGI), **kw)


def test_parse_json_yaml_e_fence():
    assert parse_payload('{"a": 1}') == ({"a": 1}, None)
    assert parse_payload("```yaml\na: 1\n```")[0] == {"a": 1}
    assert parse_payload("")[1]
    assert "YAML non valido" in parse_payload("a: [1,")[1]


def test_create_completo_con_default_ed_ereditarieta():
    p = _val("""
schema: agest-import/v1
project: {code: SHIFT, name: Satellite Hub}
defaults: {supervisor: Luigi, priority: alta}
deliverables:
  - title: Prototipo antenna
    type: prototype
    owner: Anna Verdi
    due: 2027-03-31
    tasks:
      - title: Layout feed
        assignee: Mario
        due: 15/01/2027
        ore_stimate: 12,5
        subtasks:
          - title: Simulazione transizione
""")
    assert p.ok, p.errors
    d, t, s = p.ops
    assert d.fields["tipo"] == "prototipo" and d.fields["owner_id"] == str(ANNA)
    assert d.fields["iniziativa_id"] == INI["id"]
    assert t.fields["scadenza"] == "2027-01-15" and t.fields["ore_stimate"] == 12.5
    assert t.fields["priorita"] == "alta" and t.fields["supervisor_id"] == str(LUIGI)
    # il subtask eredita owner e supervisor del task
    assert s.fields["owner_id"] == str(MARIO)
    assert s.fields["supervisor_id"] == str(LUIGI)
    assert any("Mario" in n for n in p.notes)
    assert p.counts() == {("deliverable", "create"): 1, ("task", "create"): 1,
                          ("subtask", "create"): 1}


def test_update_con_ref_e_match_title_e_alias_maic():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    tasks:
      - action: update
        ref: "{ref_breve(T1)}"
        match_title: Stesura capitolo 1
        status: Working on
        description_append: rivisto con Luigi
""")
    assert p.ok, p.errors
    t = p.ops[1]
    assert "stato" not in t.fields  # già in corso: nessuna modifica
    assert t.fields["descrizione"] == "bozza\n\nrivisto con Luigi"


def test_ref_che_non_corrisponde_al_titolo_e_errore():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: update
    ref: "{ref_breve(D1)}"
    match_title: Tutt'altro titolo
    title: Nuovo
""")
    assert not p.ok
    assert "match_title" in p.errors[0]


def test_duplicato_bloccato_salvo_consenso():
    yaml_text = f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    tasks:
      - title: Stesura capitolo 1
"""
    assert not _val(yaml_text).ok
    p = _val(yaml_text, consenti_duplicati=True)
    assert p.ok and any("esiste già" in w for w in p.warnings)


def test_altro_progetto_rifiutato():
    p = _val("""
project: {code: ALTRO}
deliverables:
  - title: X
""")
    assert any("non è questa iniziativa" in e for e in p.errors)


def test_nome_ambiguo_e_sconosciuto():
    persone = PERSONE + [{"id": UUID(int=9), "nome": "Mario", "cognome": "Bianchi",
                          "email": "mario.bianchi@antecnica.it"}]
    pp = Persone(persone)
    assert "ambiguo" in pp.risolvi("Mario")[1]
    assert pp.risolvi("Mario Bianchi")[0] == UUID(int=9)
    assert "nessuna persona" in pp.risolvi("Zorro")[1]
    assert pp.risolvi("me")[0] is None  # me non impostato


def test_completare_deliverable_con_task_aperti_e_errore():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: complete
    ref: "{ref_breve(D1)}"
    match_title: Report finale
""")
    assert not p.ok and "aperti" in p.errors[0]
    ok = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: complete
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    tasks:
      - action: complete
        ref: "{ref_breve(T1)}"
        match_title: Stesura capitolo 1
        subtasks:
          - action: cancel
            ref: "{ref_breve(S1)}"
            match_title: Figure
""")
    assert ok.ok, ok.errors
    assert ok.ops[1].fields["completato_il"] == date.today().isoformat()


def test_move_task_senza_deliverable_dentro_d1():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    tasks:
      - action: move
        ref: "{ref_breve(T2)}"
        match_title: Riunione kick-off
""")
    assert p.ok, p.errors
    assert p.ops[1].action == "move"
    # task sotto il deliverable sbagliato senza move -> errore
    q = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    tasks:
      - action: update
        ref: "{ref_breve(T2)}"
        match_title: Riunione kick-off
        priority: alta
""")
    assert not q.ok and "move" in q.errors[0]


def test_contenitore_zero_e_gantt():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "0"
    tasks:
      - action: update
        ref: "{ref_breve(T2)}"
        match_title: Riunione kick-off
        gantt: T1.1
""", gantt_codici={"T1.1": "99999999-0000-0000-0000-000000000000"})
    assert p.ok, p.errors
    assert p.ops[1].fields["gantt_voce_id"] == "99999999-0000-0000-0000-000000000000"
    q = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: keep
    ref: "0"
    tasks:
      - action: update
        ref: "{ref_breve(T2)}"
        match_title: Riunione kick-off
        gantt: T9.9
""")
    assert not q.ok


def test_nessuna_modifica_spuria_su_numeri_e_date():
    p = _val(f"""
project: {{code: SHIFT}}
deliverables:
  - action: update
    ref: "{ref_breve(D1)}"
    match_title: Report finale
    due: 2027-01-31
    tasks:
      - action: update
        ref: "{ref_breve(T1)}"
        match_title: Stesura capitolo 1
        estimate_hours: 10.0
""")
    assert p.ok, p.errors
    assert not p.changes()


def test_anteprima_e_prompt():
    p = _val("""
project: {code: SHIFT}
deliverables:
  - title: Nuovo report
    type: report
""")
    righe = righe_anteprima(p, Persone(PERSONE))
    assert righe[0]["Azione"].endswith("crea")
    prompt = costruisci_prompt(INI, _snap(), PERSONE)
    assert ref_breve(D1) in prompt and "Mario Rossi" in prompt
    assert "agest-import/v1" in prompt
