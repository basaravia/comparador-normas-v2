"""Prototipo del paso 3a (docs/09 §3a): el LLM descompone cada artículo en requisitos y cada requisito consulta el manual.

    cd <checkout con config/.env> && STAGE=sandbox EMB_BATCH=8 PYTHONPATH=. python <ruta>/prototipo_descomposicion.py GOLDEN_REQ.csv NORMA.pdf MANUAL.pdf [--limite N]

Mide, contra el golden por requisito (solo los de acuerdo `alta`):
  - fidelidad: cuántos fragmentos del LLM son texto literal del artículo (ratio difuso >= 0,90) y qué fracción de las anclas del golden toca alguno;
  - recall@candidatos por par (artículo, sección) consultando con cada requisito del LLM (top-10 cada uno) frente al artículo entero y frente a las anclas ideales.
Persiste la descomposición en output/comparaciones/descomposicion__<modelo>.json (solo fragmentos del artículo, ya públicos en la norma; ignorado por git).
"""
import argparse, csv, json, re, sys, time
from collections import defaultdict
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import BaseModel
from backend.config import settings
from backend.engine.candidatos import candidatos
from backend.extraction.lector import leer_documento
from backend.llm.client import ModelClient
from backend.retrieval.exclusion import clasificar_secciones
from backend.retrieval.index import construir_indice

PROMPT = Path(__file__).resolve().parent.parent / "backend" / "prompts" / "requisitos.md"
norm = lambda t: re.sub(r"\s+", " ", t).strip()


class Req(BaseModel):
    id: str
    fragmento: str
    obligatorio: bool


class Desc(BaseModel):
    naturaleza_articulo: Literal["obligacion", "informativo", "no_aplica_entidad"]
    requisitos: list[Req] = []


def ratio_en(frag: str, texto: str) -> float:
    f, t = norm(frag), norm(texto)
    if f in t:
        return 1.0
    return SequenceMatcher(None, f, t, autojunk=False).find_longest_match(0, len(f), 0, len(t)).size / max(len(f), 1)


def main(a):
    n = leer_documento(Path(a.norma), "N", "normativa", cache=Path(a.cache))
    m = leer_documento(Path(a.manual), "M", "manual_control", cache=Path(a.cache))
    clas = clasificar_secciones(m); inc = [s for s in m if s.es_hoja and clas.get(s.id, (True, ""))[0]]
    arts = {re.search(r"\d+", s.identificador).group(): s for s in n if s.es_hoja and s.nivel == "articulo" and s.identificador.lower().startswith("art") and re.search(r"\d+", s.identificador)}
    gold = [r for r in csv.DictReader(open(a.golden, encoding="utf-8")) if r["acuerdo"] == "alta" and r["req_id"]]
    usar = sorted({r["articulo"] for r in gold}, key=int)[: a.limite]
    c = ModelClient(); sistema = PROMPT.read_text(encoding="utf-8")
    salida = Path("output/comparaciones"); salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / f"descomposicion__{settings.GROQ_LLM_MODEL.replace('/', '-')}.json"
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    for k in usar:
        if k in cache:
            continue
        s = arts[k]
        for intento in range(6):                      # el plan gratuito de Groq limita los tokens por minuto (429): se espera y se reintenta
            try:
                d = c.chat_json(sistema, f"<articulo>\nRuta: {' > '.join(s.ruta)}\n{s.texto_literal}\n</articulo>", Desc)
                cache[k] = d.model_dump()
                break
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    time.sleep(20)
                    continue
                cache[k] = {"error": str(e)[:200]}
                break
        else:
            cache[k] = {"error": "límite de tasa tras 6 intentos"}
        if "error" in cache[k]:
            print(f"art {k}: ERROR {cache[k]['error']}", flush=True)
            del cache[k]
            continue
        ruta.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"art {k}: {cache[k]['naturaleza_articulo']} · {len(cache[k]['requisitos'])} requisitos", flush=True)
    usar = [k for k in usar if k in cache]

    # --- fidelidad
    tot = lit = 0
    for k in usar:
        for r in cache[k].get("requisitos", []):
            tot += 1; lit += ratio_en(r["fragmento"], arts[k].texto_literal) >= 0.90
    nat_ok = sum(1 for k in usar if cache[k].get("naturaleza_articulo") == "obligacion")
    print(f"\nArtículos {len(usar)} · naturaleza obligacion {nat_ok} · requisitos del LLM {tot} · literales (>=0,90) {lit} ({100*lit/max(tot,1):.0f} %) · del golden {len([r for r in gold if r['articulo'] in usar and r['obligatorio']=='si'])}")
    cubiertas = tocadas = 0
    for r in gold:
        if r["articulo"] in usar and r["obligatorio"] == "si" and r["estado_esperado"] in ("cubierto", "parcial", "no_cubierto"):
            cubiertas += 1
            pos = norm(arts[r["articulo"]].texto_literal).find(norm(r["ancla_literal"]))
            fin = pos + len(norm(r["ancla_literal"]))
            for q in cache[r["articulo"]].get("requisitos", []):
                p = norm(arts[r["articulo"]].texto_literal).find(norm(q["fragmento"]))
                if p >= 0 and min(fin, p + len(norm(q["fragmento"]))) - max(pos, p) >= 0.5 * (fin - pos):
                    tocadas += 1; break
    print(f"Anclas obligatorias del golden con algún requisito del LLM que las cubre (>=50 %): {tocadas}/{cubiertas} ({100*tocadas/max(cubiertas,1):.0f} %)")

    # --- recuperación
    ident = {s.identificador: s.id for s in inc}
    nombres = {"N": "Norma", "M": "Manual"}
    i_m = construir_indice(inc, c, nombres)
    i_n = construir_indice([arts[k] for k in usar], c, nombres)
    todo = replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6, K_SUBCHUNKS=10**6)
    pares = defaultdict(set)
    for r in gold:
        if r["articulo"] in usar and r["obligatorio"] == "si" and r["estado_esperado"] in ("cubierto", "parcial"):
            for s in r["secciones_respaldo"].split(";"):
                if s in ident:
                    pares[r["articulo"]].add(ident[s])
    res = {"articulo": [0, []], "articulo top-21 (control)": [0, []], "requisitos LLM": [0, []]}
    n_pares = sum(len(v) for v in pares.values())
    for k in usar:
        art10 = [s for s, _ in candidatos(i_n.vectores_de(arts[k].id), i_m, todo)][:10]
        vq = c.embed_multi([q["fragmento"] for q in cache[k].get("requisitos", []) if q["obligatorio"]]) if cache[k].get("requisitos") else []
        rq = {s for v in vq for s, _ in candidatos(v, i_m, todo)[:10]}
        art21 = [s for s, _ in candidatos(i_n.vectores_de(arts[k].id), i_m, todo)][:21]
        for nombre, cand in (("articulo", set(art10)), ("articulo top-21 (control)", set(art21)), ("requisitos LLM", rq)):
            res[nombre][0] += len(pares[k] & cand); res[nombre][1].append(len(cand))
    for nombre, (hit, tam) in res.items():
        print(f"PARES recall@candidatos [{nombre}]: {hit}/{n_pares} = {100*hit/max(n_pares,1):.1f} % · candidatos por artículo {np.mean(tam):.1f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("golden"); p.add_argument("norma"); p.add_argument("manual"); p.add_argument("--limite", type=int, default=999); p.add_argument("--cache", default="output/bloques")
    main(p.parse_args())
