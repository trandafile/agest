"""Notifiche e-mail per i task (v3, come MAIC tasks): briefing settimanale
del lunedì e avviso «scadenza passata ieri», con deduplica a DB.

Il modulo NON importa Streamlit: lo usa anche `scripts/send_reminders.py`
lanciato da GitHub Actions (l'app su Streamlit Cloud dorme quando inattiva,
quindi lo scheduler in-app da solo non basta).

Configurazione (variabili d'ambiente / secrets):
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  APP_URL (link nel messaggio), NOTIFICHE_ATTIVE ("1"/"0").
Senza SMTP_PASSWORD le funzioni di invio si limitano a loggare (dry-run).

Deduplica:
  * briefing: una volta per settimana ISO e persona (`persona.last_reminder_sent`);
  * avviso scaduto: una volta per task (`task.last_reminder_sent`).
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage

from src.lib import email_html as eh

log = logging.getLogger(__name__)

ATTIVI = ("da_fare", "in_corso", "bloccato")
STATO_TXT = {
    "da_fare": "Da fare",
    "in_corso": "In corso",
    "bloccato": "Bloccato",
    "completato": "Completato",
    "annullato": "Annullato",
}


@dataclass(frozen=True)
class ConfigSMTP:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    mittente: str = ""
    app_url: str = ""
    attive: bool = True

    @property
    def configurato(self) -> bool:
        return bool(
            self.attive and self.host and self.password and (self.mittente or self.user)
        )

    @classmethod
    def da_ambiente(cls, env: dict | None = None) -> ConfigSMTP:
        e = env if env is not None else os.environ
        return cls(
            host=e.get("SMTP_HOST", ""),
            port=int(e.get("SMTP_PORT", "587") or 587),
            user=e.get("SMTP_USER", ""),
            password=e.get("SMTP_PASSWORD", ""),
            mittente=e.get("SMTP_FROM", "") or e.get("SMTP_USER", ""),
            app_url=e.get("APP_URL", "https://antgest.streamlit.app"),
            attive=str(e.get("NOTIFICHE_ATTIVE", "1")).strip().lower()
            not in ("0", "false", "no", ""),
        )


# ---------------------------------------------------------------------------
# Selezione (pura, testabile)
# ---------------------------------------------------------------------------


def settimana_iso(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso[0], iso[1]


def deve_inviare_briefing(oggi: date, ultimo_invio: date | None) -> bool:
    """Lunedì (o primo giorno utile della settimana) e non ancora inviato
    in questa settimana ISO."""
    if ultimo_invio is not None and settimana_iso(ultimo_invio) == settimana_iso(oggi):
        return False
    return True


def seleziona_briefing(
    tasks: list[dict], persona_id, oggi: date, soglia_giorni: int = 14
) -> dict:
    """Sezioni del briefing per una persona.

    `tasks`: [{id, titolo, stato, scadenza, owner_id, supervisor_id,
    completato_il, progetto}].
    """
    miei = [t for t in tasks if t.get("owner_id") == persona_id]
    attivi = [t for t in miei if t.get("stato") in ATTIVI]
    scaduti = sorted(
        (t for t in attivi if t.get("scadenza") and t["scadenza"] < oggi),
        key=lambda t: t["scadenza"],
    )
    in_scadenza = sorted(
        (
            t
            for t in attivi
            if t.get("scadenza")
            and oggi <= t["scadenza"] <= oggi + timedelta(days=soglia_giorni)
        ),
        key=lambda t: t["scadenza"],
    )
    da_sbloccare = [
        t
        for t in tasks
        if t.get("supervisor_id") == persona_id and t.get("stato") == "bloccato"
    ]
    completati = [
        t
        for t in miei
        if t.get("stato") == "completato"
        and t.get("completato_il")
        and t["completato_il"] >= oggi - timedelta(days=7)
    ]
    return {
        "scaduti": scaduti,
        "in_scadenza": in_scadenza,
        "da_sbloccare": da_sbloccare,
        "attivi": sorted(
            attivi, key=lambda t: (t.get("scadenza") or date.max, t.get("titolo") or "")
        ),
        "completati": completati,
    }


def scaduti_ieri(tasks: list[dict], oggi: date) -> list[dict]:
    ieri = oggi - timedelta(days=1)
    return [
        t
        for t in tasks
        if t.get("stato") in ATTIVI
        and t.get("scadenza") == ieri
        and not t.get("last_reminder_sent")
    ]


# ---------------------------------------------------------------------------
# Rendering (HTML a tabelle e stili inline: Gmail/Outlook-safe; mattoni in
# src/lib/email_html.py, stessa disciplina di MAIC tasks)
# ---------------------------------------------------------------------------


def _riga(t: dict) -> dict:
    """Task (dict dal DB) -> riga per email_html.riga_task."""
    return {
        "titolo": t.get("titolo") or "",
        "stato": t.get("stato"),
        "scadenza": t.get("scadenza"),
        "progetto": t.get("progetto"),
    }


def html_briefing(
    nome: str, sezioni: dict, oggi: date, app_url: str
) -> tuple[str, str]:
    """(html, testo) del briefing settimanale."""
    n_comp = len(sezioni["completati"])
    corpo = eh.paragrafo(
        f"Ciao <b>{eh.esc(nome)}</b>, ecco il quadro dei tuoi task per la settimana."
    )
    corpo += eh.riquadri(
        [
            (
                "scaduti",
                len(sezioni["scaduti"]),
                "scaduto" if sezioni["scaduti"] else "ok",
            ),
            (
                "in scadenza",
                len(sezioni["in_scadenza"]),
                "in_scadenza" if sezioni["in_scadenza"] else "normale",
            ),
            (
                "da sbloccare",
                len(sezioni["da_sbloccare"]),
                "bloccato" if sezioni["da_sbloccare"] else "normale",
            ),
            ("attivi", len(sezioni["attivi"]), "info"),
        ]
    )
    if n_comp:
        corpo += eh.paragrafo(
            f"Nell'ultima settimana hai completato <b>{n_comp}</b> task: "
            + ", ".join(eh.esc(t.get("titolo")) for t in sezioni["completati"][:6])
            + ("…" if n_comp > 6 else "."),
            size=13,
            colore=eh.MUTED,
        )
    corpo += eh.sezione(
        "SCADUTI", "scaduto", [_riga(t) for t in sezioni["scaduti"]], oggi
    )
    corpo += eh.sezione(
        "IN SCADENZA ENTRO 14 GIORNI",
        "in_scadenza",
        [_riga(t) for t in sezioni["in_scadenza"]],
        oggi,
    )
    corpo += eh.sezione(
        "DA SBLOCCARE (sei supervisor)",
        "bloccato",
        [_riga(t) for t in sezioni["da_sbloccare"]],
        oggi,
    )
    corpo += eh.sezione(
        "TUTTI I TUOI TASK ATTIVI", "info", [_riga(t) for t in sezioni["attivi"]], oggi
    )
    if not sezioni["attivi"] and not sezioni["da_sbloccare"]:
        corpo += eh.paragrafo(
            "Nessun task attivo: buona settimana! 👍", colore=eh.MUTED
        )
    corpo_html = eh.cornice(
        anteprima=(
            f"{len(sezioni['scaduti'])} scaduti · {len(sezioni['in_scadenza'])} in "
            f"scadenza · {len(sezioni['attivi'])} attivi"
        ),
        titolo=f"Briefing settimanale — {oggi:%d/%m/%Y}",
        corpo_html=corpo,
        app_url=app_url,
        etichetta_bottone="Apri La mia settimana",
    )
    testo = [f"Briefing settimanale {oggi:%d/%m/%Y} — {nome}"]
    for chiave, titolo in (
        ("scaduti", "SCADUTI"),
        ("in_scadenza", "IN SCADENZA"),
        ("da_sbloccare", "DA SBLOCCARE"),
        ("attivi", "ATTIVI"),
    ):
        if sezioni[chiave]:
            testo.append(f"\n{titolo} ({len(sezioni[chiave])}):")
            testo += [
                f" - {t.get('titolo')} [{STATO_TXT.get(t.get('stato'), '')}] "
                f"{t.get('scadenza') or ''}"
                for t in sezioni[chiave]
            ]
    testo.append(f"\n{app_url}")
    return corpo_html, "\n".join(testo)


def html_scaduto(nome: str, t: dict, oggi: date, app_url: str) -> tuple[str, str]:
    """(html, testo) per «scadenza passata ieri»."""
    corpo = eh.paragrafo(
        f"Ciao <b>{eh.esc(nome)}</b>, questo task era in scadenza il "
        f"<b>{eh.fmt_data(t.get('scadenza'))}</b> e risulta ancora aperto."
    )
    corpo += eh.sezione("SCADUTO", "scaduto", [_riga(t)], oggi)
    corpo += eh.paragrafo(
        "Aggiorna lo stato, sposta la scadenza o segnalo come bloccato "
        "indicando cosa manca.",
        size=13,
        colore=eh.MUTED,
    )
    corpo_html = eh.cornice(
        anteprima=f"Scaduto ieri: {t.get('titolo')}",
        titolo="Scadenza passata",
        corpo_html=corpo,
        app_url=app_url,
        etichetta_bottone="Apri il task",
    )
    testo = (
        f"Il task '{t.get('titolo')}' era in scadenza il "
        f"{eh.fmt_data(t.get('scadenza'))} ed e' ancora aperto. {app_url}"
    )
    return corpo_html, testo


# ---------------------------------------------------------------------------
# Invio
# ---------------------------------------------------------------------------


def invia(
    cfg: ConfigSMTP,
    destinatario: str,
    oggetto: str,
    corpo_html: str,
    corpo_testo: str,
    allegati: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Invia via SMTP STARTTLS. In dry-run (SMTP non configurato) logga e
    ritorna False. `allegati`: [(nome_file, contenuto, mime)]."""
    if not cfg.configurato:
        log.info("[dry-run] a %s: %s", destinatario, oggetto)
        return False
    msg = costruisci_messaggio(
        cfg, destinatario, oggetto, corpo_html, corpo_testo, allegati
    )
    with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as s:
        s.starttls()
        if cfg.user:
            s.login(cfg.user, cfg.password)
        s.send_message(msg)
    return True


def costruisci_messaggio(
    cfg: ConfigSMTP,
    destinatario: str,
    oggetto: str,
    corpo_html: str,
    corpo_testo: str,
    allegati: list[tuple[str, bytes, str]] | None = None,
) -> EmailMessage:
    """Messaggio multipart (testo + html [+ allegati]); separato da `invia`
    per essere testabile senza SMTP."""
    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = cfg.mittente or cfg.user
    msg["To"] = destinatario
    msg.set_content(corpo_testo)
    msg.add_alternative(corpo_html, subtype="html")
    for nome_file, dati, mime in allegati or []:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(
            dati,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=nome_file,
        )
    return msg


# ---------------------------------------------------------------------------
# Notifiche a evento (task assegnato, commento, monthly report pronto)
# ---------------------------------------------------------------------------


def html_task_assegnato(
    nome: str, t: dict, da_chi: str, app_url: str
) -> tuple[str, str]:
    """(html, testo) per «ti è stato assegnato un task»."""
    oggi = date.today()
    corpo = eh.paragrafo(
        f"Ciao <b>{eh.esc(nome)}</b>, <b>{eh.esc(da_chi)}</b> ti ha assegnato un task."
    )
    corpo += eh.sezione(
        "NUOVO TASK",
        "info",
        [
            {
                "titolo": t.get("titolo"),
                "stato": t.get("stato") or "da_fare",
                "scadenza": t.get("scadenza"),
                "progetto": t.get("progetto"),
            }
        ],
        oggi,
    )
    if t.get("descrizione"):
        corpo += eh.citazione(str(t["descrizione"])[:600])
    corpo_html = eh.cornice(
        anteprima=f"{da_chi} ti ha assegnato: {t.get('titolo')}",
        titolo="Nuovo task assegnato",
        corpo_html=corpo,
        app_url=app_url,
        etichetta_bottone="Apri i miei task",
    )
    scad = t.get("scadenza")
    testo = (
        f"{da_chi} ti ha assegnato il task '{t.get('titolo')}'"
        + (f" ({t['progetto']})" if t.get("progetto") else "")
        + (f", scadenza {scad:%d/%m/%Y}" if isinstance(scad, date) else "")
        + f". {app_url}"
    )
    return corpo_html, testo


def html_commento(
    nome: str, titolo_entita: str, autore: str, testo_commento: str, app_url: str
) -> tuple[str, str]:
    """(html, testo) per «nuovo commento su …»."""
    corpo = eh.paragrafo(
        f"Ciao <b>{eh.esc(nome)}</b>, <b>{eh.esc(autore)}</b> ha commentato "
        f"<b>{eh.esc(titolo_entita)}</b>:"
    )
    corpo += eh.citazione(testo_commento)
    corpo += eh.paragrafo(
        "Rispondi dal gestionale: il commento resta nella cronaca del task e "
        "finisce nel monthly report.",
        size=13,
        colore=eh.MUTED,
    )
    corpo_html = eh.cornice(
        anteprima=f"{autore}: {testo_commento[:80]}",
        titolo="Nuovo commento",
        corpo_html=corpo,
        app_url=app_url,
        etichetta_bottone="Rispondi nel gestionale",
    )
    testo = f"{autore} ha commentato '{titolo_entita}': {testo_commento}\n{app_url}"
    return corpo_html, testo


def html_monthly_pronto(
    nome: str, etichetta: str, anno: int, mese: int, app_url: str
) -> tuple[str, str]:
    """(html, testo) per «il file del monthly report è pronto»."""
    mesi = [
        "",
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ]
    mese_txt = f"{mesi[mese]} {anno}"
    corpo = eh.paragrafo(
        f"Ciao <b>{eh.esc(nome)}</b>, è pronto il file per il <b>monthly report di "
        f"{eh.esc(mese_txt)}</b> del progetto {eh.chip_progetto(etichetta)}. "
        "Lo trovi in allegato e nella Dashboard."
    )
    corpo += eh.elenco_passi(
        [
            "Apri il file <b>.md</b> e compila la sezione «Note del responsabile».",
            "Incolla l'intero file in ChatGPT o Claude: produrrà la bozza del report.",
            "Rifinisci la bozza e segna il report come <b>completato</b> in "
            "Progetti → Monthly report.",
        ]
    )
    corpo_html = eh.cornice(
        anteprima=f"Monthly report {etichetta} — {mese_txt}: file pronto",
        titolo=f"Monthly report {etichetta} — {mese_txt}",
        corpo_html=corpo,
        app_url=app_url,
        etichetta_bottone="Apri la Dashboard",
    )
    testo = (
        f"E' pronto il file per il monthly report di {mese_txt} del progetto "
        f"{etichetta} (in allegato). Compila le note del responsabile, incollalo in "
        f"ChatGPT/Claude e segna il report come completato nel gestionale. {app_url}"
    )
    return corpo_html, testo


# ---------------------------------------------------------------------------
# Esecuzione headless (psycopg diretto, niente pool Streamlit)
# ---------------------------------------------------------------------------

SQL_PERSONE = """
    select id, nome, cognome, email, last_reminder_sent
    from persona where attivo order by cognome
"""
SQL_TASK = """
    select t.id, t.titolo, t.stato, t.scadenza, t.owner_id, t.supervisor_id,
           t.completato_il, t.last_reminder_sent,
           coalesce(i.acronimo, i.titolo) as progetto
    from task t left join iniziativa i on i.id = t.iniziativa_id
    where not t.archiviato
"""


def esegui_reminder(
    conn, cfg: ConfigSMTP, oggi: date | None = None, solo_lunedi: bool = True
) -> dict:
    """Briefing settimanale (lunedì, dedup per settimana ISO) + avvisi
    «scaduto ieri» (dedup per task). `conn` è una connessione psycopg
    (autocommit off: ogni invio riuscito viene committato)."""
    oggi = oggi or date.today()
    esito = {"briefing": 0, "avvisi": 0, "saltati": 0, "dry_run": not cfg.configurato}
    with conn.cursor() as cur:
        cur.execute(SQL_PERSONE)
        cols = [c.name for c in cur.description]
        persone = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        cur.execute(SQL_TASK)
        cols = [c.name for c in cur.description]
        tasks = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    by_owner_email = {p["id"]: p for p in persone}

    # 1) briefing settimanale
    if oggi.weekday() == 0 or not solo_lunedi:
        for p in persone:
            if not deve_inviare_briefing(oggi, p.get("last_reminder_sent")):
                esito["saltati"] += 1
                continue
            sez = seleziona_briefing(tasks, p["id"], oggi)
            if not (sez["attivi"] or sez["da_sbloccare"]):
                esito["saltati"] += 1
                continue
            corpo_html, corpo_txt = html_briefing(p["nome"], sez, oggi, cfg.app_url)
            inviato = invia(
                cfg,
                p["email"],
                f"[ANTECNICA] Briefing settimanale — {oggi:%d/%m/%Y}",
                corpo_html,
                corpo_txt,
            )
            if inviato:
                with conn.cursor() as cur:
                    cur.execute(
                        "update persona set last_reminder_sent = %s where id = %s",
                        (oggi, p["id"]),
                    )
                conn.commit()
                esito["briefing"] += 1

    # 2) avvisi scadenza passata ieri
    for t in scaduti_ieri(tasks, oggi):
        p = by_owner_email.get(t.get("owner_id"))
        if not p:
            continue
        corpo_html, corpo_txt = html_scaduto(p["nome"], t, oggi, cfg.app_url)
        inviato = invia(
            cfg,
            p["email"],
            f"[ANTECNICA] Scadenza passata: {t.get('titolo')}",
            corpo_html,
            corpo_txt,
        )
        if inviato:
            with conn.cursor() as cur:
                cur.execute(
                    "update task set last_reminder_sent = %s where id = %s",
                    (oggi, t["id"]),
                )
            conn.commit()
            esito["avvisi"] += 1
    return esito
