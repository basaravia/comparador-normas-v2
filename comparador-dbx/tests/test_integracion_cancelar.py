"""Cancelar una comparación con el modelo REAL del stage (P-26). Marca `integracion`: gasta tokens o tiempo de GPU/CPU.

Lo que no puede probar un doble: que con llamadas reales en vuelo (que tardan segundos o minutos) «Cancelar» responde enseguida, no publica
resultados y no lanza más pares. La llamada que ya estaba en curso no se puede abortar: sigue en el proveedor hasta terminar (V-17)."""
import time

import pytest

from backend.core import sesiones
from backend.engine import servicio
from backend.engine.juez import llamadas_vivas

pytestmark = pytest.mark.integracion

TOPE_CANCELAR_S = 10          # con llamadas en vuelo se midió 1,6–1,9 s; el margen cubre una máquina cargada
ESPERA_HUERFANAS_S = 240      # máximo que se espera a que terminen las llamadas que quedaron huérfanas tras cancelar
ESPERA_EN_VUELO_S = 180       # tiempo máximo hasta que haya al menos un par en análisis (recuperación + primera llamada)


def _hojas(nodos):
    for n in nodos:
        if n.hoja:
            yield n
        yield from _hojas(n.hijos)


def test_cancelar_con_llamadas_reales_en_vuelo_responde_en_segundos_y_no_publica_nada(cliente):
    s = sesiones.crear()
    try:
        servicio.cargar_ejemplo(s)
        arts = [h.id for h in _hojas(servicio.arbol(s, "normativa")[0].nodos)][:2]
        secs = [h.id for h in _hojas(servicio.arbol(s, "manual_control")[0].nodos) if h.seleccionada][:4]
        job = servicio.comparar(s, arts, secs, cliente)
        comp = s.comparaciones[job.comparacion_id]

        t0 = time.time()
        while not job.pares_en_curso and job.estado in ("en_cola", "en_curso") and time.time() - t0 < ESPERA_EN_VUELO_S:
            time.sleep(0.5)
        assert job.pares_en_curso, f"no hubo ningún par en análisis en {ESPERA_EN_VUELO_S} s (estado {job.estado}, etapa {job.etapa!r})"
        en_vuelo = len(job.pares_en_curso)

        antes = time.time()
        servicio.cancelar(s, job.job_id)
        while job.estado != "cancelado" and time.time() - antes < TOPE_CANCELAR_S + 5:
            time.sleep(0.1)
        tardo = time.time() - antes

        assert job.estado == "cancelado", f"seguía {job.estado} a los {tardo:.1f} s"
        assert tardo < TOPE_CANCELAR_S, f"canceló en {tardo:.1f} s con {en_vuelo} par(es) en vuelo"
        assert comp.out.estado == "cancelado" and comp.entrada is None                  # no queda papel de trabajo a medias
        assert job.pares_en_curso == [] and not job.espera_limite.activa
        hechos, resueltos = job.pares_hechos, list(job.ultimos_veredictos)
        time.sleep(3)                                                                    # lo que el proveedor devuelva tarde no cambia el resultado
        assert job.estado == "cancelado" and job.pares_hechos == hechos and list(job.ultimos_veredictos) == resueltos
        print(f"\ncancelado en {tardo:.2f} s con {en_vuelo} par(es) en vuelo; pares resueltos antes de cancelar: {hechos}")
    finally:
        sesiones.reiniciar(s.id)
        # Las llamadas huérfanas siguen en el proveedor hasta terminar (V-17) y el tope ERR-CMP-008 rechaza otra comparación mientras haya LLM_CONCURRENCY vivas:
        # con un modelo de razonamiento tardan decenas de segundos. Se espera a que terminen para no dejarle esa carga a la prueba siguiente.
        t0 = time.time()
        while llamadas_vivas() > 0 and time.time() - t0 < ESPERA_HUERFANAS_S:
            time.sleep(0.5)
