"""Fusiona dos etiquetados independientes del golden por requisito y mide el acuerdo (protocolo qa-ia: doble etiquetado).

    python scripts/fusionar_golden.py A.csv B.csv NORMA.pdf MANUAL.pdf [--salida tests]

Entrada: dos CSV con `articulo,naturaleza,req_id,ancla_literal,obligatorio,estado_esperado,secciones_respaldo,cita_manual,nota`.
Salida (en --salida, por defecto tests/):
  golden_requisitos_arlaft.csv  un requisito por fila, con el acuerdo (`alta` = ambos etiquetadores coinciden; `por_confirmar` = difieren o
                                solo uno lo vio) y `confianza_mapeo`. Lo que está `por_confirmar` NO entra a las métricas hasta que el usuario lo decida.
  golden_arlaft_v2.csv          pares (artículo, sección) derivados de los requisitos con acuerdo, con el mismo formato que golden_arlaft.csv
                                (los scripts de medición lo leen igual), más filas `omision` para los artículos sin ninguna cobertura.
  y el informe de acuerdo (naturaleza, requisitos emparejados, estado, kappa) en la salida estándar.
Solo se leen identificadores y anclas: el texto de la norma y del manual viene de los PDF de documentos/.
"""
import argparse
import csv
import re
from pathlib import Path

from backend.extraction.lector import leer_documento

try:                                    # con las zonas (rama feat/zonas-test-val) la caché depende de la zona
    from backend.config import carpeta_bloques
except ImportError:
    carpeta_bloques = lambda zona=None: Path("output/bloques")

norm = lambda t: re.sub(r"\s+", " ", t).strip()


def leer(ruta):
    return list(csv.DictReader(open(ruta, encoding="utf-8", newline="")))


def posicion(texto: str, ancla: str) -> tuple[int, int] | None:
    i = norm(texto).find(norm(ancla))
    return (i, i + len(norm(ancla))) if i >= 0 else None


def iou(a, b) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union else 0.0


def kappa(pares: list[tuple[str, str]]) -> float:
    if not pares:
        return float("nan")
    n = len(pares)
    cats = sorted({x for p in pares for x in p})
    po = sum(a == b for a, b in pares) / n
    pe = sum((sum(a == c for a, _ in pares) / n) * (sum(b == c for _, b in pares) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main(a):
    nsecs = leer_documento(Path(a.norma), "N", "normativa", cache=carpeta_bloques())
    msecs = leer_documento(Path(a.manual), "M", "manual_control", cache=carpeta_bloques())
    art = {}
    for s in nsecs:
        if s.es_hoja and s.nivel == "articulo" and s.identificador.lower().startswith("art") and re.search(r"\d+", s.identificador):
            art[re.search(r"\d+", s.identificador).group()] = s
    sec = {s.identificador: s for s in msecs if s.es_hoja}
    A, B = leer(a.A), leer(a.B)
    articulos = sorted({f["articulo"] for f in A} | {f["articulo"] for f in B}, key=int)

    def por_art(filas, n):
        return [f for f in filas if f["articulo"] == n]

    reqs, nat_pares, emparejados, est_pares, solo = [], [], 0, [], 0
    for n in articulos:
        fa, fb = por_art(A, n), por_art(B, n)
        na, nb = (fa[0]["naturaleza"] if fa else ""), (fb[0]["naturaleza"] if fb else "")
        nat_pares.append((na, nb))
        if na != nb:                      # la naturaleza difiere: el artículo entero queda por confirmar y no entra a las métricas
            reqs.append({"articulo": n, "naturaleza": f"{na}|{nb}", "req_id": "", "ancla_literal": "", "obligatorio": "", "estado_esperado": "",
                         "secciones_respaldo": "", "cita_manual": "", "estado_A": "", "estado_B": "", "acuerdo": "por_confirmar",
                         "nota": "los etiquetadores discrepan en la naturaleza del artículo"})
            continue
        if na != "obligacion":
            reqs.append({"articulo": n, "naturaleza": na, "req_id": "", "ancla_literal": "", "obligatorio": "", "estado_esperado": "", "secciones_respaldo": "",
                         "cita_manual": "", "estado_A": "", "estado_B": "", "acuerdo": "alta", "nota": ""})
            continue
        textoart = art[n].texto_literal
        ra = [(f, posicion(textoart, f["ancla_literal"])) for f in fa if f["req_id"]]
        rb = [(f, posicion(textoart, f["ancla_literal"])) for f in fb if f["req_id"]]
        usados, filas_art = set(), []
        for f1, p1 in ra:
            mejor, mj = None, 0.0
            for j, (f2, p2) in enumerate(rb):
                if j in usados or not p1 or not p2:
                    continue
                v = iou(p1, p2)
                if v > mj:
                    mejor, mj = j, v
            if mejor is not None and mj >= 0.3:
                usados.add(mejor)
                f2 = rb[mejor][0]
                emparejados += 1
                est_pares.append((f1["estado_esperado"], f2["estado_esperado"]))
                ok = f1["estado_esperado"] == f2["estado_esperado"] and f1["obligatorio"] == f2["obligatorio"]
                ss = sorted({s.strip() for f in (f1, f2) for s in f["secciones_respaldo"].split(";") if s.strip()})
                filas_art.append((p1[0], {"articulo": n, "naturaleza": na, "ancla_literal": f1["ancla_literal"], "obligatorio": f1["obligatorio"],
                    "estado_esperado": f1["estado_esperado"] if ok else "", "secciones_respaldo": ";".join(ss), "cita_manual": f1["cita_manual"],
                    "estado_A": f1["estado_esperado"], "estado_B": f2["estado_esperado"], "acuerdo": "alta" if ok else "por_confirmar",
                    "nota": f1["nota"] if ok else f"A: {f1['estado_esperado']}/{f1['obligatorio']} · B: {f2['estado_esperado']}/{f2['obligatorio']}"}))
            else:
                solo += 1
                filas_art.append((p1[0] if p1 else 0, {"articulo": n, "naturaleza": na, "ancla_literal": f1["ancla_literal"], "obligatorio": f1["obligatorio"],
                    "estado_esperado": "", "secciones_respaldo": f1["secciones_respaldo"], "cita_manual": f1["cita_manual"], "estado_A": f1["estado_esperado"],
                    "estado_B": "", "acuerdo": "por_confirmar", "nota": "solo lo vio el etiquetador A"}))
        for j, (f2, p2) in enumerate(rb):
            if j not in usados:
                solo += 1
                filas_art.append((p2[0] if p2 else 0, {"articulo": n, "naturaleza": na, "ancla_literal": f2["ancla_literal"], "obligatorio": f2["obligatorio"],
                    "estado_esperado": "", "secciones_respaldo": f2["secciones_respaldo"], "cita_manual": f2["cita_manual"], "estado_A": "",
                    "estado_B": f2["estado_esperado"], "acuerdo": "por_confirmar", "nota": "solo lo vio el etiquetador B"}))
        for k, (_, fila) in enumerate(sorted(filas_art, key=lambda x: x[0]), 1):
            fila["req_id"] = f"R{k}"
            reqs.append(fila)

    cols = ["articulo", "naturaleza", "req_id", "ancla_literal", "obligatorio", "estado_esperado", "secciones_respaldo", "cita_manual", "estado_A", "estado_B", "acuerdo", "nota"]
    salida = Path(a.salida)
    with open(salida / "golden_requisitos_arlaft.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + ["confianza_mapeo"])
        w.writeheader()
        for r in reqs:
            w.writerow({**{c: r.get(c, "") for c in cols}, "confianza_mapeo": "" if r["acuerdo"] == "alta" else "por_confirmar"})

    # Pares derivados: solo requisitos obligatorios con acuerdo.
    pares, omision = {}, []
    for n in articulos:
        rs = [r for r in reqs if r["articulo"] == n and r["req_id"] and r["acuerdo"] == "alta" and r["obligatorio"] == "si"]
        if not rs:
            continue
        cubiertas = False
        for r in rs:
            for s in [x for x in r["secciones_respaldo"].split(";") if x]:
                rel = 2 if r["estado_esperado"] == "cubierto" else 1
                pares[(n, s)] = max(pares.get((n, s), 0), rel)
                cubiertas = True
        if not cubiertas:
            omision.append(n)
    apoyos = {}
    for r in reqs:
        for s in [x for x in r.get("secciones_respaldo", "").split(";") if x]:
            apoyos.setdefault((r["articulo"], s), set()).add(r["req_id"])
    with open(salida / "golden_arlaft_v2.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "articulo_id", "articulo_identificador", "seccion_id", "seccion_identificador", "seccion_titulo", "cobertura_esperada", "relevancia", "estrato", "nota"])
        i = 0
        for (n, s), rel in sorted(pares.items(), key=lambda x: (int(x[0][0]), x[0][1])):
            i += 1
            largo = len(sec[s].texto_literal) > 1500 if s in sec else False
            multi = sum(1 for (aa, _), _v in pares.items() if aa == n) > 1
            estrato = "+".join(["cumple" if rel == 2 else "parcial"] + (["larga"] if largo else []) + (["multiseccion"] if multi else []))
            w.writerow([f"G2-{i:03d}", art[n].id, art[n].identificador, sec[s].id, s, sec[s].titulo or "", "cumple" if rel == 2 else "parcial", rel, estrato, "derivado de requisitos con acuerdo"])
        for n in omision:
            i += 1
            w.writerow([f"G2-{i:03d}", art[n].id, art[n].identificador, "", "", "", "omision", 0, "omision", "todos los requisitos obligatorios no cubiertos"])

    # Informe de acuerdo
    n_nat = sum(x == y for x, y in nat_pares)
    print(f"Artículos: {len(articulos)} · naturaleza coincide en {n_nat}/{len(nat_pares)} · kappa naturaleza {kappa(nat_pares):.2f}")
    print(f"Requisitos: A {sum(1 for f in A if f['req_id'])} · B {sum(1 for f in B if f['req_id'])} · emparejados {emparejados} · solo en uno {solo}")
    ok = sum(x == y for x, y in est_pares)
    print(f"Estado en los emparejados: acuerdo {ok}/{len(est_pares)} ({100 * ok / max(len(est_pares), 1):.0f} %) · kappa {kappa(est_pares):.2f}")
    alta = [r for r in reqs if r["acuerdo"] == "alta" and r["req_id"]]
    print(f"Requisitos con acuerdo (entran al golden): {len(alta)} · por confirmar: {sum(1 for r in reqs if r['acuerdo'] != 'alta')}")
    print("Estados con acuerdo:", {e: sum(1 for r in alta if r['estado_esperado'] == e) for e in ('cubierto', 'parcial', 'no_cubierto')})
    print(f"Pares derivados: {len(pares)} (cubierto {sum(1 for v in pares.values() if v == 2)}, parcial {sum(1 for v in pares.values() if v == 1)}) · omisiones: {len(omision)}")
    print("Artículos con requisitos apoyados por ≥2 secciones:", sorted({n for n in articulos if sum(1 for (aa, _s) in pares if aa == n) > 1}, key=int))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("A"); p.add_argument("B"); p.add_argument("norma"); p.add_argument("manual")
    p.add_argument("--salida", default="tests")
    main(p.parse_args())
