"""Mide tiempo y RAM de `generar_papel` con ~100 artículos × 1 respaldo (textos reales).

Se lanza desde el notebook 05 con `taskset -c 3` y `OMP_NUM_THREADS=1`. Imprime un JSON.
"""
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.config import carpeta_manuales
from backend.output.workpaper import generar_papel  # noqa: E402
from scripts.datos_papel import armar_entrada, cargar_manual, cargar_norma, documento  # noqa: E402


def pico_mb() -> float:
    """Pico de RAM residente del proceso (VmHWM de /proc)."""
    for linea in Path("/proc/self/status").read_text().splitlines():
        if linea.startswith("VmHWM"):
            return round(int(linea.split()[1]) / 1024, 1)
    return -1.0


NORMAS = Path(sys.argv[1])
MANUAL = carpeta_manuales() / "MOCK-DEMO-01.pdf"
N_ART = int(sys.argv[2]) if len(sys.argv) > 2 else 100
SALIDA = RAIZ / "output" / "papel_100.xlsx"
SALIDA.parent.mkdir(exist_ok=True)

pdf = next(NORMAS.glob("Proyecto-de-Ley-Organica-Organica*.pdf"))
entrada = armar_entrada([(documento(pdf, "N1", "normativa"), cargar_norma(pdf, "N1"))],
                        (documento(MANUAL, "M1", "manual_control"), cargar_manual(MANUAL, "M1")),
                        max_articulos=N_ART)
base_mb = pico_mb()                       # PDFs cargados y entrada armada
t0 = time.perf_counter()
conteos = generar_papel(entrada, SALIDA)
segundos = time.perf_counter() - t0
print(json.dumps({"articulos": len(entrada.filas), "pares": len(entrada.pares), "respaldos_por_articulo": 1,
                  "segundos_generar": round(segundos, 2), "ram_pico_antes_mb": base_mb,
                  "ram_pico_final_mb": pico_mb(), "xlsx_kb": SALIDA.stat().st_size // 1024, "conteos": conteos}))
