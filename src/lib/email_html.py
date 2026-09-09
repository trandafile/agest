"""Mattoni HTML per le e-mail di agest (stessa disciplina di MAIC tasks).

Markup volutamente «vecchio stile»: tabelle annidate, stili inline, niente
<style>, niente flexbox, niente immagini esterne — è ciò che sopravvive a
Gmail e Outlook. I chip sono SEMPRE testo colorato su tinta chiara con bordo:
se il client scarta gli sfondi restano leggibili. Solo libreria standard, così
lo importano anche gli script del cron senza Streamlit.

Palette: quella del template ANTECNICA 2026 (antracite #0B0F14 in testata,
azzurro #2E8FC0 per link e bottoni).
"""

from __future__ import annotations

import html as _html
from datetime import date

BRAND = "#2E8FC0"
INK = "#0B0F14"
PAGE_BG = "#F4F6F8"
CARD_BG = "#FFFFFF"
BORDER = "#E1E6EA"
TEXT = "#1F2429"
MUTED = "#6B7684"

URGENZA = {
    "scaduto": ("#C62828", "#FDECEC"),
    "in_scadenza": ("#B26A00", "#FFF4E5"),
    "bloccato": ("#D93025", "#FDEDEC"),
    "ok": ("#2E7D32", "#E8F5E9"),
    "info": ("#1F6FA8", "#E8F1FC"),
    "normale": ("#5F6368", "#F1F3F4"),
}
STATO = {
    "da_fare": ("Da fare", "#5F6368", "#F1F3F4"),
    "in_corso": ("In corso", "#1565C0", "#E8F1FC"),
    "bloccato": ("Bloccato", "#D93025", "#FDEDEC"),
    "completato": ("Completato", "#2E7D32", "#E8F5E9"),
    "annullato": ("Annullato", "#B71C1C", "#FFEBEE"),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def esc(v) -> str:
    return _html.escape(str(v if v is not None else ""))


def _tinta(colore: str, peso: float = 0.12) -> str:
    """Mescola un colore col bianco: `peso` = quanto colore resta."""
    h = (colore or "#000000").lstrip("#")
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "#F1F3F4"

    def mix(c: int) -> int:
        return round(c * peso + 255 * (1 - peso))

    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def fmt_data(d) -> str:
    return f"{d:%d/%m/%Y}" if isinstance(d, date) else "—"


# ── Atomi ────────────────────────────────────────────────────────────────────


def chip(testo: str, fg: str, bg: str | None = None, bold: bool = True) -> str:
    if not testo:
        return ""
    bg = bg or _tinta(fg, 0.12)
    return (
        f'<span style="display:inline-block;background-color:{bg};'
        f"border:1px solid {_tinta(fg, 0.40)};color:{fg};border-radius:4px;"
        f"padding:1px 7px;font-size:11px;font-weight:{'700' if bold else '400'};"
        f'font-family:{FONT};white-space:nowrap;">{esc(testo)}</span>'
    )


def chip_stato(stato: str | None) -> str:
    etichetta, fg, bg = STATO.get(stato or "", (stato or "—", "#5F6368", "#F1F3F4"))
    return chip(etichetta, fg, bg)


def chip_progetto(nome: str | None) -> str:
    return chip(nome, BRAND, _tinta(BRAND, 0.14)) if nome else ""


def chip_scadenza(scadenza, oggi: date, soglia: int = 14) -> str:
    if not isinstance(scadenza, date):
        return chip("senza scadenza", MUTED, "#F1F3F4", bold=False)
    giorni = (scadenza - oggi).days
    testo = fmt_data(scadenza)
    if giorni < 0:
        fg, bg = URGENZA["scaduto"]
        return chip(f"{testo} · in ritardo di {-giorni} g", fg, bg)
    if giorni <= soglia:
        fg, bg = URGENZA["in_scadenza"]
        quando = "oggi" if giorni == 0 else f"tra {giorni} g"
        return chip(f"{testo} · {quando}", fg, bg)
    fg, bg = URGENZA["normale"]
    return chip(testo, fg, bg, bold=False)


def bottone(url: str, etichetta: str) -> str:
    """Bianco su azzurro: sicuro perché il colore sta su un <td bgcolor>,
    attributo HTML che i client conservano."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:18px auto 4px auto;"><tr>'
        f'<td align="center" bgcolor="{BRAND}" style="background-color:{BRAND};'
        f'border-radius:6px;"><a href="{esc(url)}" target="_blank" '
        f'style="display:inline-block;padding:11px 26px;font-family:{FONT};'
        "font-size:14px;font-weight:700;color:#FFFFFF;text-decoration:none;"
        f'border-radius:6px;">{esc(etichetta)}</a></td></tr></table>'
    )


def paragrafo(testo_html: str, size: int = 14, colore: str | None = None) -> str:
    return (
        f'<p style="margin:10px 0;font-family:{FONT};font-size:{size}px;'
        f'line-height:1.55;color:{colore or TEXT};">{testo_html}</p>'
    )


def citazione(testo: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="margin:8px 0;"><tr>'
        f'<td style="border-left:4px solid {BRAND};padding:8px 12px;'
        f"font-family:{FONT};font-size:14px;line-height:1.5;color:{TEXT};"
        f'background-color:{PAGE_BG};">{esc(testo)}</td></tr></table>'
    )


def riquadri(tiles: list[tuple[str, object, str]]) -> str:
    """tiles = [(etichetta, valore, chiave_urgenza)] su una riga."""
    if not tiles:
        return ""
    larg = f"{100 // len(tiles)}%"
    celle = []
    for etichetta, valore, chiave in tiles:
        fg, bg = URGENZA.get(chiave, URGENZA["normale"])
        celle.append(
            f'<td width="{larg}" align="center" style="padding:4px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0"><tr><td align="center" bgcolor="{bg}" '
            f'style="background-color:{bg};border:1px solid {_tinta(fg, 0.30)};'
            f'border-radius:6px;padding:10px 4px;font-family:{FONT};">'
            f'<div style="font-size:22px;font-weight:800;color:{fg};line-height:1.1;">'
            f"{esc(valore)}</div>"
            f'<div style="font-size:11px;color:{fg};text-transform:uppercase;'
            'letter-spacing:0.04em;font-weight:700;margin-top:2px;">'
            f"{esc(etichetta)}</div></td></tr></table></td>"
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="margin:6px 0 2px 0;"><tr>{"".join(celle)}</tr></table>'
    )


def riga_task(t: dict, oggi: date, soglia: int = 14) -> str:
    """Una riga: chip progetto · titolo · stato — scadenza a destra."""
    dettaglio = ""
    if t.get("dettaglio"):
        dettaglio = (
            f'<div style="font-size:11px;color:{MUTED};margin-top:2px;">'
            f"{esc(t['dettaglio'])}</div>"
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="border-bottom:1px solid #EEF1F4;"><tr>'
        f'<td style="padding:9px 10px;font-family:{FONT};vertical-align:top;">'
        f"{chip_progetto(t.get('progetto'))} "
        f'<span style="font-size:14px;font-weight:700;color:{TEXT};">'
        f"{esc(t.get('titolo'))}</span> {chip_stato(t.get('stato'))}"
        f"{dettaglio}</td>"
        '<td align="right" style="padding:9px 10px;white-space:nowrap;'
        f'vertical-align:top;">{chip_scadenza(t.get("scadenza"), oggi, soglia)}'
        "</td></tr></table>"
    )


def sezione(
    titolo: str, chiave: str, righe: list[dict], oggi: date, soglia: int = 14
) -> str:
    """Fascia colorata con titolo e conteggio, poi le righe. Vuota = niente."""
    if not righe:
        return ""
    fg, bg = URGENZA.get(chiave, URGENZA["normale"])
    corpo = "".join(riga_task(r, oggi, soglia) for r in righe)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="margin:16px 0 0 0;">'
        f'<tr><td bgcolor="{bg}" style="background-color:{bg};'
        f"border-left:4px solid {fg};border-radius:5px;padding:7px 10px;"
        f'font-family:{FONT};"><span style="font-size:13px;font-weight:800;'
        f'color:{fg};letter-spacing:0.02em;">{esc(titolo)}</span>'
        f'<span style="font-size:12px;font-weight:700;color:{fg};"> · {len(righe)}'
        "</span></td></tr>"
        f'<tr><td style="padding:0;">{corpo}</td></tr></table>'
    )


def elenco_passi(passi: list[str]) -> str:
    voci = "".join(
        f'<li style="margin:4px 0;font-family:{FONT};font-size:14px;'
        f'line-height:1.5;color:{TEXT};">{p}</li>'
        for p in passi
    )
    return f'<ol style="margin:8px 0 8px 20px;padding:0;">{voci}</ol>'


# ── Cornice ───────────────────────────────────────────────────────────────────


def cornice(
    *,
    anteprima: str,
    titolo: str,
    corpo_html: str,
    app_url: str | None = None,
    etichetta_bottone: str = "Apri il gestionale",
) -> str:
    """Cornice ANTECNICA: testata antracite, card bianca, piè di pagina.
    `anteprima` è la riga mostrata dal client nell'elenco dei messaggi."""
    cta = bottone(app_url, etichetta_bottone) if app_url else ""
    anno = date.today().year
    testata = (
        f'<tr><td bgcolor="{INK}" style="background-color:{INK};'
        f'padding:18px 22px;font-family:{FONT};">'
        '<div style="font-size:19px;font-weight:800;color:#FFFFFF;'
        'letter-spacing:0.14em;">ANTECNICA</div>'
        f'<div style="font-size:12px;color:{BRAND};margin-top:1px;'
        'letter-spacing:0.04em;">Gestionale</div></td></tr>'
    )
    intestazione = (
        f'<tr><td style="padding:20px 22px 6px 22px;font-family:{FONT};">'
        f'<div style="font-size:18px;font-weight:800;color:{TEXT};">'
        f"{esc(titolo)}</div></td></tr>"
    )
    pie = (
        '<tr><td bgcolor="#FAFBFC" style="background-color:#FAFBFC;'
        f'border-top:1px solid {BORDER};padding:14px 22px;font-family:{FONT};">'
        f'<div style="font-size:11px;color:{MUTED};line-height:1.5;">'
        "ANTECNICA S.r.l. — spin-off dell'Università della Calabria<br>"
        f"Messaggio automatico del gestionale · {anno}</div></td></tr>"
    )
    return (
        '<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(titolo)}</title></head>"
        f'<body style="margin:0;padding:0;background-color:{PAGE_BG};">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        f"{esc(anteprima)}</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" bgcolor="{PAGE_BG}" style="background-color:{PAGE_BG};'
        'padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'border="0" bgcolor="{CARD_BG}" style="width:600px;max-width:100%;'
        f"background-color:{CARD_BG};border:1px solid {BORDER};"
        'border-radius:10px;overflow:hidden;">'
        f"{testata}{intestazione}"
        f'<tr><td style="padding:0 22px 18px 22px;">{corpo_html}{cta}</td></tr>'
        f"{pie}</table></td></tr></table></body></html>"
    )
