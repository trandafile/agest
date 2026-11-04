"""UI dell'import YAML/JSON (pagina Task): verifica → anteprima → import.

Riservato a gestore task e admin (`src.auth.permessi.puo_importare_task`).
"""

from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from src.auth.permessi import puo_importare_task
from src.domain.models import Persona
from src.domain.task_import import (
    GUIDA_MD,
    SCHEMA_YAML,
    Persone,
    costruisci_prompt,
    parse_payload,
    righe_anteprima,
    validate,
)
from src.lib.labels import etichetta_con_tag

_K = "_task_import"


def _dati_iniziativa(ini) -> dict:
    return {
        "id": ini.id,
        "acronimo": getattr(ini, "acronimo", None),
        "codice": getattr(ini, "codice", None),
        "titolo": ini.titolo,
    }


def _valida(ini, testo: str, persona: Persona, consenti_dup: bool):
    from src.data import task_import_repo as repo

    dati, err = parse_payload(testo)
    if err:
        return None, err, None
    snap = repo.istantanea(ini.id)
    persone = repo.persone_attive()
    gantt = repo.voci_gantt(ini.id)
    piano = validate(
        dati,
        _dati_iniziativa(ini),
        snap,
        persone,
        me=str(persona.id),
        consenti_duplicati=consenti_dup,
        gantt_codici={g["codice"]: g["id"] for g in gantt},
    )
    return piano, None, Persone(persone)


def blocco_import(persona: Persona, iniziative: list, persone: list[Persona]) -> None:
    if not puo_importare_task(persona):
        st.info("L'import è riservato ai gestori task e all'amministratore.")
        return
    if not iniziative:
        st.info("Nessuna iniziativa: crea prima un progetto.")
        return
    ini = st.selectbox(
        "Iniziativa in cui importare",
        iniziative,
        format_func=etichetta_con_tag,
        key=f"{_K}_ini",
    )
    t_inc, t_prompt, t_guida = st.tabs(
        ["📋 Incolla e verifica", "🤖 Prompt per LLM", "ℹ️ Guida e schema"]
    )

    with t_guida:
        st.markdown(GUIDA_MD)
        st.code(SCHEMA_YAML, language="yaml")

    with t_prompt:
        st.caption(
            "Copia il prompt in un LLM, aggiungi in fondo cosa vuoi organizzare "
            "e incolla qui la risposta YAML. Contiene lo stato attuale "
            "dell'iniziativa (con i #ref) e i nomi del team."
        )
        if st.button("Genera prompt", key=f"{_K}_genp"):
            from src.data import task_import_repo as repo

            st.session_state[f"{_K}_prompt"] = costruisci_prompt(
                _dati_iniziativa(ini),
                repo.istantanea(ini.id),
                repo.persone_attive(),
                repo.voci_gantt(ini.id),
            )
        if st.session_state.get(f"{_K}_prompt"):
            st.code(st.session_state[f"{_K}_prompt"], language="markdown")

    with t_inc:
        with st.form(f"{_K}_form"):
            testo = st.text_area(
                "Contenuto YAML o JSON",
                height=260,
                placeholder="schema: agest-import/v1\nproject: {code: …}\n…",
            )
            consenti_dup = st.checkbox(
                "Crea comunque gli elementi con titolo già presente",
                help="Solo se sono davvero elementi nuovi: di norma un titolo "
                "uguale sotto lo stesso padre rende il file invalido.",
            )
            verifica = st.form_submit_button("🔍 Verifica", type="primary")
        if verifica:
            piano, err, pp = _valida(ini, testo, persona, consenti_dup)
            st.session_state[_K] = {
                "ini": str(ini.id),
                "hash": hashlib.sha1((testo or "").encode()).hexdigest(),
                "testo": testo,
                "dup": consenti_dup,
                "err": err,
                "piano": piano,
                "pp": pp,
            }

        stato = st.session_state.get(_K)
        if not stato or stato.get("ini") != str(ini.id):
            return
        if stato.get("err"):
            st.error(stato["err"])
            return
        piano, pp = stato["piano"], stato["pp"]
        for e in piano.errors:
            st.error(e)
        for w in piano.warnings:
            st.warning(w)
        if piano.notes:
            st.caption("Nomi interpretati: " + "; ".join(piano.notes))
        righe = righe_anteprima(piano, pp)
        if righe:
            st.dataframe(pd.DataFrame(righe), hide_index=True, use_container_width=True)
        if not piano.ok:
            st.info("Il file non è valido: correggi gli errori e verifica di nuovo.")
            return
        n = piano.counts()
        if not n:
            return
        riepilogo = ", ".join(
            f"{v} {a} {k}" for (k, a), v in sorted(n.items(), key=lambda x: x[0])
        )
        st.success(f"Pronto: {riepilogo}.")
        notifica = st.checkbox(
            "Invia un'e-mail ai nuovi assegnatari", value=False, key=f"{_K}_notif"
        )
        if st.button("📥 Importa", type="primary", key=f"{_K}_go"):
            _importa(ini, stato, persona, persone, notifica)


def _importa(ini, stato: dict, persona: Persona, persone: list[Persona], notifica: bool) -> None:
    from src.data import task_import_repo as repo

    # Rivalida sull'istantanea fresca: se nel frattempo qualcuno ha cambiato
    # l'iniziativa, il piano verificato prima potrebbe non essere più giusto.
    piano, err, _ = _valida(ini, stato["testo"], persona, stato["dup"])
    if err or piano is None or not piano.ok:
        st.error(
            "Nel frattempo l'iniziativa è cambiata e il file non è più valido: "
            "premi di nuovo «Verifica»."
        )
        return
    try:
        fatto, creati = repo.applica_piano(piano, eseguito_da=persona.email)
    except Exception as exc:  # noqa: BLE001
        from src.lib.errori import messaggio_errore_db

        st.error(f"Import interrotto, nessuna modifica scritta: {messaggio_errore_db(exc)}")
        return
    st.session_state.pop(_K, None)
    st.success(f"Import completato: {len(fatto)} modifiche.")
    with st.expander("Dettaglio", expanded=False):
        st.markdown("\n".join(f"- {r}" for r in fatto))
    if notifica and creati:
        _notifica(creati, persona, persone, ini)


def _notifica(creati: list[dict], persona: Persona, persone: list[Persona], ini) -> None:
    from types import SimpleNamespace

    try:
        from src.lib.notifiche_app import notifica_task_assegnato
    except Exception:  # noqa: BLE001
        return
    by_id = {str(p.id): p for p in persone}
    inviate = 0
    for t in creati:
        owner = by_id.get(str(t.get("owner_id") or ""))
        if owner is None:
            continue
        scad = t.get("scadenza")
        if isinstance(scad, str):
            from datetime import date

            scad = date.fromisoformat(scad[:10])
        task = SimpleNamespace(titolo=t.get("titolo"), scadenza=scad)
        try:
            if notifica_task_assegnato(task, owner, persona, progetto=etichetta_con_tag(ini)):
                inviate += 1
        except Exception:  # noqa: BLE001 — le notifiche non bloccano mai
            pass
    if inviate:
        st.caption(f"✉️ {inviate} e-mail di assegnazione in invio.")
