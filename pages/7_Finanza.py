"""Finanza — SOLO admin (spec §8): import, riconciliazione, dashboard, export."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.auth.session import require_role
from src.data import finanza_repo, iniziativa_repo, persona_repo, progetti_repo
from src.domain.finanza import (
    CAMPI_DOCUMENTO,
    CAMPI_MOVIMENTO,
    PRESET_SHEET_ANTECNICA,
    normalizza_documento,
    normalizza_movimento,
    proiezione_cassa,
    prossimi_mesi,
    tabella_rendicontazione,
)
from src.domain.models import CATEGORIE_BUDGET, RuoloSistema

persona = require_role(RuoloSistema.admin)
UTENTE = st.session_state.get("user_email")

st.title("Finanza")

iniziative = iniziativa_repo.list_iniziative()
ini_by_label = {f"{i.codice or ''} {i.titolo}".strip(): i for i in iniziative}

tab_imp, tab_mov, tab_doc, tab_spese, tab_dash, tab_exp, tab_audit = st.tabs(
    [
        "📥 Import",
        "🏦 Movimenti",
        "🧾 Documenti",
        "🧰 Spese",
        "📈 Dashboard",
        "📤 Export rendicontazione",
        "🛡️ Audit",
    ]
)


def _leggi_file(file) -> pd.DataFrame | None:
    try:
        if file.name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(file)
        return pd.read_csv(file, sep=None, engine="python")
    except Exception as exc:  # noqa: BLE001
        st.error(f"File non leggibile: {exc}")
        return None


# --- Import -------------------------------------------------------------------
with tab_imp:
    st.markdown(
        "Importa il CSV/XLSX esportato dal Google Sheet finanziario e mappa "
        "le colonne sui campi. Le righe senza data o importo vengono scartate."
    )
    destinazione = st.radio(
        "Destinazione", ["Movimenti bancari", "Documenti fiscali"], horizontal=True
    )
    file = st.file_uploader("File CSV o XLSX", type=["csv", "xlsx", "xls"])
    if file is not None:
        df = _leggi_file(file)
        if df is not None and not df.empty:
            st.dataframe(df.head(10), use_container_width=True)
            colonne = ["(nessuna)"] + list(df.columns)
            campi = (
                CAMPI_MOVIMENTO
                if destinazione == "Movimenti bancari"
                else CAMPI_DOCUMENTO
            )
            colonne_set = {str(c).strip() for c in df.columns}
            preset_ok = (
                destinazione == "Movimenti bancari"
                and {"Data", "Importo (€)", "Tipo Transazione"} <= colonne_set
            )
            usa_preset = st.checkbox(
                "Usa il tracciato del Google Sheet finanziario ANTECNICA "
                "(Data / Descrizione / N. Fattura / Tipo / Importo / Categoria / "
                "Progetto / Persona / Note)",
                value=preset_ok,
                disabled=not preset_ok,
            )
            mappa: dict[str, str] = {}
            if usa_preset:
                mappa = {
                    campo: col
                    for campo, col in PRESET_SHEET_ANTECNICA.items()
                    if col in colonne_set
                }
                st.caption("Mappatura automatica applicata. ✔️")
            else:
                st.markdown("**Mappatura colonne → campi**")
                cols = st.columns(min(len(campi), 4))
                for i, campo in enumerate(campi):
                    # pre-seleziona per nome uguale (case-insensitive)
                    idx = next(
                        (
                            j + 1
                            for j, c in enumerate(df.columns)
                            if str(c).strip().lower() == campo.replace("_", " ")
                            or str(c).strip().lower() == campo
                        ),
                        0,
                    )
                    scelta = cols[i % 4].selectbox(campo, colonne, index=idx)
                    if scelta != "(nessuna)":
                        mappa[campo] = scelta

            if st.button("Importa", type="primary"):
                grezze = df.to_dict("records")
                if destinazione == "Movimenti bancari":
                    norm = [normalizza_movimento(r, mappa) for r in grezze]
                    buone = [r for r in norm if r]
                    n = finanza_repo.import_movimenti(buone, eseguito_da=UTENTE)
                else:
                    norm = [normalizza_documento(r, mappa) for r in grezze]
                    buone = [r for r in norm if r]
                    n = finanza_repo.import_documenti(buone, eseguito_da=UTENTE)
                scartate = len(grezze) - len(buone)
                st.success(
                    f"Importate {n} righe"
                    + (
                        f" ({scartate} scartate: data/importo mancanti)."
                        if scartate
                        else "."
                    )
                )


def _selettore_iniziativa(chiave: str):
    label = st.selectbox(
        "Iniziativa (commessa)",
        ["(nessuna)"] + list(ini_by_label),
        key=chiave,
    )
    return None if label == "(nessuna)" else ini_by_label[label].id


# --- Movimenti -----------------------------------------------------------------
with tab_mov:
    anno_m = st.selectbox(
        "Anno",
        range(date.today().year - 3, date.today().year + 1),
        index=3,
        key="anno_mov",
    )
    movimenti = finanza_repo.list_movimenti(anno_m)
    if movimenti:
        titolo_ini = {
            str(i.id): f"{i.codice or ''} {i.titolo}".strip() for i in iniziative
        }
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": f"{m['data']:%d/%m/%Y}",
                        "Importo €": float(m["importo"]),
                        "Segno": (
                            "🟢 entrata" if m["segno"] == "entrata" else "🔴 uscita"
                        ),
                        "Descrizione": m["descrizione"] or "",
                        "Categoria": m.get("categoria") or "",
                        "Persona": m.get("persona_contatto") or "",
                        "Commessa": titolo_ini.get(
                            str(m["iniziativa_id"]), m.get("progetto_label") or "—"
                        ),
                    }
                    for m in movimenti
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.markdown("**Riconciliazione per commessa**")
        da_ric = st.selectbox(
            "Movimento",
            options=[None] + movimenti,
            format_func=lambda m: (
                "—"
                if m is None
                else f"{m['data']:%d/%m} {m['segno']} {float(m['importo']):,.2f}€ "
                f"{(m['descrizione'] or '')[:40]}"
            ),
        )
        ini_id = _selettore_iniziativa("ric_mov")
        if da_ric is not None and st.button("Associa", key="btn_ric_mov"):
            finanza_repo.riconcilia_movimento(da_ric["id"], ini_id, eseguito_da=UTENTE)
            st.rerun()
    else:
        st.info("Nessun movimento per l'anno selezionato: importali dal tab Import.")

# --- Documenti -------------------------------------------------------------------
with tab_doc:
    anno_d = st.selectbox(
        "Anno",
        range(date.today().year - 3, date.today().year + 1),
        index=3,
        key="anno_doc",
    )
    documenti = finanza_repo.list_documenti(anno_d)
    if documenti:
        titolo_ini = {
            str(i.id): f"{i.codice or ''} {i.titolo}".strip() for i in iniziative
        }
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Tipo": "📤 attiva" if d["tipo"] == "attiva" else "📥 passiva",
                        "Numero": d["numero"] or "",
                        "Data": f"{d['data']:%d/%m/%Y}",
                        "Importo €": float(d["importo"]),
                        "Controparte": d["controparte"] or "",
                        "Stato": d["stato_incasso_pagamento"],
                        "Scadenza": (
                            f"{d['data_scadenza']:%d/%m/%Y}"
                            if d["data_scadenza"]
                            else ""
                        ),
                        "Commessa": titolo_ini.get(str(d["iniziativa_id"]), "—"),
                    }
                    for d in documenti
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.markdown("**Riconciliazione per commessa**")
        da_ric = st.selectbox(
            "Documento",
            options=[None] + documenti,
            format_func=lambda d: (
                "—"
                if d is None
                else f"{d['tipo']} {d['numero'] or ''} {d['data']:%d/%m} "
                f"{float(d['importo']):,.2f}€"
            ),
        )
        ini_id = _selettore_iniziativa("ric_doc")
        if da_ric is not None and st.button("Associa", key="btn_ric_doc"):
            finanza_repo.riconcilia_documento(da_ric["id"], ini_id, eseguito_da=UTENTE)
            st.rerun()
    else:
        st.info("Nessun documento per l'anno selezionato.")

# --- Spese --------------------------------------------------------------------------
with tab_spese:
    with st.form("nuova_spesa", clear_on_submit=True):
        f1, f2, f3 = st.columns(3)
        cat = f1.selectbox("Categoria", CATEGORIE_BUDGET)
        imp = f2.number_input("Importo €", min_value=0.0, step=50.0)
        quando = f3.date_input("Data", value=date.today())
        f4, f5 = st.columns(2)
        label = f4.selectbox(
            "Iniziativa (commessa)",
            ["(nessuna)"] + list(ini_by_label),
            key="spesa_ini",
        )
        rif = f5.text_input("Riferimento documento")
        desc = st.text_input("Descrizione")
        if st.form_submit_button("Registra spesa", type="primary") and imp > 0:
            finanza_repo.create_spesa(
                cat,
                imp,
                quando,
                iniziativa_id=(
                    None if label == "(nessuna)" else ini_by_label[label].id
                ),
                descrizione=desc or None,
                riferimento_documento=rif or None,
                eseguito_da=UTENTE,
            )
            st.rerun()
    spese = finanza_repo.list_spese()
    if spese:
        titolo_ini = {
            str(i.id): f"{i.codice or ''} {i.titolo}".strip() for i in iniziative
        }
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": f"{s['data']:%d/%m/%Y}",
                        "Categoria": s["categoria"],
                        "Importo €": float(s["importo"]),
                        "Commessa": titolo_ini.get(str(s["iniziativa_id"]), "—"),
                        "Descrizione": s["descrizione"] or "",
                        "Rif. doc.": s["riferimento_documento"] or "",
                    }
                    for s in spese
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Nessuna spesa registrata.")

# --- Dashboard ---------------------------------------------------------------
with tab_dash:
    saldo = finanza_repo.saldo_attuale()
    ricorrente = finanza_repo.uscite_ricorrenti_stima()
    k1, k2, k3 = st.columns(3)
    k1.metric("Saldo (da movimenti importati)", f"{saldo:,.2f} €")
    k2.metric(
        "Uscite ricorrenti stimate",
        f"{ricorrente:,.2f} €/mese",
        help="Media delle uscite mensili degli ultimi 3 mesi pieni.",
    )
    k3.metric(
        "Autonomia stimata",
        f"{saldo / ricorrente:.1f} mesi" if ricorrente > 0 else "—",
        help="Saldo / uscite ricorrenti (senza nuove entrate).",
    )

    anno_dash = st.selectbox(
        "Anno",
        range(date.today().year - 3, date.today().year + 1),
        index=3,
        key="anno_dash",
    )
    cf = finanza_repo.cash_flow_mensile(anno_dash)
    st.subheader("Cash flow mensile")
    if cf:
        df_cf = pd.DataFrame(
            [
                {
                    "Mese": f"{r['mese']:02d}",
                    "Entrate": float(r["entrate"]),
                    "Uscite": -float(r["uscite"]),
                    "Saldo": float(r["entrate"]) - float(r["uscite"]),
                }
                for r in cf
            ]
        ).set_index("Mese")
        st.bar_chart(df_cf[["Entrate", "Uscite"]])
        st.line_chart(df_cf["Saldo"].cumsum().rename("Saldo cumulato"))
    else:
        st.info("Nessun movimento nell'anno.")

    st.subheader("Uscite per categoria")
    per_cat = finanza_repo.uscite_per_categoria(anno_dash)
    if per_cat:
        st.bar_chart(
            pd.DataFrame(
                [
                    {"Categoria": r["categoria"], "Uscite €": float(r["tot"])}
                    for r in per_cat
                ]
            ).set_index("Categoria")
        )

    st.subheader("Proiezione flusso di cassa")
    st.caption(
        "Saldo proiettato = saldo attuale + incassi programmati (documenti "
        "attivi aperti e milestone previste) − pagamenti programmati "
        "(documenti passivi aperti) − uscite ricorrenti stimate."
    )
    n_mesi = st.slider("Orizzonte (mesi)", 3, 18, 6)
    mesi_avanti = prossimi_mesi(date.today(), n_mesi)
    entrate_prog = {
        (r["anno"], r["mese"]): Decimal(r["tot"])
        for r in finanza_repo.entrate_programmate_mensili()
    }
    uscite_prog = {
        (r["anno"], r["mese"]): Decimal(r["tot"])
        for r in finanza_repo.uscite_programmate_mensili()
    }
    proiezione = proiezione_cassa(
        Decimal(str(saldo)),
        mesi_avanti,
        entrate_prog,
        uscite_prog,
        uscita_ricorrente_stimata=Decimal(str(round(ricorrente, 2))),
    )
    df_pro = pd.DataFrame(
        [
            {
                "Mese": f"{r['anno']}-{r['mese']:02d}",
                "Entrate previste": float(r["entrate"]),
                "Uscite previste": float(r["uscite"]),
                "Saldo proiettato": float(r["saldo"]),
            }
            for r in proiezione
        ]
    ).set_index("Mese")
    st.line_chart(df_pro["Saldo proiettato"])
    st.dataframe(df_pro, use_container_width=True)
    negativi = [r for r in proiezione if r["saldo"] < 0]
    if negativi:
        primo = negativi[0]
        st.error(
            f"⚠️ Saldo proiettato NEGATIVO da {primo['mese']:02d}/{primo['anno']}: "
            "valuta di anticipare incassi o rinviare uscite."
        )

    st.subheader("P&L per progetto (movimenti riconciliati)")
    pnl = finanza_repo.pnl_per_progetto()
    if pnl:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Progetto": r["progetto"],
                        "Entrate €": float(r["entrate"]),
                        "Uscite €": float(r["uscite"]),
                        "Saldo €": float(r["saldo"]),
                    }
                    for r in pnl
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Scadenzario (documenti non saldati)")
    scad = finanza_repo.scadenzario()
    if scad:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Scadenza": (f"{(r['data_scadenza'] or r['data']):%d/%m/%Y}"),
                        "Tipo": r["tipo"],
                        "Numero": r["numero"] or "",
                        "Importo €": float(r["importo"]),
                        "Controparte": r["controparte"] or "",
                        "Stato": r["stato_incasso_pagamento"],
                    }
                    for r in scad
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("Nessun documento in sospeso.")

# --- Export rendicontazione --------------------------------------------------
with tab_exp:
    st.markdown(
        "Tabella **ore × tariffa vigente** per iniziativa/persona/periodo, "
        "esportabile in CSV/XLSX per i rendiconti dei finanziatori."
    )
    e1, e2 = st.columns(2)
    label_i = e1.selectbox(
        "Iniziativa", ["(tutte)"] + list(ini_by_label), key="exp_ini"
    )
    persone = persona_repo.list_persone()
    sel_p = e2.selectbox(
        "Persona",
        [None] + persone,
        format_func=lambda p: "(tutte)" if p is None else p.nome_completo,
    )
    e3, e4 = st.columns(2)
    dal = e3.date_input("Dal", value=date(date.today().year, 1, 1))
    al = e4.date_input("Al", value=date.today())

    if st.button("Genera tabella", type="primary"):
        righe = finanza_repo.ore_per_rendicontazione(
            None if label_i == "(tutte)" else ini_by_label[label_i].id,
            sel_p.id if sel_p else None,
            dal,
            al,
        )
        if not righe:
            st.warning("Nessuna ora a timesheet nel periodo/filtri scelti.")
        else:
            tariffe = progetti_repo.tariffe_by_persona(
                list({str(r["persona_id"]) for r in righe})
            )
            tab = tabella_rendicontazione(righe, tariffe)
            df_exp = pd.DataFrame(tab)
            st.dataframe(df_exp, hide_index=True, use_container_width=True)
            tot = df_exp["Costo €"].fillna(0).sum()
            n_senza = int(df_exp["Tariffa €/h"].isna().sum())
            st.metric("Totale costo personale", f"{tot:,.2f} €")
            if n_senza:
                st.warning(f"{n_senza} righe senza tariffa vigente alla data.")
            csv = df_exp.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Scarica CSV", csv, "rendicontazione.csv", "text/csv")
            buf = io.BytesIO()
            df_exp.to_excel(buf, index=False, sheet_name="Rendicontazione")
            st.download_button(
                "⬇️ Scarica XLSX",
                buf.getvalue(),
                "rendicontazione.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# --- Audit -------------------------------------------------------------------
with tab_audit:
    audit = finanza_repo.audit_recenti()
    if audit:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Quando": f"{a['eseguito_il']:%d/%m/%Y %H:%M}",
                        "Tabella": a["tabella"],
                        "Azione": a["azione"],
                        "Utente": a["eseguito_da"] or "—",
                    }
                    for a in audit
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Nessuna voce di audit.")
