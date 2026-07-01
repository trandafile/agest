"""Autorizzazione per ruolo — logica pura (testabile senza Streamlit).

Sotto Opzione A l'enforcement effettivo e' qui, in Python: ogni pagina/azione
passa da una guardia di ruolo. La RLS a DB e' rete di sicurezza.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.models import RuoloSistema


class AccessDenied(Exception):
    """Sollevata quando l'utente non ha il ruolo richiesto."""


def can_access(
    user_role: RuoloSistema, required: Iterable[RuoloSistema] | RuoloSistema
) -> bool:
    """True se `user_role` puo' accedere a una risorsa che richiede `required`.

    Regola: l'admin accede a tutto; gli altri ruoli devono comparire tra quelli
    richiesti. Nessuna gerarchia implicita tra `pm` e `dipendente`.
    """
    if user_role == RuoloSistema.admin:
        return True
    if isinstance(required, RuoloSistema):
        required = (required,)
    return user_role in set(required)


def is_allowed_email(email: str | None, domain: str) -> bool:
    """True se `email` appartiene al dominio aziendale consentito."""
    if not email:
        return False
    return email.strip().lower().endswith("@" + domain.strip().lower())
