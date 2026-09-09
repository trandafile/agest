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

import html
import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage

log = logging.getLogger(__name__)

ATTIVI = ("da_fare", "in_corso", "bloccato")
STATO_TXT = {
    "da_fare": "Da fare",
    "in_corso": "In corso",
    "bloccato": "Bloccato",
    "completato": "Completato",
    "annullato": "Annullato",
}
BRAND = "#2E8FC0"
INK = "#0B0F14"
MUTED = "#45535F"


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
# Rendering (HTML tabellare vecchio stile: Gmail-safe, senza immagini)
# ---------------------------------------------------------------------------


def _riga(t: dict, oggi: date) -> str:
    scad = t.get("scadenza")
    if scad:
        delta = (scad - oggi).days
        quando = f"{scad:%d/%m/%Y}" + (
            f" (in ritardo di {-delta} g)"
            if delta < 0
            else (f" (tra {delta} g)" if delta <= 14 else "")
        )
    else:
        quando = "senza scadenza"
    prog = f" · {html.escape(str(t['progetto']))}" if t.get("progetto") else ""
    return (
        f"<tr><td style='padding:4px 8px;border-bottom:1px solid #E1E6EA'>"
        f"<b>{html.escape(t.get('titolo') or '')}</b>{prog}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #E1E6EA;color:{MUTED}'>"
        f"{STATO_TXT.get(t.get('stato'), t.get('stato') or '')}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #E1E6EA;"
        f"color:{MUTED}'>{quando}</td></tr>"
    )


def _sezione(titolo: str, righe: list[dict], oggi: date, vuoto: str = "") -> str:
    if not righe:
        return (
            f"<p style='color:{MUTED};margin:12px 0 4px'><b>{titolo}</b> — {vuoto}</p>"
            if vuoto
            else ""
        )
    corpo = "".join(_riga(t, oggi) for t in righe)
    return (
        f"<p style='margin:16px 0 4px'><b style='color:{BRAND}'>{titolo}</b>"
        f" ({len(righe)})</p>"
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        f"{corpo}</table>"
    )


def html_briefing(
    nome: str, sezioni: dict, oggi: date, app_url: str
) -> tuple[str, str]:
    """(html, testo) del briefing settimanale."""
    parti = [
        "<div style='font-family:Segoe UI,Calibri,Arial,sans-serif;"
        f"color:{INK};max-width:680px'>",
        f"<h2 style='color:{BRAND};margin:0 0 4px'>Briefing settimanale — "
        f"{oggi:%d/%m/%Y}</h2>",
        f"<p>Ciao {html.escape(nome)}, ecco il quadro dei tuoi task.</p>",
    ]
    if sezioni["completati"]:
        parti.append(
            f"<p style='color:{MUTED}'>Nell'ultima settimana hai completato "
            f"<b>{len(sezioni['completati'])}</b> task: "
            + ", ".join(
                html.escape(t.get("titolo") or "") for t in sezioni["completati"][:6]
            )
            + ".</p>"
        )
    parti.append(_sezione("SCADUTI", sezioni["scaduti"], oggi, "nessuno 👍"))
    parti.append(
        _sezione("IN SCADENZA ENTRO 14 GIORNI", sezioni["in_scadenza"], oggi, "nessuno")
    )
    parti.append(
        _sezione("DA SBLOCCARE (sei supervisor)", sezioni["da_sbloccare"], oggi)
    )
    parti.append(
        _sezione("TUTTI I TUOI TASK ATTIVI", sezioni["attivi"], oggi, "nessuno")
    )
    parti.append(
        f"<p style='margin-top:20px'><a href='{html.escape(app_url)}' "
        f"style='color:{BRAND}'>Apri il gestionale</a>"
        f" · <span style='color:{MUTED}'>ANTECNICA Gestionale</span></p></div>"
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
    return "".join(parti), "\n".join(testo)


def html_scaduto(nome: str, t: dict, oggi: date, app_url: str) -> tuple[str, str]:
    corpo = (
        "<div style='font-family:Segoe UI,Calibri,Arial,sans-serif;"
        f"color:{INK};max-width:680px'>"
        f"<h2 style='color:#D9534F;margin:0 0 4px'>Scadenza passata</h2>"
        f"<p>Ciao {html.escape(nome)}, il task "
        f"<b>{html.escape(t.get('titolo') or '')}</b>"
        + (f" ({html.escape(str(t['progetto']))})" if t.get("progetto") else "")
        + f" era in scadenza il <b>{t['scadenza']:%d/%m/%Y}</b> ed è ancora "
        + f"«{STATO_TXT.get(t.get('stato'), '')}».</p>"
        "<p>Aggiorna lo stato o sposta la scadenza: "
        f"<a href='{html.escape(app_url)}' style='color:{BRAND}'>"
        "apri il gestionale</a>.</p></div>"
    )
    testo = (
        f"Il task '{t.get('titolo')}' era in scadenza il "
        f"{t['scadenza']:%d/%m/%Y}. {app_url}"
    )
    return corpo, testo


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


def _cornice(titolo: str, colore: str, corpo: str, app_url: str, link_txt: str) -> str:
    return (
        "<div style='font-family:Segoe UI,Calibri,Arial,sans-serif;"
        f"color:{INK};max-width:680px'>"
        f"<h2 style='color:{colore};margin:0 0 4px'>{titolo}</h2>"
        f"{corpo}"
        f"<p style='margin-top:20px'><a href='{html.escape(app_url)}' "
        f"style='color:{BRAND}'>{link_txt}</a>"
        f" · <span style='color:{MUTED}'>ANTECNICA Gestionale</span></p></div>"
    )


def html_task_assegnato(
    nome: str, t: dict, da_chi: str, app_url: str
) -> tuple[str, str]:
    """(html, testo) per «ti è stato assegnato un task»."""
    scad = t.get("scadenza")
    quando = f" con scadenza <b>{scad:%d/%m/%Y}</b>" if scad else ""
    prog = (
        f" nel progetto <b>{html.escape(str(t['progetto']))}</b>"
        if t.get("progetto")
        else ""
    )
    corpo = (
        f"<p>Ciao {html.escape(nome)}, <b>{html.escape(da_chi)}</b> "
        "ti ha assegnato il task "
        f"<b>{html.escape(t.get('titolo') or '')}</b>{prog}{quando}.</p>"
    )
    testo = (
        f"{da_chi} ti ha assegnato il task '{t.get('titolo')}'"
        + (f" ({t['progetto']})" if t.get("progetto") else "")
        + (f", scadenza {scad:%d/%m/%Y}" if scad else "")
        + f". {app_url}"
    )
    return (
        _cornice("Nuovo task assegnato", BRAND, corpo, app_url, "Apri il gestionale"),
        testo,
    )


def html_commento(
    nome: str, titolo_entita: str, autore: str, testo_commento: str, app_url: str
) -> tuple[str, str]:
    """(html, testo) per «nuovo commento su …»."""
    corpo = (
        f"<p>Ciao {html.escape(nome)}, <b>{html.escape(autore)}</b> ha commentato "
        f"<b>{html.escape(titolo_entita)}</b>:</p>"
        f"<blockquote style='border-left:3px solid {BRAND};"
        "margin:8px 0;padding:4px 12px;"
        f"color:{MUTED}'>{html.escape(testo_commento)}</blockquote>"
    )
    testo = f"{autore} ha commentato '{titolo_entita}': {testo_commento}\n{app_url}"
    return (
        _cornice("Nuovo commento", BRAND, corpo, app_url, "Rispondi nel gestionale"),
        testo,
    )


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
    corpo = (
        f"<p>Ciao {html.escape(nome)}, è pronto il file per il <b>monthly report di "
        f"{mese_txt}</b> del progetto <b>{html.escape(etichetta)}</b> (in allegato, "
        "e scaricabile dalla Dashboard).</p>"
        "<ol style='color:" + MUTED + "'>"
        "<li>Apri il file .md e compila la sezione «Note del responsabile».</li>"
        "<li>Incolla l'intero file in ChatGPT o Claude: produrrà la bozza "
        "del report.</li>"
        "<li>Rifinisci la bozza e segna il report come completato nella "
        "pagina Progetti.</li>"
        "</ol>"
    )
    testo = (
        f"E' pronto il file per il monthly report di {mese_txt} "
        f"del progetto {etichetta} "
        "(in allegato). Compila le note del responsabile, incollalo in "
        "ChatGPT/Claude e "
        f"segna il report come completato nel gestionale. {app_url}"
    )
    return (
        _cornice(
            f"Monthly report {etichetta} — {mese_txt}",
            BRAND,
            corpo,
            app_url,
            "Apri la Dashboard",
        ),
        testo,
    )


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
