"""`LLM_VUELTAS_LIMITE` en la configuración (25 nov 2026, antes era la constante VUELTAS_MAX): el 0 documentado y los valores de defaults.env, sin credenciales
de Databricks versionadas."""
import pytest
from dotenv import dotenv_values

from backend.config import RAIZ, es_secreto, settings
from backend.core.errors import LLMUnavailableError
from backend.engine import juez
from backend.engine.juez import juzgar_par
from backend.models import Par
from l3_ayudas import cfg
from test_limite_tasa import ConAvance, Falla429, seccion


@pytest.fixture(autouse=True)
def sin_dormir(monkeypatch):
    monkeypatch.setattr(juez, "_dormir", lambda segundos, obs: None)


def test_con_cero_vueltas_el_par_aborta_al_primer_agotamiento_aunque_los_demas_avancen():
    c = cfg(LLM_INTENTOS_LIMITE=3, LLM_ESPERA_LIMITE_S=20, LLM_VUELTAS_LIMITE=0)
    cliente = Falla429(fallos=10**6)
    par = Par(id="P1", articulo_id="A", seccion_id="M", origen={"v1"}, score_v1=0.5)
    with pytest.raises(LLMUnavailableError):
        juzgar_par(par, seccion("A"), seccion("M"), {}, cliente, c, ConAvance(avanza=True))
    assert cliente.llamadas == c.LLM_INTENTOS_LIMITE


def test_defaults_env_trae_las_vueltas_y_los_endpoints_de_databricks_pero_ninguna_credencial():
    d = dotenv_values(RAIZ / "config" / "defaults.env")
    assert int(d["LLM_VUELTAS_LIMITE"]) == 5 and d["DATABRICKS_LLM_ENDPOINT"] and d["DATABRICKS_EMB_ENDPOINT"]
    versionadas = [k for k, v in d.items() if k.startswith("DATABRICKS_") and es_secreto(k) and v]
    assert versionadas == [] and not d.get("DATABRICKS_HOST")                   # el host y las credenciales los pone la App o config/.env
    assert settings.LLM_VUELTAS_LIMITE >= 0
