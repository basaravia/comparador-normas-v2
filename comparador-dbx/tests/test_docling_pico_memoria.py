"""P-28: el pico de memoria del lector se lee de los subprocesos ya terminados (en MB, sin importar si el sistema da KB o bytes)."""
import subprocess
import sys

from backend.extraction import docling_extractor as d


def test_el_pico_de_memoria_de_los_hijos_sube_tras_un_subproceso_que_reserva_memoria():
    antes = d.pico_memoria_hijos_mb()
    subprocess.run([sys.executable, "-c", "x = bytearray(150 * 1024 * 1024); x[::4096] = b'a' * len(x[::4096])"], check=True)
    despues = d.pico_memoria_hijos_mb()
    assert despues >= 150 and despues >= antes             # al menos lo que reservó el hijo (más lo que ya usa el intérprete)
    assert despues < 4000                                  # y está en MB: si se leyera en KB daría millones


def test_la_conversion_a_mb_distingue_linux_en_kb_de_macos_en_bytes(monkeypatch):
    """`ru_maxrss` lo da el sistema operativo: Linux en KB, macOS en bytes. Se dicta el contador para ejercitar las dos ramas aquí (el dev corre en Mac)."""
    monkeypatch.setattr(d.resource, "getrusage", lambda quien: type("U", (), {"ru_maxrss": 512 * 1024})())
    monkeypatch.setattr(d.sys, "platform", "linux")
    assert d.pico_memoria_hijos_mb() == 512.0                                  # 524288 KB
    monkeypatch.setattr(d.resource, "getrusage", lambda quien: type("U", (), {"ru_maxrss": 512 * 1024 * 1024})())
    monkeypatch.setattr(d.sys, "platform", "darwin")
    assert d.pico_memoria_hijos_mb() == 512.0                                  # 536870912 bytes


def test_sin_subprocesos_terminados_el_pico_es_cero(monkeypatch):
    monkeypatch.setattr(d.resource, "getrusage", lambda quien: type("U", (), {"ru_maxrss": 0})())
    assert d.pico_memoria_hijos_mb() == 0.0
