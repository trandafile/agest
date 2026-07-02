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
from src.lib import gdrive
from src.lib.archivio import salva_documento
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

    if st.button("📥 Importa movimenti + conserva file", type="primary"):
        buone = [
            r for r in df_edit.to_dict("records") if r.get("data") and r.get("importo")
        ]
        n = finanza_repo.import_movimenti(buone, eseguito_da=UTENTE)
        finanza_repo.registra_import(anno, mese, file.name, file_hash, n, UTENTE)
        # copia locale nella cartella Drive montata (uso in locale, no Neon)
        copia_locale = False
        try:
            if DRIVE_DIR.exists():
                dest = DRIVE_DIR / str(anno)
                dest.mkdir(exist_ok=True)
                (dest / file.name).write_bytes(contenuto)
                copia_locale = True
        except Exception:  # noqa: BLE001
            pass
        # upload su Google Drive (se configurato) + metadato nel DB
        esito = salva_documento(
            "estratto_conto",
            file.name,
            contenuto,
            file.type,
            anno=anno,
            mese=mese,
            caricato_da=UTENTE,
        )
        msg = f"Importati {n} movimenti ({mese:02d}/{anno})."
        if esito["gdrive"]:
            msg += f" File su [Google Drive]({esito['gdrive']})."
        elif copia_locale:
            msg += f" File copiato in {DRIVE_DIR}\\{anno}."
        elif esito["errore"]:
            msg += f" ⚠️ File NON archiviato: {esito['errore']}"
        st.success(msg)

st.divider()
st.subheader("📁 Archivio estratti conto")
if gdrive.configurato():
    st.caption("✅ I file vengono salvati su **Google Drive** (non nel database).")
else:
    st.caption(
        "⚠️ Google Drive non ancora configurato: per ora i file NON vengono "
        "archiviati online (in locale è comunque salvata la copia in G:). "
        "Vedi sotto «Come attivare la copia su Google Drive» (OAuth consigliato)."
    )

with st.expander("⬆️ Carica un estratto conto (senza importare movimenti)"):
    ac1, ac2 = st.columns(2)
    a_anno = ac1.selectbox(
        "Anno", range(oggi.year - 3, oggi.year + 1), index=3, key="arch_anno"
    )
    a_mese = ac2.selectbox(
        "Mese",
        range(1, 13),
        index=oggi.month - 1,
        format_func=lambda m: f"{m:02d}",
        key="arch_mese",
    )
    a_file = st.file_uploader(
        "PDF / XML dell'estratto conto", type=["pdf", "xml", "csv"], key="arch_up"
    )
    if a_file is not None and st.button(
        "Conserva su Drive", disabled=not gdrive.configurato()
    ):
        esito = salva_documento(
            "estratto_conto",
            a_file.name,
            a_file.getvalue(),
            a_file.type,
            anno=a_anno,
            mese=a_mese,
            caricato_da=UTENTE,
        )
        if esito["gia_presente"]:
            st.warning("File già presente in archivio (stesso contenuto).")
        elif esito["errore"]:
            st.error(esito["errore"])
        else:
            st.success(f"File salvato su [Google Drive]({esito['gdrive']}).")
            st.rerun()

archivio = finanza_repo.list_archivio(categoria="estratto_conto")
if archivio:
    for r in archivio:
        col1, col2 = st.columns([5, 1])
        periodo = (
            f"{r['mese']:02d}/{r['anno']}"
            if r["mese"] and r["anno"]
            else str(r["anno"] or "—")
        )
        link = f" · [📂 Apri su Drive]({r['gdrive_url']})" if r["gdrive_url"] else ""
        col1.markdown(f"**{periodo}** · {r['file_nome']}{link}")
        if col2.button("🗑", key=f"del_arch_{r['id']}"):
            finanza_repo.delete_file_archivio(r["id"], eseguito_da=UTENTE)
            st.rerun()
else:
    st.info("Nessun estratto conto in archivio.")

with st.expander("↗️ Come attivare la copia su Google Drive"):
    st.markdown(
        "**Consigliato — OAuth (senza chiavi service account):**\n"
        "1. Su Google Cloud crea un **ID client OAuth** di tipo *Desktop app* "
        "e abilita la **Google Drive API**.\n"
        "2. In locale esegui `python scripts/gdrive_oauth.py "
        "--client-id … --client-secret …`, accedi con il tuo account "
        "`@antecnica.it` e acconsenti.\n"
        "3. Copia l'ID della cartella Drive di destinazione (dall'URL) e "
        "incolla il blocco stampato nei **Secrets**:\n"
        '```toml\n[gdrive]\nclient_id = "…"\nclient_secret = "…"\n'
        'refresh_token = "…"\nfolder_estratti = "<ID cartella Drive>"\n```\n'
        "I file finiscono nel **tuo** Drive.\n\n"
        "*In alternativa* (se l'organizzazione consente le chiavi JSON) puoi "
        "usare un **service account** con `service_account = '''{…}'''` + "
        "`folder_estratti`, condividendo la cartella con la sua email."
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
