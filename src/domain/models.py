"""Modelli di dominio (pydantic v2) — Fase 1.

Attraversano il confine DB/UI: la validazione vive qui, non nei widget.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuoloSistema(enum.StrEnum):
    """Ruoli di sistema (coerenti con l'enum SQL `ruolo_sistema`)."""

    admin = "admin"
    pm = "pm"
    dipendente = "dipendente"


class TipoContratto(enum.StrEnum):
    tempo_determinato = "tempo_determinato"
    tempo_indeterminato = "tempo_indeterminato"
    socio = "socio"


TIPO_CONTRATTO_LABEL = {
    "tempo_determinato": "Tempo determinato",
    "tempo_indeterminato": "Tempo indeterminato",
    "socio": "Socio",
}


class Persona(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: UUID | None = None
    nome: str
    cognome: str
    matricola: str | None = None
    email: str
    ruolo_sistema: RuoloSistema = RuoloSistema.dipendente
    attivo: bool = True
    codice_fiscale: str | None = None
    monte_ore_annuo: int | None = 1720
    tipo_contratto: TipoContratto | None = None
    contratto_data_inizio: date | None = None
    contratto_data_fine: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def contratto_descr(self) -> str:
        """Descrizione sintetica del contratto per tabelle/UI."""
        if self.tipo_contratto is None:
            return "—"
        base = TIPO_CONTRATTO_LABEL[self.tipo_contratto.value]
        if self.contratto_data_inizio and self.contratto_data_fine:
            return (
                f"{base} ({self.contratto_data_inizio:%d/%m/%Y}"
                f"→{self.contratto_data_fine:%d/%m/%Y})"
            )
        if self.contratto_data_inizio:
            return f"{base} (dal {self.contratto_data_inizio:%d/%m/%Y})"
        return base

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.cognome}".strip()


class TipoIniziativa(enum.StrEnum):
    proposta = "proposta"
    progetto = "progetto"


class StatoProposta(enum.StrEnum):
    bozza = "bozza"
    inviata = "inviata"
    approvata = "approvata"
    rifiutata = "rifiutata"


class StatoProgetto(enum.StrEnum):
    attivo = "attivo"
    chiuso = "chiuso"


class TipoAttivita(enum.StrEnum):
    RI = "RI"  # Ricerca Industriale
    SS = "SS"  # Sviluppo Sperimentale
    altro = "altro"


class Iniziativa(BaseModel):
    """Backbone Proposte/Progetti (stessa entità in stati diversi).

    Nella UI è etichettata «Progetto» (o «Proposta» quando tipo='proposta').
    Campi allineati a MAIC tasks `projects`: acronimo=acronym, codice=identifier,
    controparte=funding_agency, titolo=name.
    """

    id: UUID | None = None
    tipo: TipoIniziativa
    stato: str
    codice: str | None = None  # = Mtasks.identifier
    acronimo: str | None = None  # = Mtasks.acronym
    titolo: str  # = Mtasks.name
    controparte: str | None = None  # = Mtasks.funding_agency (ente/cliente)
    responsabile_id: UUID | None = None
    tipo_attivita_default: str | None = None
    data_inizio: date | None = None
    data_fine: date | None = None
    ore_totali: Decimal | None = None
    budget_totale: Decimal | None = None
    probabilita_successo: Decimal | None = Field(default=None, ge=0, le=1)
    note: str | None = None
    cup: str | None = None
    tipo_progetto_desc: str | None = None
    costo_complessivo: Decimal | None = None
    finanziamento_complessivo: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def etichetta(self) -> str:
        """Etichetta breve per selettori/tabelle: «ACRONIMO · Titolo»."""
        prefisso = self.acronimo or self.codice
        return f"{prefisso} · {self.titolo}" if prefisso else self.titolo


class Assegnazione(BaseModel):
    id: UUID | None = None
    iniziativa_id: UUID
    persona_id: UUID
    work_package_id: UUID | None = None
    tipo_attivita: TipoAttivita = TipoAttivita.altro
    ore_pianificate: Decimal | None = Field(default=None, ge=0)
    tetto_ore_mese: Decimal | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TimesheetMese(BaseModel):
    id: UUID | None = None
    persona_id: UUID
    anno: int
    mese: int = Field(ge=1, le=12)
    stato: str = "bozza"
    confermato_il: datetime | None = None


class TimesheetOra(BaseModel):
    id: UUID | None = None
    persona_id: UUID
    assegnazione_id: UUID
    data: date
    ore: int = Field(ge=0, le=8)
    forzato: bool = False


class Presenza(BaseModel):
    id: UUID | None = None
    persona_id: UUID
    data: date
    ora_ingresso: time | None = None
    ora_uscita: time | None = None
    ore_totali: Decimal | None = None
    tipo: str = "ufficio"
    note: str | None = None


class Assenza(BaseModel):
    id: UUID | None = None
    persona_id: UUID
    tipo: str
    data_inizio: date
    data_fine: date
    ore_o_giorni: Decimal | None = None
    stato: str = "richiesta"
    approvato_da: UUID | None = None
    note: str | None = None


STATI_TASK = ("da_fare", "in_corso", "bloccato", "completato", "annullato")
PRIORITA_TASK = ("urgente", "alta", "media", "bassa", "nessuna")

STATO_TASK_BADGE = {
    "da_fare": "⚪ Da fare",
    "in_corso": "🔵 In corso",
    "bloccato": "🔴 Bloccato",
    "completato": "🟢 Completato",
    "annullato": "⚫ Annullato",
}
PRIORITA_BADGE = {
    "urgente": "🔴 Urgente",
    "alta": "🟠 Alta",
    "media": "🔵 Media",
    "bassa": "🟢 Bassa",
    "nessuna": "⚪ —",
}


class Deliverable(BaseModel):
    """Livello tra progetto e task (come MAIC tasks)."""

    id: UUID | None = None
    iniziativa_id: UUID
    titolo: str
    tipo: str | None = None
    stato: str = "da_fare"
    scadenza: date | None = None
    owner_id: UUID | None = None
    supervisor_id: UUID | None = None
    descrizione: str | None = None
    archiviato: bool = False
    created_at: datetime | None = None

    @property
    def attivo(self) -> bool:
        return not self.archiviato and self.stato not in ("completato", "annullato")


class Task(BaseModel):
    """Task stile MAIC tasks; i subtask hanno `parent_task_id` valorizzato."""

    id: UUID | None = None
    iniziativa_id: UUID | None = None
    deliverable_id: UUID | None = None
    parent_task_id: UUID | None = None
    titolo: str
    descrizione: str | None = None
    owner_id: UUID | None = None
    supervisor_id: UUID | None = None
    stato: str = "da_fare"
    priorita: str = "nessuna"
    ore_stimate: Decimal | None = None
    scadenza: date | None = None
    completato_il: date | None = None
    archiviato: bool = False
    created_at: datetime | None = None

    @property
    def attivo(self) -> bool:
        return not self.archiviato and self.stato not in ("completato", "annullato")


CATEGORIE_BUDGET = (
    "personale",
    "materiali",
    "missioni",
    "attrezzature",
    "subcontratti",
    "overhead",
)


class WorkPackage(BaseModel):
    id: UUID | None = None
    iniziativa_id: UUID
    codice: str | None = None
    titolo: str
    budget_ore: Decimal | None = None
    budget_costo: Decimal | None = None


class VoceBudget(BaseModel):
    id: UUID | None = None
    iniziativa_id: UUID
    work_package_id: UUID | None = None
    categoria: str
    descrizione: str | None = None
    importo: Decimal = Field(ge=0)


class Milestone(BaseModel):
    id: UUID | None = None
    iniziativa_id: UUID
    work_package_id: UUID | None = None
    titolo: str
    data_prevista: date | None = None
    stato: str = "prevista"
    importo_incasso: Decimal | None = None
    genera_pagamento: bool = False


class Festivita(BaseModel):
    id: UUID | None = None
    data: date
    descrizione: str


class TariffaOraria(BaseModel):
    id: UUID | None = None
    persona_id: UUID | None = None
    valido_da: date
    valido_al: date | None = None
    importo_orario: Decimal = Field(ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("valido_al")
    @classmethod
    def _periodo_coerente(cls, v: date | None, info) -> date | None:
        da = info.data.get("valido_da")
        if v is not None and da is not None and v < da:
            raise ValueError("valido_al non puo' precedere valido_da")
        return v

    def copre(self, quando: date) -> bool:
        """True se la tariffa e' vigente alla data `quando`."""
        if quando < self.valido_da:
            return False
        return self.valido_al is None or quando <= self.valido_al
