"""Sostenibilità economica — SOLO amministratore (spec §13.3).

Cruscotto KPI (Piano strategico 2026-2030 §6), proiezione di cassa
pluriennale a scenari (contratti firmati / + pipeline pesata / + pipeline
intera), backlog dei contratti, stima utile e tasse dell'esercizio.
I calcoli stanno in `src/lib/sostenibilita_calc.py` (condivisi col report).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.auth.session import require_role
from src.data import sostenibilita_repo
from src.domain.models import RuoloSistema
from src.domain.sostenibilita import primo_mese_negativo, saldo_minimo
from src.lib.sostenibilita_calc import BASI, calcola
from src.ui.grafici import (
    AZZURRO,
    COLORE_SCENARIO,
    GRIGIO,
    NOME_SCENARIO,
    ROSSO,
    layout_base,
)

persona = require_role(RuoloSistema.admin)

st.title("Sostenibilità economica")
oggi = date.today()

# --- Parametri dell'anno --------------------------------------------------------
anno = st.selectbox("Anno di riferimento", range(oggi.year - 1, oggi.year + 3), index=1)
par = sostenibilita_repo.get_parametri(anno)

with st.expander("⚙️ Parametri dell'anno (costo pieno FTE, costi fissi, aliquota)"):
    st.caption(
        "Dal foglio «Costo Personale»: costo pieno €/h = (personale + costi "
        "indiretti) / (FTE × ore vendibili). L'aliquota stima le imposte "
        "sull'utile (IRES 24% + IRAP 3,9% ≈ 27,9%)."
    )
    with st.form("parametri"):
        p1, p2, p3 = st.columns(3)
        c_fissi = p1.number_input(
            "Costi mensili strutturali € (0 = stima automatica)",
            min_value=0.0,
            step=500.0,
            value=float(par["costi_fissi_mensili"] or 0),
        )
        c_pers = p2.number_input(
            "Costo personale annuo €",
            min_value=0.0,
            step=1000.0,
            value=float(par["costo_personale_annuo"] or 0),
        )
        c_ind = p3.number_input(
            "Costi indiretti annui €",
            min_value=0.0,
            step=1000.0,
            value=float(par["costi_indiretti_annui"] or 0),
        )
        p4, p5, p6 = st.columns(3)
        fte = p4.number_input(
            "Teste dirette (FTE)",
            min_value=0.0,
            step=0.1,
            value=float(par["teste_dirette"] or 0),
        )
        ore_fte = p5.number_input(
            "Ore vendibili per FTE",
            min_value=1,
            step=10,
            value=int(par["ore_vendibili_fte"] or 1620),
        )
        aliq = p6.number_input(
            "Aliquota fiscale stimata",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(par["aliquota_fiscale"] or 0.279),
            format="%.3f",
        )
        saldo_ov = st.number_input(
            "Saldo di cassa verificato € (0 = usa i movimenti importati)",
            min_value=0.0,
            step=1000.0,
            value=float(par["saldo_iniziale"] or 0),
            help="Da usare se lo storico dei movimenti è incompleto.",
        )
        note = st.text_input("Note", value=par["note"] or "")
        if st.form_submit_button("Salva parametri", type="primary"):
            sostenibilita_repo.salva_parametri(
                anno,
                costi_fissi_mensili=c_fissi or None,
                costo_personale_annuo=c_pers or None,
                costi_indiretti_annui=c_ind or None,
                teste_dirette=fte or None,
                ore_vendibili_fte=int(ore_fte),
                aliquota_fiscale=aliq,
                saldo_iniziale=saldo_ov or None,
                note=note or None,
            )
            st.success("Parametri salvati.")
            st.rerun()

# --- Calcolo -----------------------------------------------------------------------
n_mesi = st.slider("Orizzonte di proiezione (mesi)", 6, 36, 24, step=6)
c0 = calcola(anno, n_mesi)  # per le etichette delle opzioni
base_scelta = st.radio(
    "Base dei costi mensili strutturali",
    list(BASI),
    index=list(BASI).index(c0["base_scelta"]),
    format_func=lambda k: c0["opzioni_base"][k],
    horizontal=True,
)
c = c0 if base_scelta == c0["base_scelta"] else calcola(anno, n_mesi, base_scelta)
if c["ignorate"]:
    st.caption(
        "Spese periodiche con periodicità non riconosciuta (escluse): "
        + ", ".join(s.get("descrizione") or "?" for s in c["ignorate"])
    )

# --- Cruscotto KPI ----------------------------------------------------------------
st.subheader("Cruscotto di sostenibilità")
cols = st.columns(4)
for n, k in enumerate(c["kpis"]):
    with cols[n % 4]:
        st.metric(f"{k.semaforo} {k.nome}", k.valore_txt, help=k.descrizione)
        st.caption(f"allarme {k.allarme} · target {k.target}")

s1, s2, s3 = st.columns(3)
s1.metric(
    "Saldo di cassa",
    f"{float(c['saldo']):,.0f} €",
    help="Verificato (parametri) oppure calcolato dai movimenti importati.",
)
s2.metric("Costi mensili strutturali", f"{float(c['costi_mensili']):,.0f} €")
s3.metric(
    "Backlog contratti firmati",
    f"{float(c['backlog_tot']):,.0f} €",
    help="Σ finanziamento − incassato, progetti attivi.",
)
if c["costo_pieno"]:
    st.caption(
        f"Costo pieno per ora: **{float(c['costo_pieno']):,.2f} €/h** · tariffa media "
        f"implicita dei progetti attivi: **{float(c['tariffa_media'] or 0):,.2f} €/h**."
    )
else:
    st.caption(
        "Compila costo personale, costi indiretti e FTE nei parametri per la KPI "
        "tariffa/costo pieno."
    )

# --- Proiezione a scenari ----------------------------------------------------------
st.subheader("Proiezione di cassa a scenari")
fig = go.Figure()
for chiave, righe in c["scenari"].items():
    fig.add_trace(
        go.Scatter(
            x=[f"{r['anno']}-{r['mese']:02d}" for r in righe],
            y=[float(r["saldo"]) for r in righe],
            mode="lines+markers",
            name=NOME_SCENARIO[chiave],
            line={
                "color": COLORE_SCENARIO[chiave],
                "width": 3 if chiave == "pesato" else 2,
            },
        )
    )
fig.add_hline(y=0, line={"color": ROSSO, "width": 1, "dash": "dash"})
layout_base(fig, altezza=400, title="Saldo proiettato per scenario", yaxis_title="€")
st.plotly_chart(fig, use_container_width=True)

for chiave, righe in c["scenari"].items():
    neg = primo_mese_negativo(righe)
    mn = saldo_minimo(righe)
    if neg:
        st.error(
            f"{NOME_SCENARIO[chiave]}: saldo negativo da {neg[1]:02d}/{neg[0]} "
            f"(minimo {float(mn[0]):,.0f} € a {mn[1][1]:02d}/{mn[1][0]})."
        )
    else:
        st.success(
            f"{NOME_SCENARIO[chiave]}: sempre positivo (minimo {float(mn[0]):,.0f} € "
            f"a {mn[1][1]:02d}/{mn[1][0]})."
        )

with st.expander("Dettaglio mensile (scenario pesato)"):
    df_m = pd.DataFrame(
        [
            {
                "Mese": f"{r['anno']}-{r['mese']:02d}",
                "Entrate firmate": float(
                    c["entrate_firmate"].get((r["anno"], r["mese"]), 0)
                ),
                "Pipeline pesata": float(
                    c["pipe_pesata"].get((r["anno"], r["mese"]), 0)
                ),
                "Uscite": float(r["uscite"]),
                "Saldo": float(r["saldo"]),
            }
            for r in c["scenari"]["pesato"]
        ]
    ).set_index("Mese")
    st.dataframe(df_m.style.format("{:,.0f}"), use_container_width=True)

st.markdown("**Totali per anno** (scenario pesato)")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Anno": t["anno"],
                "Entrate €": float(t["entrate"]),
                "Uscite €": float(t["uscite"]),
                "Saldo fine anno €": float(t["saldo_fine"]),
            }
            for t in c["totali_anno"]
        ]
    )
    .set_index("Anno")
    .style.format("{:,.0f}"),
    use_container_width=True,
)

# --- Backlog contratti -----------------------------------------------------------
st.subheader("Backlog dei contratti firmati")
if c["backlog_det"]:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Progetto": d["etichetta"],
                    "Controparte": d["controparte"],
                    "Tipo ricavo": d["tipo_ricavo"],
                    "Importo €": float(d["importo"]),
                    "Incassato €": float(d["incassato"]),
                    "Residuo €": float(d["residuo"]),
                    "Fine": f"{d['data_fine']:%d/%m/%Y}" if d["data_fine"] else "",
                }
                for d in c["backlog_det"]
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("Nessun progetto attivo.")

# --- Storico entrate/uscite per anno ---------------------------------------------
st.subheader("Entrate e uscite per anno (consuntivo)")
storico = [
    r
    for r in sostenibilita_repo.entrate_uscite_per_anno()
    if r["anno"] >= oggi.year - 4
]
if storico:
    fig_s = go.Figure()
    anni_s = [str(r["anno"]) for r in storico]
    fig_s.add_trace(
        go.Bar(
            x=anni_s,
            y=[float(r["entrate"]) for r in storico],
            name="Entrate",
            marker_color=AZZURRO,
        )
    )
    fig_s.add_trace(
        go.Bar(
            x=anni_s,
            y=[float(r["uscite"]) for r in storico],
            name="Uscite",
            marker_color=GRIGIO,
        )
    )
    layout_base(fig_s, altezza=320, barmode="group")
    st.plotly_chart(fig_s, use_container_width=True)

# --- Stima utile e tasse ------------------------------------------------------------
st.subheader(f"Stima utile e tasse {anno}")
stima = c["stima"]
u1, u2, u3, u4 = st.columns(4)
u1.metric("Entrate (consuntivo + previste)", f"{float(stima['entrate']):,.0f} €")
u2.metric("Uscite (consuntivo + previste)", f"{float(stima['uscite']):,.0f} €")
u3.metric("Utile lordo stimato", f"{float(stima['utile_lordo']):,.0f} €")
u4.metric(
    f"Imposte stimate ({float(stima['aliquota']) * 100:.1f}%)",
    f"{float(stima['tasse_stimate']):,.0f} €",
    help=f"Utile netto stimato: {float(stima['utile_netto']):,.0f} €",
)
st.caption(
    f"Consuntivo {anno}: entrate {float(c['cons']['entrate']):,.0f} €, uscite "
    f"{float(c['cons']['uscite']):,.0f} €; il residuo dell'anno viene dallo scenario "
    "pesato (contratti + pipeline × probabilità). Stima gestionale, non un bilancio."
)
