"""Prueba de humo de extremo a extremo con un ejemplo REDUCIDO (D-66, decisión del usuario del 25 nov 2026): comprueba que la app responde de punta a punta con modelos reales
sin gastar una comparación completa (por defecto 3 artículos x 3 secciones = hasta 9 pares).

    python scripts/prueba_humo.py http://localhost:8000
    python scripts/prueba_humo.py https://<app>.databricksapps.com --perfil-databricks DEFAULT     # la app desplegada: usa el token del CLI (no se imprime)
    python scripts/prueba_humo.py URL --articulos 2 --secciones 2 --pdf documentos/manuales/MOCK-DEMO-02.pdf   # además sube un PDF y espera a Docling

Pasos: salud con el LLM real, sesión, «Cargar ejemplo» (marcado como ejemplo), comparación reducida, Excel descargable y, opcional, un PDF con Docling.
Sale con código 0 si todo cumple y 1 si algo falla; imprime solo conteos y tiempos (nunca correos, tokens ni textos de documentos)."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


def hojas(arboles: list[dict], solo_marcadas: bool) -> list[str]:
    """Ids de las hojas utilizables (no excluidas) de los árboles de secciones; con `solo_marcadas`, solo las preseleccionadas."""
    salida: list[str] = []

    def rec(n: dict) -> None:
        for h in n.get("hijos", []):
            rec(h)
        if n.get("hoja") and not n.get("excluida") and (not solo_marcadas or n.get("seleccionada")):
            salida.append(n["id"])

    for a in arboles:
        for n in a["nodos"]:
            rec(n)
    return salida


def esperar(c: httpx.Client, job: dict, limite_s: int) -> dict:
    t0 = time.time()
    while job.get("estado") in ("en_cola", "en_curso") and time.time() - t0 < limite_s:
        time.sleep(4)
        job = c.get(f"/api/jobs/{job['job_id']}").json()
    return job


def exigir_https(url: str, con_token: bool) -> None:
    """El token del CLI solo viaja por https (un http:// escrito por error lo enviaría en claro)."""
    if con_token and not url.lower().startswith("https://"):
        raise SystemExit("Con --perfil-databricks la URL debe empezar por https:// (el token no viaja en claro).")


def token_cli(perfil: str) -> str:
    return json.loads(subprocess.run(["databricks", "auth", "token", "--profile", perfil, "-o", "json"], capture_output=True, text=True, check=True).stdout)["access_token"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url")
    ap.add_argument("--perfil-databricks", help="perfil del CLI de Databricks para una app desplegada (OAuth del usuario)")
    ap.add_argument("--articulos", type=int, default=3)
    ap.add_argument("--secciones", type=int, default=3)
    ap.add_argument("--pdf", help="PDF opcional para probar Docling en el servidor")
    ap.add_argument("--limite-s", type=int, default=900, help="espera máxima de cada trabajo")
    a = ap.parse_args()

    exigir_https(a.url, bool(a.perfil_databricks))
    cab = {"Authorization": f"Bearer {token_cli(a.perfil_databricks)}"} if a.perfil_databricks else {}
    c = httpx.Client(base_url=a.url.rstrip("/"), headers=cab, timeout=120, follow_redirects=False)
    fallos: list[str] = []

    def comprobar(nombre: str, ok: bool, detalle: str = "") -> None:
        print(f"{'OK ' if ok else 'FALLA'}  {nombre}{(' · ' + detalle) if detalle else ''}")
        if not ok:
            fallos.append(nombre)

    h = c.get("/api/health")
    salud = h.json() if h.status_code == 200 else {}
    comprobar("salud con el LLM real", h.status_code == 200 and salud.get("estado") == "ok" and salud.get("llm") is True, f"HTTP {h.status_code}")
    if fallos:
        return 1
    c.get("/api/session")                                                       # abre la sesión (cookie), como el navegador al entrar
    r = c.post("/api/samples/load")
    docs = r.json() if r.status_code == 200 else []
    comprobar("«Cargar ejemplo»", r.status_code == 200 and bool(docs) and all(d.get("es_ejemplo") for d in docs), f"{len(docs)} documentos marcados como ejemplo")
    if fallos:
        return 1
    arts = hojas(c.get("/api/sections/tree", params={"tipo": "normativa"}).json(), False)[:a.articulos]
    secs = hojas(c.get("/api/sections/tree", params={"tipo": "manual_control"}).json(), True)[:a.secciones]
    comprobar("el ejemplo trae secciones", bool(arts) and bool(secs), f"{len(arts)} artículos x {len(secs)} secciones")
    if fallos:
        return 1

    t0 = time.time()
    job = esperar(c, c.post("/api/comparisons", json={"articulo_ids": arts, "seccion_ids": secs}).json(), a.limite_s)
    comprobar("comparación reducida", job.get("estado") == "listo" and not job.get("errores"),
              f"{job.get('estado')} · {job.get('pares_hechos')}/{job.get('pares_total')} pares en {time.time() - t0:.0f} s · conteo {job.get('conteo_cobertura')} · a revisión {job.get('a_revision')}")
    cid = c.get("/api/session").json().get("comparacion_id")
    x = c.get(f"/api/comparisons/{cid}/excel") if cid else None
    comprobar("Excel descargable", x is not None and x.status_code == 200 and x.content[:2] == b"PK", f"{len(x.content) if x is not None else 0} bytes")

    if a.pdf:
        t1 = time.time()
        r = c.post("/api/documents", files=[("archivos", (Path(a.pdf).name, Path(a.pdf).read_bytes(), "application/pdf"))])
        ids = [d["id"] for d in r.json()] if r.status_code == 200 else []
        job = esperar(c, c.post("/api/documents/process", json={"doc_ids": ids}).json(), a.limite_s) if ids else {}
        estados = [d.get("estado") for d in c.get("/api/session").json().get("documentos", []) if d.get("id") in ids]
        comprobar("PDF con Docling", job.get("estado") == "listo" and estados == ["listo"], f"{time.time() - t1:.0f} s")

    print("\nRESULTADO:", "todo cumple" if not fallos else "FALLAN: " + ", ".join(fallos))
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
