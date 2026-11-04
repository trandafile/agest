"""Livello «gestore task» (src/auth/permessi.py)."""

from types import SimpleNamespace
from uuid import uuid4

from src.auth.permessi import (
    descrizione_livello,
    is_gestore_task,
    puo_eliminare_task,
    puo_gestire_deliverable,
    puo_importare_task,
    puo_modificare_task,
)
from src.domain.models import RuoloSistema


def _p(ruolo=RuoloSistema.dipendente, gestore=False):
    return SimpleNamespace(id=uuid4(), ruolo_sistema=ruolo, gestore_task=gestore)


def test_dipendente_modifica_solo_i_propri():
    me, altro = _p(), _p()
    mio = SimpleNamespace(owner_id=me.id, supervisor_id=None)
    suo = SimpleNamespace(owner_id=altro.id, supervisor_id=None)
    assert puo_modificare_task(mio, me) and not puo_modificare_task(suo, me)
    assert not puo_eliminare_task(me) and not puo_importare_task(me)
    assert not puo_gestire_deliverable(me)
    assert descrizione_livello(me) == "dipendente"


def test_gestore_task_gestisce_tutto_ma_non_e_admin():
    g, altro = _p(gestore=True), _p()
    suo = SimpleNamespace(owner_id=altro.id, supervisor_id=None)
    assert is_gestore_task(g) and puo_modificare_task(suo, g)
    assert puo_eliminare_task(g) and puo_importare_task(g) and puo_gestire_deliverable(g)
    assert descrizione_livello(g) == "dipendente · gestore task"


def test_admin_e_pm():
    a, pm = _p(RuoloSistema.admin), _p(RuoloSistema.pm)
    assert is_gestore_task(a) and descrizione_livello(a) == "amministratore"
    assert puo_gestire_deliverable(pm) and not puo_eliminare_task(pm)


def test_persona_senza_campo_gestore_e_dipendente():
    # modello vecchio (prima della 0019): niente attributo gestore_task
    p = SimpleNamespace(id=uuid4(), ruolo_sistema=RuoloSistema.dipendente)
    assert not is_gestore_task(p)
