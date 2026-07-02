"""Finanza v2: preset Google Sheet, proiezione di cassa, parser CAMT."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.finanza import (
    PRESET_SHEET_ANTECNICA,
    normalizza_movimento,
    parse_data,
    proiezione_cassa,
    prossimi_mesi,
)
from src.lib.estratto_conto import parse_camt053, totale

D = Decimal


def test_preset_sheet_antecnica():
    riga = {
        "Data": "05/01/2026",
        "Descrizione Transazione": "BONIFICO A FRANCESCO GRECO compenso",
        "N. Fattura": "",
        "Tipo Transazione": "Uscita",
        "Importo (€)": "-3005,5",
        "Categoria": "Personale",
        "Progetto": "",
        "Persona/Contatto": "Greco",
        "Note": "",
    }
    out = normalizza_movimento(riga, PRESET_SHEET_ANTECNICA)
    assert out["data"] == date(2026, 1, 5)
    assert out["importo"] == D("3005.5") and out["segno"] == "uscita"
    assert out["categoria"] == "Personale"
    assert out["persona_contatto"] == "Greco"
    assert out["progetto_label"] is None


def test_preset_sheet_entrata_con_progetto():
    riga = {
        "Data": "16/02/2026",
        "Descrizione Transazione": "BONIFICO DA POLIMI CUP D43C22003080001",
        "Tipo Transazione": "Entrata",
        "Importo (€)": "68.459,08",
        "Categoria": "Progetto",
        "Progetto": "RUSC",
        "Persona/Contatto": "",
        "Note": "",
        "N. Fattura": "",
    }
    out = normalizza_movimento(riga, PRESET_SHEET_ANTECNICA)
    assert out["segno"] == "entrata" and out["importo"] == D("68459.08")
    assert out["progetto_label"] == "RUSC"


def test_parse_data_rifiuta_anni_refuso():
    assert parse_data("25/5/0206") is None  # refuso reale presente nel foglio
    assert parse_data("31/12/2026") == date(2026, 12, 31)


def test_prossimi_mesi_cavallo_anno():
    assert prossimi_mesi(date(2026, 11, 15), 4) == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]


def test_proiezione_cassa():
    mesi = [(2026, 7), (2026, 8), (2026, 9)]
    rows = proiezione_cassa(
        saldo_iniziale=D("10000"),
        mesi=mesi,
        entrate_programmate={(2026, 8): D("50000")},
        uscite_programmate={(2026, 9): D("20000")},
        uscita_ricorrente_stimata=D("15000"),
    )
    assert [r["saldo"] for r in rows] == [D("-5000"), D("30000"), D("-5000")]
    assert rows[1]["entrate"] == D("50000")
    assert rows[2]["uscite"] == D("35000")  # 20000 + ricorrente


CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
 <BkToCstmrStmt><Stmt>
  <Ntry>
   <Amt Ccy="EUR">1500.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
   <BookgDt><Dt>2026-06-10</Dt></BookgDt>
   <NtryDtls><TxDtls>
     <RltdPties><Dbtr><Nm>CLIENTE SRL</Nm></Dbtr></RltdPties>
     <RmtInf><Ustrd>Saldo fattura 12</Ustrd></RmtInf>
   </TxDtls></NtryDtls>
  </Ntry>
  <Ntry>
   <Amt Ccy="EUR">250.50</Amt><CdtDbtInd>DBIT</CdtDbtInd>
   <BookgDt><Dt>2026-06-12</Dt></BookgDt>
   <AddtlNtryInf>PAGAMENTO POS</AddtlNtryInf>
  </Ntry>
 </Stmt></BkToCstmrStmt>
</Document>"""


def test_parse_camt053():
    righe = parse_camt053(CAMT)
    assert len(righe) == 2
    assert righe[0]["segno"] == "entrata"
    assert righe[0]["importo"] == D("1500.00")
    assert righe[0]["controparte"] == "CLIENTE SRL"
    assert righe[1]["segno"] == "uscita"
    assert righe[1]["descrizione"] == "PAGAMENTO POS"
    assert totale(righe) == D("1249.50")
