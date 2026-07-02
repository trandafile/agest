"""Import/normalizzazione dati finanziari + export rendicontazione (spec §8).

Il Google Sheet finanziario arriva come CSV/XLSX con colonne libere: qui si
normalizzano importi/date in formato italiano e si mappano le colonne sui
campi di `movimento_bancario` / `documento_fiscale`. Pure Python, testabile.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.domain.models import TariffaOraria
from src.domain.tariffe import tariffa_vigente

CAMPI_MOVIMENTO = (
    "data",
    "importo",
    "segno",
    "descrizione",
    "controparte",
    "categoria",
    "n_fattura",
    "progetto",
    "persona_contatto",
    "note",
)

# Tracciato del Google Sheet finanziario ANTECNICA (mappatura automatica)
PRESET_SHEET_ANTECNICA = {
    "data": "Data",
    "descrizione": "Descrizione Transazione",
    "n_fattura": "N. Fattura",
    "segno": "Tipo Transazione",
    "importo": "Importo (€)",
    "categoria": "Categoria",
    "progetto": "Progetto",
    "persona_contatto": "Persona/Contatto",
    "note": "Note",
}
CAMPI_DOCUMENTO = (
    "tipo",
    "numero",
    "data",
    "importo",
    "controparte",
    "stato_incasso_pagamento",
    "data_scadenza",
)


def parse_importo(val: object) -> Decimal | None:
    """Importo da stringa italiana ('1.234,56', '€ 1.234,56', '-500') o numero.

    Ritorna il valore assoluto NON viene applicato: il segno resta al chiamante.
    None se non interpretabile.
    """
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    s = str(val).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    # '1.234,56' -> '1234.56' ; '1234.56' resta ; '1,234.56' (en) -> '1234.56'
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_data(val: object) -> date | None:
    """Data da 'gg/mm/aaaa', 'aaaa-mm-gg', datetime o date."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        # anni palesemente errati (es. refuso '0206') -> riga da segnalare
        if not 1990 <= d.year <= 2100:
            return None
        return d
    return None


def normalizza_movimento(riga: dict, mappa: dict[str, str]) -> dict | None:
    """Riga grezza -> campi movimento_bancario secondo `mappa` {campo: colonna}.

    Il segno: se la mappa ha 'segno' esplicito usa quello ('entrata'/'uscita',
    accetta anche 'E'/'U', '+'/'-'); altrimenti lo deduce dal segno dell'importo.
    Ritorna None se mancano data o importo (riga da scartare, conteggiata).
    """
    d = parse_data(riga.get(mappa.get("data", "")))
    imp = parse_importo(riga.get(mappa.get("importo", "")))
    if d is None or imp is None:
        return None
    segno = None
    if "segno" in mappa and mappa["segno"]:
        raw = str(riga.get(mappa["segno"], "")).strip().lower()
        if raw in ("entrata", "e", "+", "in", "avere"):
            segno = "entrata"
        elif raw in ("uscita", "u", "-", "out", "dare"):
            segno = "uscita"
    if segno is None:
        segno = "entrata" if imp >= 0 else "uscita"
    return {
        "data": d,
        "importo": abs(imp),
        "segno": segno,
        "descrizione": _txt(riga, mappa, "descrizione"),
        "controparte": _txt(riga, mappa, "controparte"),
        "categoria": _txt(riga, mappa, "categoria"),
        "n_fattura": _txt(riga, mappa, "n_fattura"),
        "persona_contatto": _txt(riga, mappa, "persona_contatto"),
        "note": _txt(riga, mappa, "note"),
        "progetto_label": _txt(riga, mappa, "progetto"),
    }


def normalizza_documento(riga: dict, mappa: dict[str, str]) -> dict | None:
    """Riga grezza -> campi documento_fiscale. None se mancano data/importo."""
    d = parse_data(riga.get(mappa.get("data", "")))
    imp = parse_importo(riga.get(mappa.get("importo", "")))
    if d is None or imp is None:
        return None
    tipo_raw = str(riga.get(mappa.get("tipo", ""), "")).strip().lower()
    tipo = (
        "attiva"
        if tipo_raw in ("attiva", "a", "vendita", "emessa")
        else (
            "passiva"
            if tipo_raw in ("passiva", "p", "acquisto", "ricevuta")
            else ("attiva" if imp >= 0 else "passiva")
        )
    )
    stato_raw = (
        str(riga.get(mappa.get("stato_incasso_pagamento", ""), "")).strip().lower()
    )
    stato = (
        "saldato"
        if stato_raw in ("saldato", "pagato", "incassato", "si", "sì")
        else "parziale" if stato_raw == "parziale" else "aperto"
    )
    return {
        "tipo": tipo,
        "numero": _txt(riga, mappa, "numero"),
        "data": d,
        "importo": abs(imp),
        "controparte": _txt(riga, mappa, "controparte"),
        "stato_incasso_pagamento": stato,
        "data_scadenza": parse_data(riga.get(mappa.get("data_scadenza", ""))),
    }


def _txt(riga: dict, mappa: dict[str, str], campo: str) -> str | None:
    col = mappa.get(campo)
    if not col:
        return None
    v = riga.get(col)
    s = str(v).strip() if v is not None else ""
    return s or None


def prossimi_mesi(da: date, n: int) -> list[tuple[int, int]]:
    """I prossimi `n` (anno, mese) a partire dal mese di `da` (incluso)."""
    out = []
    a, m = da.year, da.month
    for _ in range(n):
        out.append((a, m))
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


def proiezione_cassa(
    saldo_iniziale: Decimal,
    mesi: list[tuple[int, int]],
    entrate_programmate: dict[tuple[int, int], Decimal],
    uscite_programmate: dict[tuple[int, int], Decimal],
    uscita_ricorrente_stimata: Decimal = Decimal("0"),
) -> list[dict]:
    """Proiezione del flusso di cassa mese per mese.

    Per ogni mese: saldo = saldo precedente + entrate programmate (documenti
    attivi aperti per scadenza, milestone previste) − uscite programmate
    (documenti passivi aperti) − stima delle uscite ricorrenti (media storica).
    """
    out = []
    saldo = saldo_iniziale
    for chiave in mesi:
        entrate = entrate_programmate.get(chiave, Decimal("0"))
        uscite = (
            uscite_programmate.get(chiave, Decimal("0")) + uscita_ricorrente_stimata
        )
        saldo = saldo + entrate - uscite
        out.append(
            {
                "anno": chiave[0],
                "mese": chiave[1],
                "entrate": entrate,
                "uscite": uscite,
                "saldo": saldo,
            }
        )
    return out


def tabella_rendicontazione(
    ore_registrate: list[dict],
    tariffe_by_persona: dict[str, list[TariffaOraria]],
) -> list[dict]:
    """Tabella ore x tariffa vigente per l'export dei rendiconti (spec §8).

    `ore_registrate`: [{persona_id, persona, iniziativa, tipo_attivita,
                        data (date), ore (int)}].
    Aggiunge tariffa applicata e costo; le righe senza tariffa hanno costo None.
    """
    out = []
    for r in ore_registrate:
        t = tariffa_vigente(tariffe_by_persona.get(str(r["persona_id"]), []), r["data"])
        tariffa = t.importo_orario if t else None
        out.append(
            {
                "Persona": r["persona"],
                "Iniziativa": r["iniziativa"],
                "Tipo attività": r["tipo_attivita"],
                "Data": r["data"],
                "Ore": r["ore"],
                "Tariffa €/h": float(tariffa) if tariffa is not None else None,
                "Costo €": (
                    float(Decimal(r["ore"]) * tariffa) if tariffa is not None else None
                ),
            }
        )
    return out
