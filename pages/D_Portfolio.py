"""Portfolio pluriennale — GANTT dei progetti e delle proposte (una riga per
iniziativa, esteso per anno), carico previsto per persona/anno, ricavi attesi.

Visibilità (spec §13.1): tutti vedono le barre temporali e il proprio carico;
importi, probabilità, ricavi attesi e piano ore di tutti solo amministratore.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.auth.session import require_login
from src.auth.visibilita import vede_economia
from src.data import iniziativa_repo, portfolio_repo, progetti_repo
from src.domain.portfolio import (
    anni_portfolio,
    carico_per_anno,
    quota_per_anno,
    ricavi_per_anno,
    tabella_saturazione,
)
from src.lib.labels import etichetta_progetto, getf
from src.ui.grafici import (
    AZZURRO,
    COLORE_STATO_INIZIATIVA,
    GRIGIO,
    ROSSO,
    layout_base,
)

persona = require_login()
is_admin = vede_economia(persona.ruolo_sistema)

st.title("Portfolio pluriennale")
st.caption(
    "Progetti in essere e proposte in corso, estesi nel tempo: una riga per "
    "iniziativa, carico previsto per persona e anno"
    + (", ricavi attesi." if is_admin else ".")
)

# --- Dati -------------------------------------------------------------------------
tutte = iniziativa_repo.list_iniziative()
c1, c2, c3 = st.columns([1.2, 1.2, 2])
inc_chiusi = c1.checkbox("Includi progetti chiusi", value=False)
inc_prop = c2.checkbox("Includi proposte", value=True)
oggi = date.today()


def _categoria(i) -> str:
    if i.tipo == "progetto":
        return "Progetto attivo" if i.stato == "attivo" else "Progetto chiuso"
    return "Proposta inviata" if i.stato == "inviata" else "Proposta in bozza"


iniziative = []
for i in tutte:
    if i.tipo == "progetto":
        if i.stato == "chiuso" and not inc_chiusi:
            continue
    else:
        if not inc_prop or i.stato not in ("bozza", "inviata"):
            continue
    if not (i.data_inizio and i.data_fine):
        continue
    iniziative.append(i)

if not iniziative:
    st.info("Nessuna iniziativa con date di inizio e fine.")
    st.stop()

anni = anni_portfolio(
    [{"data_inizio": i.data_inizio, "data_fine": i.data_fine} for i in iniziative]
)
anno_da, anno_a = c3.select_slider(
    "Anni visualizzati", options=anni, value=(anni[0], anni[-1])
)
finestra = [a for a in anni if anno_da <= a <= anno_a]

# --- GANTT ---------------------------------------------------------------------
righe = []
for i in sorted(iniziative, key=lambda x: (x.data_inizio, x.titolo)):
    r = {
        "Iniziativa": etichetta_progetto(i),
        "Inizio": i.data_inizio,
        "Fine": i.data_fine + timedelta(days=1),  # px.timeline: estremo escluso
        "Categoria": _categoria(i),
        "Controparte": i.controparte or "—",
        "Durata (mesi)": round((i.data_fine - i.data_inizio).days / 30.4, 1),
    }
    if is_admin:
        imp = getf(i, "importo_riferimento")
        r["Importo €"] = f"{float(imp):,.0f}" if imp else "—"
        r["Probabilità"] = (
            f"{float(i.probabilita_successo) * 100:.0f}%"
            if i.tipo == "proposta" and i.probabilita_successo is not None
            else "—"
        )
    righe.append(r)

df = pd.DataFrame(righe)
hover = ["Controparte", "Durata (mesi)"] + (
    ["Importo €", "Probabilità"] if is_admin else []
)
fig = px.timeline(
    df,
    x_start="Inizio",
    x_end="Fine",
    y="Iniziativa",
    color="Categoria",
    color_discrete_map=COLORE_STATO_INIZIATIVA,
    hover_data=hover,
    category_orders={"Categoria": list(COLORE_STATO_INIZIATIVA)},
)
fig.update_yaxes(autorange="reversed", title=None)
fig.update_traces(marker_line_color=GRIGIO, marker_line_width=0.5)

# milestone come marker sulle barre (tutte, non sono dati sensibili)
ms_x, ms_y, ms_txt = [], [], []
for i in iniziative:
    if i.tipo != "progetto":
        continue
    for m in progetti_repo.list_milestones(i.id):
        if (
            m.data_prevista
            and finestra
            and finestra[0] <= m.data_prevista.year <= finestra[-1]
        ):
            ms_x.append(m.data_prevista)
            ms_y.append(etichetta_progetto(i))
            ms_txt.append(f"{m.titolo} ({m.stato})")
if ms_x:
    fig.add_trace(
        go.Scatter(
            x=ms_x,
            y=ms_y,
            mode="markers",
            name="Milestone",
            marker={
                "symbol": "diamond",
                "size": 9,
                "color": ROSSO,
                "line": {"width": 1, "color": "white"},
            },
            text=ms_txt,
            hovertemplate="%{text}<br>%{x|%d/%m/%Y}<extra></extra>",
        )
    )

# linee di separazione degli anni + oggi
for a in finestra:
    fig.add_shape(
        type="line",
        x0=date(a, 1, 1),
        x1=date(a, 1, 1),
        y0=0,
        y1=1,
        yref="paper",
        line={"color": "#C9D1D9", "width": 1, "dash": "dot"},
    )
fig.add_shape(
    type="line",
    x0=oggi,
    x1=oggi,
    y0=0,
    y1=1,
    yref="paper",
    line={"color": AZZURRO, "width": 2},
)
fig.add_annotation(
    x=oggi, y=1.02, yref="paper", text="oggi", showarrow=False, font={"color": AZZURRO}
)
fig.update_xaxes(
    range=[date(finestra[0], 1, 1), date(finestra[-1], 12, 31)],
    dtick="M12",
    tickformat="%Y",
    ticklabelmode="period",
    title=None,
)
layout_base(
    fig, altezza=max(320, 60 + 34 * len(df)), title="Linea temporale del portafoglio"
)
st.plotly_chart(fig, use_container_width=True)

# --- Ricavi attesi per anno (solo amministratore) -------------------------------
if is_admin:
    st.subheader("Ricavi attesi per anno")
    pesati = st.toggle("Pesa le proposte per probabilità di successo", value=True)
    ric = ricavi_per_anno(
        [
            {
                "id": i.id,
                "etichetta": etichetta_progetto(i),
                "tipo": i.tipo,
                "stato": i.stato,
                "importo": getf(i, "importo_riferimento"),
                "probabilita": i.probabilita_successo,
                "data_inizio": i.data_inizio,
                "data_fine": i.data_fine,
                "tipo_ricavo": getf(i, "tipo_ricavo", "agevolato"),
                "controparte": i.controparte,
            }
            for i in iniziative
        ],
        pesati=pesati,
    )
    ric = [r for r in ric if r["anno"] in finestra]
    if ric:
        df_r = pd.DataFrame(
            [
                {
                    "Anno": str(r["anno"]),
                    "Iniziativa": r["etichetta"],
                    "Importo €": float(r["importo"]),
                }
                for r in ric
            ]
        )
        fig_r = px.bar(
            df_r,
            x="Anno",
            y="Importo €",
            color="Iniziativa",
            barmode="stack",
            category_orders={"Anno": [str(a) for a in finestra]},
        )
        layout_base(
            fig_r,
            altezza=360,
            title="Finanziamento/budget distribuito pro-rata sugli anni",
        )
        st.plotly_chart(fig_r, use_container_width=True)
        piv = df_r.pivot_table(
            index="Iniziativa",
            columns="Anno",
            values="Importo €",
            aggfunc="sum",
            fill_value=0.0,
        )
        piv.loc["TOTALE"] = piv.sum()
        st.dataframe(piv.style.format("{:,.0f}"), use_container_width=True)
    st.caption(
        "Importo = finanziamento complessivo se noto, altrimenti budget; le "
        "proposte in bozza/inviate entrano pesate per la probabilità "
        "(impostabile nella pagina Proposte)."
    )

# --- Carico per persona e anno ----------------------------------------------------
st.subheader("Carico previsto per persona e anno")
assegnazioni = portfolio_repo.assegnazioni_portfolio()
piani = portfolio_repo.piani_ore_anno()
persone_cap = portfolio_repo.persone_capacity()
if not is_admin:
    persone_cap = [p for p in persone_cap if p["id"] == str(persona.id)]
    assegnazioni = [a for a in assegnazioni if a["persona_id"] == str(persona.id)]

righe_carico = [r for r in carico_per_anno(assegnazioni, piani) if r.anno in finestra]
sat = tabella_saturazione(righe_carico, persone_cap, finestra)

if not righe_carico:
    st.info(
        "Nessuna assegnazione pianificata. Le ore per persona si impostano nelle "
        "assegnazioni di proposte/progetti (e, per anno, nell'editor qui sotto)."
    )
else:
    df_sat = pd.DataFrame(sat)
    piv_sat = df_sat.pivot(index="nome", columns="anno", values="saturazione")
    st.markdown(
        "**Saturazione** (ore impegnate su progetti attivi + potenziali da "
        "proposte pesate, / disponibili)"
    )

    def _cella(v):
        if v is None or pd.isna(v):
            return ""
        v = float(v)
        if v > 100:
            return f"background-color:{ROSSO}33"
        if v > 85:
            return "background-color:#E0A02033"
        return ""

    st.dataframe(
        piv_sat.style.format(lambda v: "" if pd.isna(v) else f"{v:.0f}%").map(_cella),
        use_container_width=True,
    )
    for r in sat:
        if r["sovrallocata"]:
            st.warning(
                f"⚠️ {r['nome']} — {r['anno']}: "
                f"{float(r['impegnate'] + r['potenziali']):g} h "
                f"pianificate su {float(r['disponibili']):g} h disponibili."
            )

    sel_p = st.selectbox(
        "Dettaglio persona",
        persone_cap,
        format_func=lambda p: p["nome"],
    )
    if sel_p:
        mie = [r for r in righe_carico if r.persona_id == sel_p["id"]]
        cons = portfolio_repo.ore_consuntivo_per_anno()
        df_p = pd.DataFrame(
            [
                {
                    "Anno": str(r.anno),
                    "Iniziativa": r.etichetta
                    + (" (proposta)" if r.tipo == "proposta" else ""),
                    "Ore": float(r.ore),
                    "Fonte": "piano annuale" if r.esplicito else "pro-rata",
                }
                for r in mie
            ]
        )
        if not df_p.empty:
            fig_c = px.bar(
                df_p,
                x="Anno",
                y="Ore",
                category_orders={"Anno": [str(a) for a in finestra]},
                color="Iniziativa",
                barmode="stack",
                hover_data=["Fonte"],
            )
            disp = [r for r in sat if r["persona_id"] == sel_p["id"]]
            fig_c.add_trace(
                go.Scatter(
                    x=[str(r["anno"]) for r in disp],
                    y=[float(r["disponibili"]) for r in disp],
                    mode="lines+markers",
                    name="Ore disponibili",
                    line={"color": GRIGIO, "dash": "dash"},
                )
            )
            cons_p = [
                {"Anno": str(a), "Ore a timesheet": float(v)}
                for (pid, _iid, a), v in cons.items()
                if pid == sel_p["id"] and a in finestra
            ]
            if cons_p:
                df_cons = pd.DataFrame(cons_p).groupby("Anno", as_index=False).sum()
                fig_c.add_trace(
                    go.Scatter(
                        x=df_cons["Anno"],
                        y=df_cons["Ore a timesheet"],
                        mode="markers",
                        name="Consuntivo (timesheet)",
                        marker={"symbol": "x", "size": 11, "color": ROSSO},
                    )
                )
            layout_base(fig_c, altezza=360, title=f"Ore pianificate — {sel_p['nome']}")
            st.plotly_chart(fig_c, use_container_width=True)
            st.dataframe(
                df_p.pivot_table(
                    index="Iniziativa",
                    columns="Anno",
                    values="Ore",
                    aggfunc="sum",
                    fill_value=0.0,
                ).style.format("{:,.0f}"),
                use_container_width=True,
            )

# --- Editor piano ore per anno (solo amministratore) ------------------------------
if is_admin:
    st.subheader("Piano ore per anno")
    st.caption(
        "Come il foglio «impegno ore»: per ogni assegnazione, le ore previste in "
        "ciascun anno. Se non compilato, il portfolio distribuisce pro-rata le "
        "ore pianificate totali sui giorni dell'iniziativa."
    )
    ini_sel = st.selectbox(
        "Iniziativa",
        iniziative,
        format_func=lambda i: f"[{i.stato}] {etichetta_progetto(i)}",
        key="piano_ini",
    )
    ass_ini = [
        a
        for a in portfolio_repo.assegnazioni_portfolio()
        if a["iniziativa_id"] == str(ini_sel.id)
    ]
    if not ass_ini:
        st.info(
            "Nessuna assegnazione su questa iniziativa: creale in Proposte/Progetti."
        )
    else:
        anni_ini = list(range(ini_sel.data_inizio.year, ini_sel.data_fine.year + 1))
        piani_ini = portfolio_repo.piani_ore_anno(ini_sel.id)
        righe_ed = []
        for a in ass_ini:
            esplicito = {
                an: piani_ini.get((a["assegnazione_id"], an)) for an in anni_ini
            }
            if any(v is not None for v in esplicito.values()):
                valori = {an: float(v or 0) for an, v in esplicito.items()}
                fonte = "piano annuale"
            else:
                q = quota_per_anno(
                    a["data_inizio"],
                    a["data_fine"],
                    a["ore_pianificate"],
                    Decimal("0.1"),
                )
                valori = {an: float(q.get(an, 0)) for an in anni_ini}
                fonte = "pro-rata (proposto)"
            righe_ed.append(
                {
                    "_id": a["assegnazione_id"],
                    "Persona": a["nome"],
                    "Ore totali": float(a["ore_pianificate"] or 0),
                    "Fonte": fonte,
                    **{str(an): valori[an] for an in anni_ini},
                }
            )
        df_ed = pd.DataFrame(righe_ed)
        edit = st.data_editor(
            df_ed.drop(columns=["_id"]),
            hide_index=True,
            use_container_width=True,
            disabled=["Persona", "Ore totali", "Fonte"],
            column_config={
                str(an): st.column_config.NumberColumn(
                    str(an), min_value=0.0, step=1.0, format="%.0f"
                )
                for an in anni_ini
            },
            key=f"ed_piano_{ini_sel.id}",
        )
        somme = edit[[str(an) for an in anni_ini]].sum(axis=1)
        scarti = [
            f"{r['Persona']}: {float(s):g} h per anno vs {r['Ore totali']:g} h totali"
            for r, s in zip(righe_ed, somme, strict=True)
            if r["Ore totali"] and abs(float(s) - r["Ore totali"]) > 0.5
        ]
        if scarti:
            st.warning(
                "Somma per anno ≠ ore totali dell'assegnazione: " + "; ".join(scarti)
            )
        if st.button("💾 Salva piano ore", type="primary"):
            for r, (_, riga) in zip(righe_ed, edit.iterrows(), strict=True):
                portfolio_repo.salva_piano_ore(
                    r["_id"], {an: float(riga[str(an)] or 0) for an in anni_ini}
                )
            st.success("Piano ore salvato.")
            st.rerun()
