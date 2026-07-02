"""Parser degli estratti conto bancari (XML CAMT.053, CSV, PDF best-effort).

Ritorna righe normalizzate {data, importo, segno, descrizione, controparte}
da rivedere in anteprima prima dell'import. Il PDF e' best-effort: estrae le
righe che contengono una data e un importo; la correzione avviene in UI.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

from src.domain.finanza import parse_data, parse_importo


def parse_camt053(contenuto: bytes) -> list[dict]:
    """XML CAMT.053 (standard estratto conto SEPA/CBI)."""
    root = ET.fromstring(contenuto)
    ns = {"c": root.tag.split("}")[0].strip("{")}
    out: list[dict] = []
    for ntry in root.iterfind(".//c:Ntry", ns):
        amt = ntry.find("c:Amt", ns)
        cdt = ntry.findtext("c:CdtDbtInd", default="", namespaces=ns)
        data = ntry.findtext(
            "c:BookgDt/c:Dt", default="", namespaces=ns
        ) or ntry.findtext("c:ValDt/c:Dt", default="", namespaces=ns)
        descr = ntry.findtext(
            "c:NtryDtls/c:TxDtls/c:RmtInf/c:Ustrd", default="", namespaces=ns
        ) or ntry.findtext("c:AddtlNtryInf", default="", namespaces=ns)
        controparte = ntry.findtext(
            "c:NtryDtls/c:TxDtls/c:RltdPties/c:Cdtr/c:Nm",
            default="",
            namespaces=ns,
        ) or ntry.findtext(
            "c:NtryDtls/c:TxDtls/c:RltdPties/c:Dbtr/c:Nm",
            default="",
            namespaces=ns,
        )
        d = parse_data(data)
        imp = parse_importo(amt.text if amt is not None else None)
        if d is None or imp is None:
            continue
        out.append(
            {
                "data": d,
                "importo": abs(imp),
                "segno": "entrata" if cdt == "CRDT" else "uscita",
                "descrizione": (descr or "").strip() or None,
                "controparte": (controparte or "").strip() or None,
            }
        )
    return out


_RIGA_PDF = re.compile(
    r"(?P<data>\d{1,2}[/.]\d{1,2}[/.]\d{2,4})\s+(?P<resto>.+?)\s+"
    r"(?P<importo>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$"
)


def parse_pdf(contenuto: bytes) -> list[dict]:
    """PDF best-effort: righe con data all'inizio e importo alla fine."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("pypdf non installato") from exc

    testo = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(contenuto)).pages
    )
    out: list[dict] = []
    for riga in testo.splitlines():
        m = _RIGA_PDF.search(riga.strip())
        if not m:
            continue
        d = parse_data(m.group("data"))
        imp = parse_importo(m.group("importo"))
        if d is None or imp is None:
            continue
        out.append(
            {
                "data": d,
                "importo": abs(imp),
                "segno": "entrata" if imp >= 0 else "uscita",
                "descrizione": m.group("resto").strip() or None,
                "controparte": None,
            }
        )
    return out


def parse_csv_estratto(df_rows: list[dict], mappa: dict[str, str]) -> list[dict]:
    """CSV generico con mappatura colonne (riusa la normalizzazione standard)."""
    from src.domain.finanza import normalizza_movimento

    out = []
    for r in df_rows:
        n = normalizza_movimento(r, mappa)
        if n:
            out.append(
                {
                    k: n[k]
                    for k in ("data", "importo", "segno", "descrizione", "controparte")
                }
            )
    return out


def totale(righe: list[dict]) -> Decimal:
    tot = Decimal("0")
    for r in righe:
        tot += r["importo"] if r["segno"] == "entrata" else -r["importo"]
    return tot
