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


class Persona(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: UUID | None = None
    nome: str
    cognome: str
    matricola: str | None = None
    email: str
    ruolo_sistema: RuoloSistema = RuoloSistema.dipendente
    attivo: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

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
    id: UUID | None = None
    tipo: TipoIniziativa
    stato: str
    codice: str | None = None
    titolo: str
    controparte: str | None = None
    responsabile_id: UUID | None = None
    tipo_attivita_default: str | None = None
    data_inizio: date | None = None
    data_fine: date | None = None
    ore_totali: Decimal | None = None
    budget_totale: Decimal | None = None
    probabilita_successo: Decimal | None = Field(default=None, ge=0, le=1)
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
