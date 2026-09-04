"""Presentazioni automatiche (.pptx) sul template ANTECNICA 2026 (v3).

Tre report, come i deck di MAIC tasks ma anche per la parte finanziaria:
  * Report attività   — tutti (il dipendente può limitarsi ai propri task);
  * Report progetto   — SAL di un progetto (importi solo amministratore);
  * Report finanziario — SOLO amministratore (spec §13.1).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth.session import require_login
from src.auth.visibilita import vede_economia, vede_progetto_operativo
from src.data import iniziativa_repo
from src.domain.models import RuoloSistema
from src.lib.labels import etichetta_progetto
from src.lib.pptx_report import (
    build_report_attivita,
    build_report_finanziario,
    build_report_progetto,
)
from src.lib.report_pack import pack_attivita, pack_finanziario, pack_progetto
from src.lib.sostenibilita_calc import BASI

MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

persona = require_login()
is_admin = vede_economia(persona.ruolo_sistema)
oggi = date.today()

st.title("Presentazioni")
st.caption(
    "Report automatici in PowerPoint sul template aziendale 2026: attività, "
    "progetto e (solo amministrazione) finanziario."
)

tabs = ["📋 Report attività", "📁 Report progetto"] + (
    ["💶 Report finanziario"] if is_admin else []
)
tab_att, tab_prog, *resto = st.tabs(tabs)

# --- Report attività ---------------------------------------------------------------
with tab_att:
    st.markdown(
        "Portafoglio (GANTT), sintesi, albero progetto → deliverable → task → "
        "subtask, carico per persona, prossime scadenze."
    )
    c1, c2 = st.columns(2)
    periodo = c1.select_slider(
        "Periodo per «completati/avviati»", [7, 14, 30, 60, 90], value=30
    )
    default_mie = persona.ruolo_sistema == RuoloSistema.dipendente
    solo_mie = c2.checkbox("Solo i miei task (owner/supervisor)", value=default_mie)
    if st.button("⚙️ Genera report attività", type="primary", key="gen_att"):
        with st.spinner("Preparo le slide…"):
            dati = build_report_attivita(
                pack_attivita(persona, solo_mie=solo_mie, periodo_giorni=periodo)
            )
        st.session_state["pptx_att"] = dati
    if st.session_state.get("pptx_att"):
        nome = f"ANTECNICA_report_attivita_{oggi:%Y%m%d}.pptx"
        st.download_button(
            "⬇️ Scarica " + nome, st.session_state["pptx_att"], nome, MIME, key="dl_att"
        )

# --- Report progetto ---------------------------------------------------------------
with tab_prog:
    progetti = [
        i
        for i in iniziativa_repo.list_iniziative()
        if i.tipo == "progetto"
        and (
            is_admin
            or vede_progetto_operativo(persona.ruolo_sistema, persona.id, i)
            or persona.ruolo_sistema == RuoloSistema.dipendente
        )
    ]
    if not progetti:
        st.info("Nessun progetto disponibile.")
    else:
        sel = st.selectbox(
            "Progetto",
            progetti,
            format_func=lambda p: f"[{p.stato}] {etichetta_progetto(p)}",
        )
        economia = is_admin
        st.caption(
            "Stato, cronoprogramma, milestone, albero attività, ore per persona"
            + (
                ", budget vs consuntivo e flussi previsti."
                if economia
                else ". Senza importi (vista operativa)."
            )
        )
        if st.button("⚙️ Genera report progetto", type="primary", key="gen_prog"):
            with st.spinner("Preparo le slide…"):
                dati = build_report_progetto(
                    pack_progetto(persona, sel, economia=economia)
                )
            st.session_state["pptx_prog"] = (str(sel.id), dati)
        if st.session_state.get("pptx_prog") and st.session_state["pptx_prog"][
            0
        ] == str(sel.id):
            acr = (sel.acronimo or sel.codice or "progetto").replace(" ", "_")
            nome = f"ANTECNICA_SAL_{acr}_{oggi:%Y%m%d}.pptx"
            st.download_button(
                "⬇️ Scarica " + nome,
                st.session_state["pptx_prog"][1],
                nome,
                MIME,
                key="dl_prog",
            )

# --- Report finanziario (solo amministratore) ------------------------------------
if is_admin and resto:
    with resto[0]:
        st.markdown(
            "Cruscotto KPI (Piano strategico §6), cassa e backlog, cash flow, "
            "proiezione a scenari, P&L per progetto, ricavi attesi, "
            "stima utile e tasse."
        )
        f1, f2, f3 = st.columns(3)
        anno = f1.selectbox(
            "Anno", range(oggi.year - 1, oggi.year + 2), index=1, key="fin_anno"
        )
        n_mesi = f2.select_slider(
            "Orizzonte proiezione (mesi)", [6, 12, 18, 24, 36], value=24, key="fin_mesi"
        )
        base = f3.selectbox(
            "Base costi mensili",
            [None, *BASI],
            format_func=lambda b: (
                "automatica"
                if b is None
                else {
                    "parametro": "parametro fisso",
                    "storica": "stima storica",
                    "analitica": "analitica",
                }[b]
            ),
            key="fin_base",
        )
        st.warning("Contiene dati riservati: condividere solo con l'amministrazione.")
        if st.button("⚙️ Genera report finanziario", type="primary", key="gen_fin"):
            with st.spinner("Calcolo indicatori e preparo le slide…"):
                dati = build_report_finanziario(
                    pack_finanziario(persona, anno, n_mesi, base)
                )
            st.session_state["pptx_fin"] = dati
        if st.session_state.get("pptx_fin"):
            nome = f"ANTECNICA_report_finanziario_{anno}_{oggi:%Y%m%d}.pptx"
            st.download_button(
                "⬇️ Scarica " + nome,
                st.session_state["pptx_fin"],
                nome,
                MIME,
                key="dl_fin",
            )
