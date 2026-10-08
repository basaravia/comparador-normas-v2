"""Seccionado en cascada (docs/07 §2): de bloques `{texto, pagina, tipo, nivel?}` a `Seccion`.

Nivel 1 · patrones  (`patterns.PATRONES`, multi-esquema): un patrón es "del documento" si aparece ≥ 3 veces con numeración creciente;
  libro/título/capítulo/sección valen con menos si están validados (patrón + negrita + línea propia + árbol consistente).
Nivel 2 · tipografía: encabezados por tamaño de fuente y negrita (PyMuPDF `get_text("dict")`) y de Docling.
Nivel 3 · longitud: bloques de ~SECCION_CHARS caracteres respetando párrafos; `seccionado_incierto=True`.
Cada nivel solo corre si el anterior no produjo estructura; cada sección registra su `estrategia`.
Los literales a), b) no abren sección: quedan dentro del texto del artículo.
"""
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from backend.config import settings
from backend.core.errors import ComparadorError
from backend.extraction.patterns import COLA_DOCUMENTO, CORTE_ARTICULOS, PATRONES, numero
from backend.models import Seccion

log = logging.getLogger(__name__)

MIN_APARICIONES = 3        # regla de docs/07: patrón "del documento" / mínimo de encabezados tipográficos
LINEA_MAX = 300            # solo se miran los primeros caracteres de la primera línea del bloque
TITULO_MAX = 150           # una línea más larga que esto no es un título
ABREVIATURA = {"libro": "L", "titulo": "T", "capitulo": "C", "seccion": "SEC", "romano": "R", "articulo": "ART",
               "disposicion": "DISP", "numeral": "N", "letra": "LET"}   # id de sección: "N1:T-2/C-3/ART-15"
PADRES = {"libro", "titulo", "capitulo", "seccion"}   # aceptables con < 3 apariciones si están validados
ENCABEZADOS = {"libro", "titulo", "capitulo", "seccion", "articulo"}   # los que valida la tipografía (negrita)
REINICIAN = {"capitulo", "seccion", "romano", "numeral", "disposicion"}  # su numeración vuelve a 1 al abrir el padre
SOLO_MANUAL = {"numeral", "romano", "letra"}   # en una normativa con artículos son enumeraciones dentro del artículo


class SeccionadoError(ComparadorError):
    codigo = "ERR-SEC-001"
    mensaje_negocio = "El documento tiene un bloque de texto demasiado grande para procesarlo. Revisa que sea el archivo correcto."


def parsear_bloques(bloques: list[dict[str, Any]], doc_id: str, tipo_doc: Literal["normativa", "manual_control"],
                    pdf: Path | None = None, avisos: list[str] | None = None) -> list[Seccion]:
    """Aplica la cascada. `pdf` (opcional) habilita el nivel 2 con la tipografía real; `avisos` recibe las advertencias."""
    avisos = avisos if avisos is not None else []
    avisos += [f"Figura en la pág. {b['pagina']}: su contenido (imagen) no se analiza." for b in bloques if b.get("tipo") == "figura"]
    bloques = [b for b in bloques if b.get("tipo") != "figura"]
    for b in bloques:
        if len(b["texto"]) > settings.SECCION_BLOQUE_MAX:
            raise SeccionadoError(f"Bloque de {len(b['texto'])} caracteres (máximo {settings.SECCION_BLOQUE_MAX}).")
    partidos = _partir(bloques)
    marcas = _marcas_patrones(partidos, tipo_doc, negritas_pdf(pdf) if pdf else None, avisos)
    if marcas:
        return _armar(partidos, marcas, doc_id, tipo_doc, "patron", avisos)
    marcas = _marcas_tipografia(bloques, pdf)
    if marcas:
        return _armar(bloques, marcas, doc_id, tipo_doc, "tipografia", avisos)
    return _por_longitud(bloques, doc_id, tipo_doc)


# --- Nivel 1: patrones ---------------------------------------------------------------------------

def _texto(b: dict) -> str:
    """Texto del bloque con su numeración (`1.`, `a)`) si es un elemento de lista numerada.

    El marcador va aparte del texto del bloque para que los patrones de encabezado no confundan una lista con una sección."""
    return f"{b['marcador']} {b['texto']}" if b.get("marcador") else b["texto"]


def _primera_linea(texto: str) -> str:
    return texto.split("\n", 1)[0][:LINEA_MAX]


def _partir(bloques: list[dict]) -> list[dict]:
    """Parte los bloques donde Docling juntó varios artículos o disposiciones (ver `CORTE_ARTICULOS`)."""
    salida = []
    for b in bloques:
        cortes = [m.start() for m in CORTE_ARTICULOS.finditer(b["texto"])]
        if not cortes:
            salida.append(b)
            continue
        limites = [0, *cortes, len(b["texto"])]
        partes = [b["texto"][a:z].strip() for a, z in zip(limites, limites[1:]) if b["texto"][a:z].strip()]
        salida += [dict(b, texto=t, marcador=b.get("marcador", "") if k == 0 else "") for k, t in enumerate(partes)]   # la numeración, solo en el primer trozo
    return salida


def _creciente(nums: list) -> bool:
    """¿Hay una racha de ≥ 3 apariciones no decrecientes con al menos una subida? (tolera duplicados)"""
    nums = [n for n in nums if n]
    racha, sube = 1, False
    for a, b in zip(nums, nums[1:]):
        racha, sube = (racha + 1, sube or b > a) if b >= a else (1, False)
        if racha >= MIN_APARICIONES and sube:
            return True
    return False


def _sin_tildes(texto: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().casefold()))


def negritas_pdf(pdf: Path) -> dict[int, set[str]]:
    """Página → textos (normalizados) con que empieza en negrita cada línea del PDF ("Artículo 3.-", "CAPÍTULO I")."""
    import pymupdf
    out: dict[int, set[str]] = {}
    with pymupdf.open(pdf) as d:
        for n, pagina in enumerate(d, 1):
            for bloque in pagina.get_text("dict")["blocks"]:
                for ln in bloque.get("lines", []):
                    inicio = ""
                    for sp in ln["spans"]:
                        if not sp["text"].strip():
                            inicio += sp["text"]
                        elif sp["flags"] & 16 or "bold" in sp["font"].lower():
                            inicio += sp["text"]
                        else:
                            break
                    if inicio.strip() and len(ln["spans"]) and len("".join(x["text"] for x in ln["spans"])) <= 400:
                        out.setdefault(n, set()).add(_sin_tildes(inicio))
    return out


def _filtrar_negrita(todas, bloques, negritas, avisos):
    """Un encabezado de libro/título/capítulo/sección/artículo solo cuenta si su identificador abre una línea en negrita
    (descarta menciones como "conforme al artículo 5"). Solo se aplica a un tipo de patrón si la mayoría de sus
    candidatos está en negrita (si el documento no usa negrita para ese tipo, no se filtra).
    Devuelve (candidatos filtrados, {(bloque, clave)} de los que sí están en negrita)."""
    def en_negrita(i, m):
        ident = _sin_tildes(m.group("id"))
        pag = bloques[i].get("pagina", 1)
        return any(t == ident or t.startswith(ident + " ") for q in (pag, pag + 1) for t in negritas.get(q, ()))
    ok = {(i, p.clave): en_negrita(i, m) for i, hits in enumerate(todas) for p, m in hits if p.clave in ENCABEZADOS}
    por_clave: dict[str, list] = {}
    for (i, clave), bien in ok.items():
        por_clave.setdefault(clave, []).append(bien)
    filtrar = {c for c, v in por_clave.items() if sum(v) * 2 >= len(v)}
    salida = []
    for i, hits in enumerate(todas):
        quedan = [(p, m) for p, m in hits if ok.get((i, p.clave), True) or p.clave not in filtrar]
        if len(quedan) < len(hits):
            avisos.append(f"Descartado por tipografía (no está en negrita): {_primera_linea(bloques[i]['texto'])[:60]!r} (pág. {bloques[i].get('pagina')}).")
        salida.append(quedan)
    return salida, {k for k, bien in ok.items() if bien}


def _marcas_patrones(bloques, tipo_doc, negritas=None, avisos=None) -> dict[int, dict]:
    """Índice de bloque → marca de sección. Un patrón vale si es "del documento" (≥ 3 apariciones con numeración
    creciente) o, para libro/título/capítulo/sección, si está validado: patrón + negrita + línea propia (el árbol
    lo revisa después en `_validar`). {} si no hay ninguno."""
    avisos = avisos if avisos is not None else []
    todas = []  # por bloque: todos los patrones que coinciden con su primera línea
    for b in bloques:
        linea = _primera_linea(b["texto"])
        todas.append([(p, m) for p in PATRONES if p.rango is not None and (m := p.regex.match(linea))])
    en_negrita = set()
    if negritas:
        todas, en_negrita = _filtrar_negrita(todas, bloques, negritas, avisos)

    def num_de(p, m):
        g = m.groupdict()
        return numero(g.get("num"), g.get("suf") or g.get("suf2"), p.clave == "letra")

    nums: dict[str, list] = {}
    for hits in todas:
        for p, m in hits:
            nums.setdefault(p.clave, []).append(num_de(p, m))
    activos = {p.clave for p in PATRONES if not p.siempre and _creciente(nums.get(p.clave, []))}
    validados = {c for (i, c) in en_negrita if c in PADRES and c not in activos}  # encabezados con < 3 apariciones, en negrita
    if not activos and not validados:
        return {}
    hay_articulos = tipo_doc == "normativa" and any(p.nivel == "articulo" and p.clave in activos for p in PATRONES)
    activos |= {p.clave for p in PATRONES if p.siempre}  # los encabezados sin número valen siempre
    if hay_articulos:
        activos -= SOLO_MANUAL

    marcas, en_disposiciones = {}, False
    for i, hits in enumerate(todas):
        elegido = next(((p, m) for p, m in hits if p.clave in activos or (p.clave in validados and (i, p.clave) in en_negrita)), None)
        if not elegido:
            continue
        p, m = elegido
        clave, rango = p.clave, p.rango
        if clave == "disposiciones":
            en_disposiciones = True
        elif clave in ("libro", "titulo", "capitulo", "seccion"):
            en_disposiciones = False
        elif clave == "articulo" and en_disposiciones:
            continue  # "Art. 317" citado dentro de una disposición reformatoria: es texto, no un artículo de la norma
        num = num_de(p, m)
        base = numero(m.groupdict().get("num"), None, clave == "letra")
        if clave == "numeral" and num:
            rango += len(num) - 1
        suf = (m.groupdict().get("suf") or m.groupdict().get("suf2") or "").upper()
        token = f"{ABREVIATURA[clave]}-{'.'.join(map(str, base))}{'-' + suf if suf else ''}" if clave in ABREVIATURA and base else None
        validado = clave in validados and clave not in activos
        if validado:
            avisos.append(f"Encabezado aceptado con menos de 3 apariciones (patrón + negrita + línea propia): {' '.join(m.group('id').split())!r} (pág. {bloques[i].get('pagina')}).")
        marcas[i] = dict(clave=clave, nivel=p.nivel, rango=rango, ident=" ".join(m.group("id").split()).rstrip("."),
                         token=token, num=num, validado=validado, resto=_primera_linea(bloques[i]["texto"])[m.end("id"):])
    return marcas


# --- Nivel 2: tipografía --------------------------------------------------------------------------

def _norm(texto: str) -> str:
    return re.sub(r"\W+", "", texto.casefold())


def _encabezados_pdf(pdf: Path) -> dict[int, list[tuple[str, float]]]:
    """Página → [(texto normalizado, tamaño)] de las líneas con tamaño mayor al del cuerpo o en negrita."""
    import pymupdf
    lineas, por_tamano = [], Counter()
    with pymupdf.open(pdf) as d:
        for n, pagina in enumerate(d, 1):
            for bloque in pagina.get_text("dict")["blocks"]:
                for ln in bloque.get("lines", []):
                    spans = [s for s in ln["spans"] if s["text"].strip()]
                    texto = "".join(s["text"] for s in spans).strip()
                    if not texto:
                        continue
                    tam = round(max(s["size"] for s in spans) * 2) / 2
                    negrita = all(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans)
                    por_tamano[tam] += len(texto)
                    lineas.append((n, texto, tam, negrita))
    if not por_tamano:
        return {}
    cuerpo = por_tamano.most_common(1)[0][0]
    out: dict[int, list] = {}
    for n, texto, tam, negrita in lineas:
        if len(texto) <= TITULO_MAX and (tam >= cuerpo + 1 or (negrita and tam >= cuerpo - 0.5)):
            out.setdefault(n, []).append((_norm(texto), tam))
    return out


def _marcas_tipografia(bloques, pdf) -> dict[int, dict]:
    """Encabezados = líneas de mayor tamaño/negrita del PDF + bloques `encabezado` de Docling (con su `nivel`)."""
    tipog = _encabezados_pdf(pdf) if pdf else {}
    cand = {}  # índice de bloque → (tamaño o None, nivel de Docling)
    for i, b in enumerate(bloques):
        if b.get("tipo") == "tabla":
            continue
        linea = _norm(_primera_linea(b["texto"]))
        tam = next((t for texto, t in tipog.get(b.get("pagina"), []) if len(texto) >= 4 and linea.startswith(texto)), None)
        if tam is not None or b.get("tipo") == "encabezado":
            cand[i] = (tam, b.get("nivel") or 1)
    if len(cand) < MIN_APARICIONES:
        return {}
    tamanos = sorted({t for t, _ in cand.values() if t is not None}, reverse=True)  # el mayor = nivel más alto
    marcas = {}
    for i, (tam, nivel) in cand.items():
        rango = tamanos.index(tam) if tam is not None else max(nivel - 1, 0)
        marcas[i] = dict(clave="tipografia", nivel="seccion", rango=rango, token=None, num=None, resto="",
                         ident=" ".join(_primera_linea(bloques[i]["texto"]).split()))
    return marcas


# --- Armado del árbol (niveles 1 y 2) ----------------------------------------------------------------

def _slug(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "-", sin_tildes.upper()).strip("-")


def _titulo(nodo: dict) -> str | None:
    """Título corto: lo que sigue al identificador en su línea o, si no hay, la línea siguiente."""
    resto = nodo["resto"].lstrip(" \t.:-–—").strip()
    if not resto:  # encabezado partido en dos líneas o en dos bloques: "CAPÍTULO I" + título
        lineas = "\n".join(nodo["textos"][:2]).split("\n", 2)
        resto = lineas[1][:LINEA_MAX].strip() if len(lineas) > 1 else ""
    return resto if resto and len(resto) <= TITULO_MAX and not resto.endswith((".", ":", ";", ",")) else None


def _validar(nodos, descartados, avisos) -> set[int]:
    """Reglas del árbol (solo patrones). Devuelve los nodos inciertos (y sus descendientes); la ruta nunca se inventa:
    1. un padre (no raíz) con hijos de niveles distintos: los más profundos cuelgan de donde no deben;
    2. numeración: no decrece; capítulo/sección/numeral/disposición empiezan en 1 al abrir su padre; los artículos crecen en todo el documento;
    3. un numeral `N.M` cuelga de un padre numerado `N`."""
    vivos = [k for k in range(len(nodos)) if k not in descartados]
    malos: set[int] = set()

    def malo(k, motivo):
        malos.add(k)
        avisos.append(f"Seccionado incierto en {nodos[k]['ident']} (pág. {nodos[k]['ini']}): {motivo}.")

    hijos: dict = {}
    for k in vivos:
        hijos.setdefault(nodos[k]["padre"], []).append(k)
    for padre, ks in hijos.items():
        minimo = min(nodos[k]["rango"] for k in ks)
        for k in ks if padre is not None else []:
            if nodos[k]["rango"] > minimo:
                malo(k, "cuelga del mismo padre que una sección de nivel superior")
    ultimo: dict = {}
    for k in vivos:
        n = nodos[k]
        if not n["num"]:
            continue
        llave = ("*", n["clave"]) if n["clave"] == "articulo" else (n["padre"], n["clave"])
        previo = ultimo.get(llave)
        if previo is None and n["clave"] in REINICIAN and n["num"][-1] != 1 and not n.get("validado"):
            malo(k, "la numeración no empieza en 1 al abrir el padre")
        elif previo is not None and n["num"] < previo:
            malo(k, f"numeración decreciente ({previo} → {n['num']})")
        ultimo[llave] = n["num"]
        padre = nodos[n["padre"]] if n["padre"] is not None else None
        if n["clave"] == "numeral" and padre and padre["num"] and n["num"][0] != padre["num"][0]:
            malo(k, f"el numeral no corresponde a su padre {padre['ident']}")
    for k in vivos:  # lo que cuelga de un nodo incierto tampoco es confiable
        if nodos[k]["padre"] in malos:
            malos.add(k)
    return malos


def _armar(bloques, marcas, doc_id, tipo_doc, estrategia, avisos) -> list[Seccion]:
    nodos, pila, en_cola = [], [], False
    for i, b in enumerate(bloques):
        if i in marcas:
            en_cola = False
            m = marcas[i]
            while pila and nodos[pila[-1]]["rango"] >= m["rango"]:
                pila.pop()
            nodos.append(dict(m, textos=[b["texto"]], ini=b["pagina"], fin=b["pagina"],
                              padre=pila[-1] if pila else None, ruta=[nodos[j]["ident"] for j in pila],
                              ruta_id=[nodos[j]["token"] or _slug(nodos[j]["ident"])[:40] for j in pila]))
            pila.append(len(nodos) - 1)
        elif nodos and not en_cola:  # lo anterior a la primera sección (portada, memorando, índice) no es evaluable
            if COLA_DOCUMENTO.match(b["texto"][:200]):
                en_cola = True       # firmas y certificaciones: no son texto de la norma; se ignoran hasta el próximo encabezado
                continue
            nodos[-1]["textos"].append(_texto(b))
            nodos[-1]["fin"] = b.get("pagina_fin", b["pagina"])

    # Un identificador repetido cuyo primer aparecer no tiene cuerpo es una entrada del índice: se descarta.
    # Si ambos tienen cuerpo es un duplicado real de la fuente: se conservan los dos (#2).
    clave_de = [f"{doc_id}:" + "/".join(n["ruta_id"] + [n["token"] or _slug(n["ident"])[:40]]) for n in nodos]
    descartados, ultimo = set(), {}
    for k, base in enumerate(clave_de):
        previo = ultimo.get(base)
        if previo is not None and len(nodos[previo]["textos"]) <= 1:
            descartados.add(previo)
        ultimo[base] = k
    inciertos = _validar(nodos, descartados, avisos) if estrategia == "patron" else set()
    padres = {n["padre"] for k, n in enumerate(nodos) if k not in descartados}
    articulos = tipo_doc == "normativa" and any(n["nivel"] == "articulo" for n in nodos)

    secciones, cuenta = [], Counter()
    for k, n in enumerate(nodos):
        if k in descartados:
            continue
        cuenta[clave_de[k]] += 1
        sufijo = f"#{cuenta[clave_de[k]]}" if cuenta[clave_de[k]] > 1 else ""
        if sufijo:
            avisos.append(f"{n['ident']} aparece más de una vez en el documento (páginas {n['ini']}-{n['fin']}); se conserva con el sufijo {sufijo}.")
        secciones.append(Seccion(
            id=clave_de[k] + sufijo, doc_id=doc_id, tipo_doc=tipo_doc, nivel=n["nivel"], identificador=n["ident"],
            titulo=_titulo(n), ruta=n["ruta"], texto_literal="\n".join(n["textos"]).strip(),
            pagina_inicio=n["ini"], pagina_fin=n["fin"], seccionado_incierto=k in inciertos, estrategia=estrategia,
            es_hoja=(n["nivel"] == "articulo") if articulos else k not in padres))
    return secciones


# --- Nivel 3: longitud ----------------------------------------------------------------------------------

def _por_longitud(bloques, doc_id, tipo_doc) -> list[Seccion]:
    """Grupos de ~SECCION_CHARS caracteres sin partir ningún párrafo (un párrafo más largo queda entero)."""
    grupos, actual, largo = [], [], 0
    for b in bloques:
        actual.append(b)
        largo += len(b["texto"])
        if largo >= settings.SECCION_CHARS:
            grupos.append(actual)
            actual, largo = [], 0
    if actual:
        grupos.append(actual)
    return [Seccion(
        id=f"{doc_id}:BLOQUE-{n}", doc_id=doc_id, tipo_doc=tipo_doc, nivel="bloque", identificador=f"Bloque {n}",
        titulo=None, ruta=[], texto_literal="\n".join(_texto(b) for b in g).strip(),
        pagina_inicio=g[0]["pagina"], pagina_fin=g[-1]["pagina"], seccionado_incierto=True, estrategia="longitud",
        es_hoja=True) for n, g in enumerate(grupos, 1)]
