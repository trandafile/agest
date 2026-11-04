"""Gantt di progetto — cronoprogramma importato e collegato ai task. SOLO admin.

Il Gantt è il piano (WP, task, deliverable, milestone in date o mesi M1..Mn);
i task dell'app sono l'esecuzione. Qui si importa il Gantt (Excel, CSV,
copia-incolla da Excel, MS Project XML), si trasferiscono le voci nei task
operativi e si collegano i task esistenti alle voci: il Gantt mostra poi
l'avanzamento reale (task completati/totali, ritardi, slittamenti).
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.auth.session import require_role
from src.data import deliverable_repo, gantt_repo, iniziativa_repo, persona_repo
from src.domain.gantt import (
    KIND_LABEL,
    parse_file,
    parse_text,
    progress,
    resolve,
)
from src.domain.models import RuoloSistema
from src.domain.task_import import Persone
from src.lib.labels import etichetta_con_tag

persona = require_role(RuoloSistema.admin)

st.title("Gantt di progetto")
st.caption(
    "Il cronoprogramma della proposta/progetto (WP, task, deliverable, "
    "milestone) collegato ai task operativi: importa il Gantt, trasferisci le "
    "voci in task oppure collega i task esistenti, e segui l'avanzamento reale."
)

if not gantt_repo.disponibile():
    st.warning(
        "Manca la migrazione **0019_gestore_task_gantt.sql**: applicala con "
        "`python scripts/apply_schema.py` e ricarica la pagina."
    )
    st.stop()

iniziative = iniziativa_repo.list_iniziative()
if not iniziative:
    st.info("Nessuna iniziativa.")
    st.stop()
conta = gantt_repo.iniziative_con_gantt()
ini = st.selectbox(
    "Iniziativa",
    sorted(iniziative, key=lambda i: (str(i.id) not in conta, etichetta_con_tag(i))),
    format_func=lambda i: etichetta_con_tag(i)
    + (f"  · 🗓 {conta[str(i.id)]} voci" if str(i.id) in conta else ""),
)
persone = persona_repo.list_persone(solo_attivi=True)
nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
voci = gantt_repo.list_voci(ini.id)

t_gantt, t_imp, t_tras, t_coll = st.tabs(
    ["📊 Cronoprogramma", "📥 Importa", "🔁 Trasferisci in task", "🔗 Collega task"]
)

_ICONA = {"wp": "📁", "task": "▫️", "deliverable": "📦", "milestone": "◆"}
_COLORE = {"wp": "#1F3A5F", "task": "#4F7CAC", "deliverable": "#E07A1F",
           "milestone": "#C0392B"}


def _livello(v: dict, by_id: dict) -> int:
    n, p = 0, v.get("parent_id")
    while p and n < 6:
        n += 1
        p = by_id.get(p, {}).get("parent_id")
    return n


# =====================================================================
# Cronoprogramma
# =====================================================================
with t_gantt:
    if not voci:
        st.info("Nessun Gantt per questa iniziativa: importalo dalla scheda «📥 Importa».")
    else:
        by_id = {v["id"]: v for v in voci}
        lavoro = gantt_repo.lavoro_collegato(ini.id)
        prog = progress(
            [{"id": v["id"], "parent_id": v["parent_id"], "end": v["data_fine"]}
             for v in voci],
            [{"gantt_id": t["gantt_voce_id"], "status": t["stato"], "due": t["scadenza"]}
             for t in lavoro],
        )
        c1, c2, c3 = st.columns(3)
        solo_wp = c1.toggle("Solo WP e milestone", value=False)
        mostra_mesi = c2.toggle("Asse in mesi di progetto", value=False,
                                disabled=not ini.data_inizio)
        oggi = date.today()

        righe, marker = [], []
        for v in voci:
            if solo_wp and v["tipo"] not in ("wp", "milestone"):
                continue
            p = prog.get(v["id"]) or {}
            liv = _livello(v, by_id)
            etichetta = (" " * liv) + f"{v['codice']} {v['titolo']}"
            stato = ""
            if p.get("n"):
                stato = f"{p['done']}/{p['n']} task"
                if p.get("late"):
                    stato += " · ⚠️ in ritardo"
                elif p.get("slip"):
                    stato += " · ↗ scadenze oltre la fine"
            if not v["data_inizio"] or not v["data_fine"]:
                continue
            if v["tipo"] == "milestone" or (v["tipo"] == "deliverable"
                                            and v["data_inizio"] == v["data_fine"]):
                marker.append({"Voce": etichetta, "Data": v["data_fine"],
                               "Tipo": KIND_LABEL[v["tipo"]], "Stato": stato or "—",
                               "tipo": v["tipo"]})
                continue
            righe.append({
                "Voce": etichetta,
                "Inizio": v["data_inizio"],
                "Fine": v["data_fine"] + timedelta(days=1),  # estremo escluso
                "Tipo": KIND_LABEL[v["tipo"]],
                "Mesi": (f"M{v['mese_inizio']}–M{v['mese_fine']}"
                         if v.get("mese_inizio") else ""),
                "Avanzamento": (f"{p['pct'] * 100:.0f}%" if p.get("pct") is not None
                                else "—"),
                "Stato": stato or "nessun task collegato",
                "Responsabile": v.get("responsabile") or "—",
            })
        ordine = [(" " * _livello(v, by_id)) + f"{v['codice']} {v['titolo']}"
                  for v in voci]
        if not righe and not marker:
            st.info("Le voci non hanno date: controlla l'inizio dell'iniziativa o il file.")
        else:
            fig = go.Figure()
            if righe:
                df = pd.DataFrame(righe)
                fig = px.timeline(
                    df, x_start="Inizio", x_end="Fine", y="Voce", color="Tipo",
                    color_discrete_map={KIND_LABEL[k]: c for k, c in _COLORE.items()},
                    hover_data=["Mesi", "Avanzamento", "Stato", "Responsabile"],
                    text="Avanzamento",
                )
                fig.update_traces(textposition="inside", insidetextanchor="start")
            if marker:
                dm = pd.DataFrame(marker)
                fig.add_trace(go.Scatter(
                    x=dm["Data"], y=dm["Voce"], mode="markers",
                    marker={"symbol": "diamond", "size": 12,
                            "color": [_COLORE[t] for t in dm["tipo"]]},
                    name="Milestone / deliverable",
                    hovertext=[f"{r.Tipo}: {r.Stato}" for r in dm.itertuples()],
                ))
            fig.add_vline(x=pd.Timestamp(oggi).value / 1e6, line_dash="dot",
                          line_color="#888")
            presenti = {r["Voce"] for r in righe} | {m["Voce"] for m in marker}
            fig.update_yaxes(autorange="reversed", title=None,
                             categoryorder="array",
                             categoryarray=[o for o in ordine if o in presenti])
            if mostra_mesi and ini.data_inizio:
                from src.domain.gantt import month_start

                ultimo = max(v["mese_fine"] or 0 for v in voci) or 12
                passo = 3 if ultimo > 18 else 1
                fig.update_xaxes(
                    tickvals=[month_start(ini.data_inizio, m)
                              for m in range(1, ultimo + 2, passo)],
                    ticktext=[f"M{m}" for m in range(1, ultimo + 2, passo)],
                )
            fig.update_layout(height=max(320, 28 * len(presenti) + 140),
                              margin={"l": 10, "r": 10, "t": 50, "b": 10},
                              legend={"orientation": "h", "yanchor": "bottom",
                                      "y": 1.02, "x": 0, "title": None})
            st.plotly_chart(fig, use_container_width=True)

        con_deliv = {d["gantt_voce_id"] for d in gantt_repo.deliverable_collegati(ini.id)}
        tab = []
        for v in voci:
            p = prog.get(v["id"]) or {}
            flag = ("⚠️ in ritardo" if p.get("late") else
                    "↗ slittamento" if p.get("slip") else
                    "✅" if p.get("pct") == 1 else "")
            if v["id"] in con_deliv:
                flag = (flag + " 📦 collegato").strip()
            tab.append({
                "Codice": v["codice"],
                "Voce": ("  " * _livello(v, by_id)) + v["titolo"],
                "Tipo": KIND_LABEL.get(v["tipo"], v["tipo"]),
                "Inizio": v["data_inizio"],
                "Fine": v["data_fine"],
                "Mesi": (f"M{v['mese_inizio']}–M{v['mese_fine']}"
                         if v.get("mese_inizio") else ""),
                "Task collegati": f"{p.get('done', 0)}/{p.get('n', 0)}" if p.get("n") else "",
                "Stato": flag,
                "Responsabile": v.get("responsabile") or "",
            })
        st.dataframe(pd.DataFrame(tab), hide_index=True, use_container_width=True,
                     column_config={
                         "Inizio": st.column_config.DateColumn(format="DD/MM/YYYY"),
                         "Fine": st.column_config.DateColumn(format="DD/MM/YYYY"),
                     })
        n_scoll = sum(1 for v in voci if v["tipo"] == "task"
                      and not (prog.get(v["id"]) or {}).get("n"))
        if n_scoll:
            st.caption(f"{n_scoll} task del Gantt senza lavoro collegato: "
                       "usa «🔁 Trasferisci in task» o «🔗 Collega task».")

# =====================================================================
# Importa
# =====================================================================
_TEMPLATE_RIGHE = [
    ["Codice", "Titolo", "Tipo", "Mese inizio", "Mese fine", "Inizio", "Fine",
     "Responsabile", "Padre"],
    ["WP1", "Gestione del progetto", "WP", 1, 24, None, None, "ANTECNICA", None],
    ["T1.1", "Coordinamento tecnico", "Task", 1, 24, None, None, "Luigi Boccia", "WP1"],
    ["D1.1", "Piano di gestione", "Deliverable", None, 3, None, None, None, "WP1"],
    ["MS1", "Kick-off meeting", "Milestone", None, 1, None, None, None, None],
]

_PROMPT_GANTT = """Converti il cronoprogramma (Gantt) che incollo sotto in una tabella con queste colonne, separate da TAB, con una riga di intestazione:
Codice	Titolo	Tipo	Mese inizio	Mese fine	Inizio	Fine	Responsabile	Padre
Regole:
- Codice: WP1, T1.1, D1.1, MS1… (come nel documento; univoco).
- Tipo: WP | Task | Deliverable | Milestone.
- Mese inizio / Mese fine: mesi di progetto (1 = primo mese), se il Gantt è in mesi; altrimenti lascia vuoto e compila Inizio/Fine come AAAA-MM-GG.
- Deliverable e milestone: basta il mese (o la data) di consegna in Mese fine (o Fine).
- Padre: il codice della WP a cui appartiene la voce (vuoto per le WP).
- Responsabile: partner o persona responsabile, se indicato.
Rispondi solo con la tabella, senza testo prima o dopo.

GANTT:
<incolla qui il Gantt, la tabella della proposta o l'elenco di WP/task>"""

with t_imp:
    st.markdown(
        "Formati: **Excel** (.xlsx), **CSV**, righe **copiate da Excel** "
        "(incolla qui sotto), **MS Project XML**. Le intestazioni sono "
        "riconosciute in italiano o inglese; i mesi M1…Mn diventano date "
        f"a partire dall'inizio dell'iniziativa "
        f"({ini.data_inizio:%d/%m/%Y})." if ini.data_inizio else
        "Formati: Excel (.xlsx), CSV, righe copiate da Excel, MS Project XML. "
        "⚠️ L'iniziativa non ha data di inizio: i mesi M1…Mn non potranno "
        "diventare date."
    )
    buf = io.BytesIO()
    pd.DataFrame(_TEMPLATE_RIGHE[1:], columns=_TEMPLATE_RIGHE[0]).to_excel(
        buf, index=False
    )
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Modello Excel", buf.getvalue(), "modello_gantt.xlsx")
    with d2.popover("🤖 Prompt per convertire un Gantt con un LLM"):
        st.code(_PROMPT_GANTT, language="markdown")

    file = st.file_uploader("File del Gantt", type=["xlsx", "xlsm", "csv", "txt", "xml"])
    testo = st.text_area("…oppure incolla le righe (con intestazione)", height=160)
    res = None
    if file is not None:
        res = parse_file(file.name, file.getvalue())
    elif testo.strip():
        res = parse_text(testo)
    if res is not None:
        resolve(res, ini.data_inizio)
        for e in res.errors:
            st.error(e)
        for w in res.warnings:
            st.warning(w)
        if res.rows:
            st.dataframe(
                pd.DataFrame([{
                    "Codice": r.code, "Titolo": r.title,
                    "Tipo": KIND_LABEL[r.kind], "Padre": r.parent_code or "",
                    "Inizio": r.start, "Fine": r.end,
                    "Mesi": (f"M{r.start_month}–M{r.end_month}" if r.start_month else ""),
                    "Responsabile": r.lead or "",
                } for r in res.rows]),
                hide_index=True, use_container_width=True,
            )
        if res.ok:
            esistenti = {v["codice"] for v in voci}
            nuovi = [r for r in res.rows if r.code not in esistenti]
            mancanti = esistenti - {r.code for r in res.rows}
            st.info(
                f"{len(nuovi)} voci nuove, {len(res.rows) - len(nuovi)} aggiornate"
                + (f", {len(mancanti)} già presenti non sono nel file" if mancanti else "")
                + "."
            )
            rimuovi = False
            if mancanti:
                rimuovi = st.checkbox(
                    f"Rimuovi le {len(mancanti)} voci che non sono nel file "
                    "(i task collegati restano, perdono solo il collegamento)"
                )
            if st.button("📥 Importa il Gantt", type="primary"):
                try:
                    c = gantt_repo.importa(ini.id, res.rows, rimuovi_mancanti=rimuovi)
                except Exception as exc:  # noqa: BLE001
                    from src.lib.errori import messaggio_errore_db

                    st.error(messaggio_errore_db(exc))
                else:
                    st.success(
                        f"Gantt importato: {c['inserite']} nuove, {c['aggiornate']} "
                        f"aggiornate, {c['rimosse']} rimosse."
                    )
                    st.rerun()
    if voci:
        with st.expander("🗑 Elimina il Gantt di questa iniziativa"):
            ok = st.checkbox("Confermo: elimina tutte le voci (i task restano)")
            if st.button("Elimina Gantt", disabled=not ok):
                gantt_repo.elimina_gantt(ini.id)
                st.rerun()

# =====================================================================
# Trasferisci in task
# =====================================================================
with t_tras:
    if not voci:
        st.info("Importa prima il Gantt.")
    else:
        lavoro = gantt_repo.lavoro_collegato(ini.id)
        deliv_coll = gantt_repo.deliverable_collegati(ini.id)
        gia = {t["gantt_voce_id"] for t in lavoro} | {d["gantt_voce_id"] for d in deliv_coll}
        mostra_tutte = st.toggle("Mostra anche le voci già collegate", value=False)
        candidati = [v for v in voci if mostra_tutte or v["id"] not in gia]
        st.caption(
            "Task → task (scadenza = fine della voce) · Deliverable → deliverable · "
            "WP → work package · Milestone → milestone di progetto. Ogni elemento "
            "creato resta collegato alla sua voce."
        )
        if not candidati:
            st.success("Tutte le voci hanno già lavoro collegato.")
        else:
            pp = Persone([{"id": p.id, "nome": p.nome, "cognome": p.cognome,
                           "email": p.email} for p in persone])
            nomi_opz = ["—"] + [p.nome_completo for p in persone]
            by_nome = {p.nome_completo: p.id for p in persone}

            def _owner_default(v: dict) -> str:
                if v.get("responsabile"):
                    pid, err, _ = pp.risolvi(v["responsabile"])
                    if pid and not err:
                        return nomi.get(pid, "—")
                return "—"

            df = pd.DataFrame([{
                "Trasferisci": v["tipo"] in ("task", "deliverable") and v["id"] not in gia,
                "Codice": v["codice"],
                "Titolo": v["titolo"],
                "Tipo": KIND_LABEL[v["tipo"]],
                "Fine": v["data_fine"],
                "Owner": _owner_default(v),
                "_id": str(v["id"]),
            } for v in candidati])
            ed = st.data_editor(
                df, hide_index=True, use_container_width=True,
                disabled=["Codice", "Titolo", "Tipo", "Fine"],
                column_order=["Trasferisci", "Codice", "Titolo", "Tipo", "Fine", "Owner"],
                column_config={
                    "Owner": st.column_config.SelectboxColumn(options=nomi_opz),
                    "Fine": st.column_config.DateColumn(format="DD/MM/YYYY"),
                },
                key=f"tras_{ini.id}",
            )
            delivs = deliverable_repo.list_deliverables(ini.id)
            o1, o2, o3 = st.columns(3)
            d_sel = o1.selectbox(
                "Deliverable dei nuovi task",
                [None] + delivs,
                format_func=lambda d: "— nessuno —" if d is None else d.titolo,
            )
            sup = o2.selectbox(
                "Supervisor",
                [None] + persone,
                format_func=lambda p: "—" if p is None else p.nome_completo,
            )
            pref = o3.checkbox("Anteponi il codice al titolo (es. «T2.1 …»)", value=True)
            scelte = ed[ed["Trasferisci"]]
            if st.button(f"🔁 Trasferisci {len(scelte)} voci", type="primary",
                         disabled=scelte.empty):
                v_by = {str(v["id"]): v for v in voci}
                sel = [v_by[i] for i in scelte["_id"]]
                owners = {r["_id"]: by_nome.get(r["Owner"]) for _, r in scelte.iterrows()}
                c = gantt_repo.trasferisci(
                    ini.id, sel, owners,
                    deliverable_id=d_sel.id if d_sel else None,
                    supervisor_id=sup.id if sup else None,
                    prefisso_codice=pref,
                    eseguito_da=persona.email,
                )
                st.success(
                    f"Creati {c['task']} task, {c['deliverable']} deliverable, "
                    f"{c['wp']} work package, {c['milestone']} milestone — "
                    "collegati al Gantt."
                )
                st.rerun()

# =====================================================================
# Collega task esistenti
# =====================================================================
with t_coll:
    if not voci:
        st.info("Importa prima il Gantt.")
    else:
        from src.data import task_repo

        tasks = [t for t in task_repo.list_tasks(iniziativa_id=ini.id) if not t.archiviato]
        delivs = [d for d in deliverable_repo.list_deliverables(ini.id)]
        cod = {v["id"]: v["codice"] for v in voci}
        opz = ["—"] + [f"{v['codice']} {v['titolo']}" for v in voci
                       if v["tipo"] in ("task", "wp", "deliverable", "milestone")]
        by_lab = {f"{v['codice']} {v['titolo']}": v["id"] for v in voci}
        lab_by_id = {v["id"]: f"{v['codice']} {v['titolo']}" for v in voci}
        cosa = st.radio("Collega", ["Task", "Deliverable"], horizontal=True)
        if cosa == "Task":
            righe = [{
                "Task": ("↳ " if t.parent_task_id else "") + t.titolo,
                "Owner": nomi.get(t.owner_id, "—"),
                "Scadenza": t.scadenza,
                "Voce Gantt": lab_by_id.get(t.gantt_voce_id, "—"),
                "_id": str(t.id),
            } for t in tasks]
        else:
            righe = [{
                "Task": d.titolo,
                "Owner": nomi.get(d.owner_id, "—"),
                "Scadenza": d.scadenza,
                "Voce Gantt": lab_by_id.get(getattr(d, "gantt_voce_id", None), "—"),
                "_id": str(d.id),
            } for d in delivs]
        if not righe:
            st.info(f"Nessun {cosa.lower()} nell'iniziativa.")
        else:
            df = pd.DataFrame(righe)
            ed = st.data_editor(
                df, hide_index=True, use_container_width=True,
                disabled=["Task", "Owner", "Scadenza"],
                column_order=["Task", "Owner", "Scadenza", "Voce Gantt"],
                column_config={
                    "Task": st.column_config.TextColumn(cosa),
                    "Voce Gantt": st.column_config.SelectboxColumn(options=opz),
                    "Scadenza": st.column_config.DateColumn(format="DD/MM/YYYY"),
                },
                key=f"coll_{cosa}_{ini.id}",
            )
            cambi = [
                (r["_id"], by_lab.get(r["Voce Gantt"]))
                for (_, r), (_, o) in zip(ed.iterrows(), df.iterrows(), strict=True)
                if r["Voce Gantt"] != o["Voce Gantt"]
            ]
            if st.button(f"💾 Salva {len(cambi)} collegamenti", type="primary",
                         disabled=not cambi):
                gantt_repo.collega_molti(
                    "task" if cosa == "Task" else "deliverable", cambi
                )
                st.success("Collegamenti salvati.")
                st.rerun()
