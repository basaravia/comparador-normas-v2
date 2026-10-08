"""Convención del proyecto (CLAUDE.md): todo proceso largo o iterativo muestra una barra de progreso y un log sencillo.

- `configurar_logs()`: muestra en el notebook (o en la consola) lo que hace `backend`, con hora, sin romper las barras.
- `progreso(nombre, unidad)`: barra para cualquier función del backend que acepte `progreso(hechos, total)`
  (`extraer`, `ModelClient.embed`, `construir_indice`).

    configurar_logs()
    with progreso("Docling · LA/FT", "pág") as cb:
        bloques = extraer(pdf, cb)
"""
import logging
from contextlib import contextmanager
from typing import Callable, Iterator

from tqdm import tqdm


class _ManejadorTqdm(logging.Handler):
    """Escribe con `tqdm.write` para que un mensaje no parta la barra que está en pantalla."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:  # noqa: BLE001 - un log nunca debe tumbar el proceso
            self.handleError(record)


def configurar_logs(nivel: str = "INFO") -> None:
    """Deja los logs de `backend` visibles: `10:42:07  Docling: 43 bloques en 33 s`. Se puede llamar varias veces."""
    logger = logging.getLogger("backend")
    logger.handlers = [h for h in logger.handlers if not isinstance(h, _ManejadorTqdm)]
    manejador = _ManejadorTqdm()
    manejador.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    logger.addHandler(manejador)
    logger.setLevel(nivel)
    logger.propagate = False


@contextmanager
def progreso(nombre: str, unidad: str = "it") -> Iterator[Callable[[int, int], None]]:
    """Barra de progreso; entrega el callback `cb(hechos, total)` que esperan las funciones del backend."""
    barra = tqdm(total=None, desc=nombre, unit=unidad)

    def cb(hechos: int, total: int) -> None:
        barra.total, barra.n = total, hechos
        barra.refresh()

    try:
        yield cb
    finally:
        barra.close()
