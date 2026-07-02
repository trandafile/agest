"""Import banca — import mensile dell'estratto conto (SOLO admin).

Flusso: carica il file (XML CAMT.053, CSV o PDF), rivedi l'anteprima,
importa. Ogni file è tracciato per hash (niente doppi import). Il file va
archiviato anche nella cartella Drive «Estratti conto bancari pdf - xml»
(se il PC ha Google Drive montato su G:, la copia è automatica).
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auth.session import require_role
from src.data import finanza_repo
from src.domain.models import RuoloSistema
from src.lib.estratto_conto import parse_camt053, parse_pdf, totale

persona = require_role(RuoloSistema.admin)
UTENTE = st.session_state.get("user_email")

DRIVE_DIR = Path(
    "G:/Il mio Drive/Management/Contabilita'/Estratti conto bancari pdf - xml"
)

st.title("Import banca")
st.caption(
    "Import mensile dell'estratto conto. Formati: **XML CAMT.053** (preciso), "
    "**CSV**, **PDF** (best-effort: rivedi sempre l'anteprima)."
)

c1, c2 = st.columns(2)
oggi = date.today()
anno = c1.selectbox("Anno", range(oggi.year - 2, oggi.year + 1), index=2)
mese = c2.selectbox(
    "Mese", range(1, 13), index=oggi.month - 1, format_func=lambda m: f"{m:02d}"
)

file = st.file_uploader("Estratto conto (XML / CSV / PDF)", type=["xml", "csv", "pdf"])

if file is not None:
    contenuto = file.getvalue()
    file_hash = hashlib.sha256(contenuto).hexdigest()
    if finanza_repo.hash_gia_importato(file_hash):
        st.error("Questo file risulta GIÀ importato (stesso contenuto).")
        st.stop()

    nome = file.name.lower()
    try:
        if nome.endswith(".xml"):
            righe = parse_camt053(contenuto)
        elif nome.endswith(".pdf"):
            righe = parse_pdf(contenuto)
        else:
            df_csv = pd.read_csv(file, sep=None, engine="python")
            st.markdown("**Mappatura colonne CSV**")
            colonne = ["(nessuna)"] + list(df_csv.columns)
            m1, m2, m3, m4 = st.columns(4)
            mappa = {}
            for campo, col in zip(
                ("data", "importo", "descrizione", "controparte"),
                (m1, m2, m3, m4),
                strict=True,
            ):
                scelta = col.selectbox(campo, colonne, key=f"csv_{campo}")
                if scelta != "(nessuna)":
                    mappa[campo] = scelta
            from src.lib.estratto_conto import parse_csv_estratto

            righe = parse_csv_estratto(df_csv.to_dict("records"), mappa)
    except Exception as exc:  # noqa: BLE001
        st.error(f"File non interpretabile: {exc}")
        st.stop()

    if not righe:
        st.warning(
            "Nessun movimento riconosciuto nel file. Per i PDF prova con la "
            "versione XML/CSV dell'estratto conto."
        )
        st.stop()

    st.markdown(f"**Anteprima: {len(righe)} movimenti** — correggi se serve.")
    df_prev = pd.DataFrame(righe)
    df_edit = st.data_editor(
        df_prev,
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "importo": st.column_config.NumberColumn("Importo €", min_value=0.0),
            "segno": st.column_config.SelectboxColumn(
                "Segno", options=["entrata", "uscita"]
            ),
            "descrizione": st.column_config.TextColumn("Descrizione", width="large"),
            "controparte": st.column_config.TextColumn("Controparte"),
        },
        num_rows="dynamic",
        use_container_width=True,
        key=f"prev_{file_hash[:8]}",
    )
    st.caption(f"Saldo del file: **{float(totale(righe)):,.2f} €**")

    if st.button("📥 Importa movimenti", type="primary"):
        buone = [
            r for r in df_edit.to_dict("records") if r.get("data") and r.get("importo")
        ]
        n = finanza_repo.import_movimenti(buone, eseguito_da=UTENTE)
        finanza_repo.registra_import(anno, mese, file.name, file_hash, n, UTENTE)
        # copia di archivio nella cartella Drive (solo se montata, es. in locale)
        archiviato = ""
        try:
            if DRIVE_DIR.exists():
                dest = DRIVE_DIR / str(anno)
                dest.mkdir(exist_ok=True)
                (dest / file.name).write_bytes(contenuto)
                archiviato = f" File archiviato in {dest}."
        except Exception:  # noqa: BLE001
            archiviato = ""
        st.success(f"Importati {n} movimenti ({mese:02d}/{anno}).{archiviato}")
        if not archiviato:
            st.info(
                "Ricordati di caricare il file anche nella cartella Drive "
                "«Management/Contabilita'/Estratti conto bancari pdf - xml»."
            )

st.divider()
st.subheader("Import recenti")
storico = finanza_repo.list_import_bancari()
if storico:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Quando": f"{r['caricato_il']:%d/%m/%Y %H:%M}",
                    "Periodo": f"{r['mese']:02d}/{r['anno']}",
                    "File": r["file_name"],
                    "Movimenti": r["n_movimenti"],
                    "Da": r["caricato_da"] or "—",
                }
                for r in storico
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("Nessun import registrato.")
