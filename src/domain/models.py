"""Modelli di dominio (pydantic v2) — Fase 1.

Attraversano il confine DB/UI: la validazione vive qui, non nei widget.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
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
