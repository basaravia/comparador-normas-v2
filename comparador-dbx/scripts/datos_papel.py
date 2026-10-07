"""Datos de ENTRADA para probar el papel de trabajo (L5), construidos de forma DETERMINISTA.

NO son una simulación del modelo: los textos son reales (PDF de normas y MOCK de manuales,
leídos con PyMuPDF) y `Seccion`, `Par` y `Veredicto` son los modelos reales de
`backend/models/schemas.py`. Lo que L2 (seccionado), L3 (recuperación) y L4 (juez y agregación)
producirán más adelante aquí lo fija un guion de prueba: la marca de cada artículo sale del
guion, no de un cálculo, y los scores son solapamientos de palabras, no embeddings.
"""
import hashlib
import re
from pathlib import Path

import pymupdf

from backend.models.schemas import Documento, Par, Seccion, Veredicto
from backend.output.workpaper import EntradaPapel, FilaPapel

GUION = ["A", "L", "R", "A", "P", "L", "R", "A", "X", "A"]     # marca por artículo (cíclico)
_NIVELES = {"LIBRO": "libro", "TÍTULO": "titulo", "TITULO": "titulo", "CAPÍTULO": "capitulo",
            "CAPITULO": "capitulo", "SECCIÓN": "seccion", "SECCION": "seccion"}
_ENCABEZADO = re.compile(r"^(LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+([IVXLC\d]+)\s*(?:\.?-.*)?$", re.I)
_ARTICULO = re.compile(r"^ART[IÍ]CULO\s+(\d+)\s*\.?-", re.I)
_CAP_MANUAL = re.compile(r"^([IVXLC]+)\.\s{2,}(\S.*)$")
_SUB_MANUAL = re.compile(r"^(\d+\.\d+)\s{2,}(\S.*)$")


def documento(pdf: Path, doc_id: str, tipo_doc: str) -> Documento:
    d = pymupdf.open(pdf)
    return Documento(id=doc_id, nombre=pdf.name, tipo_doc=tipo_doc, paginas=len(d),
                     sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())


def _lineas(pdf: Path):
    """(página, línea limpia) de todo el PDF, sin líneas vacías ni números de página sueltos."""
    for n, pagina in enumerate(pymupdf.open(pdf), start=1):
        for linea in pagina.get_text().splitlines():
            if linea.strip() and not linea.strip().isdigit():
                yield n, linea.rstrip()


def texto_fuente(pdf: Path) -> str:
    """Texto del PDF con espacios normalizados: contra él se verifican los textos literales."""
    return " ".join(" ".join(l.split()) for _, l in _lineas(pdf))


def _seccion(doc_id, tipo, ident, titulo, ruta, cuerpo, pag_ini, pag_fin) -> Seccion:
    return Seccion(id=f"{doc_id}:{ident}", doc_id=doc_id, tipo_doc=tipo,
                   nivel="articulo" if tipo == "normativa" else "numeral", identificador=ident,
                   titulo=titulo, ruta=ruta, texto_literal=" ".join(" ".join(c.split()) for c in cuerpo),
                   pagina_inicio=pag_ini, pagina_fin=pag_fin, seccionado_incierto=False,
                   estrategia="patron", es_hoja=True)


def cargar_norma(pdf: Path, doc_id: str) -> list[Seccion]:
    """Artículos de una norma: ruta = libro/título/capítulo/sección vigentes; texto literal."""
    orden = ["libro", "titulo", "capitulo", "seccion"]
    out, ruta, actual, repetidos = [], {}, None, {}     # actual = [ident, ruta, cuerpo, pág_ini, pág_fin]

    def cerrar():
        if actual and len(actual[2]) > 1:
            out.append(_seccion(doc_id, "normativa", actual[0], None, actual[1], actual[2], actual[3], actual[4]))

    for pag, linea in _lineas(pdf):
        txt = linea.strip()
        h, a = _ENCABEZADO.match(txt), _ARTICULO.match(txt)
        if h or a:
            cerrar()
            actual = None
        if h:
            nivel = _NIVELES[h.group(1).upper()]
            for k in orden[orden.index(nivel):]:        # un nivel nuevo cierra los inferiores
                ruta.pop(k, None)
            ruta[nivel] = f"{h.group(1).capitalize()} {h.group(2).upper()}"
        elif a:
            n = a.group(1)
            repetidos[n] = repetidos.get(n, 0) + 1
            ident = f"Art. {n}" + (f" (#{repetidos[n]})" if repetidos[n] > 1 else "")
            actual = [ident, list(ruta.values()), [txt], pag, pag]
        elif actual:
            actual[2].append(txt)
            actual[4] = pag
    cerrar()
    return out


def cargar_manual(pdf: Path, doc_id: str) -> list[Seccion]:
    """Secciones de un manual MOCK: capítulos romanos ('IV.') y subsecciones ('4.1'). Omite el índice."""
    out, capitulo, actual, en_indice = [], None, None, False   # actual = [ident, titulo, ruta, cuerpo, pág_ini, pág_fin]

    def cerrar():
        if actual and actual[3]:
            out.append(_seccion(doc_id, "manual_control", actual[0], actual[1], actual[2], actual[3], actual[4], actual[5]))

    for pag, linea in _lineas(pdf):
        txt = linea.strip()
        if txt.upper().startswith("ÍNDICE"):
            en_indice = True
            continue
        cap, sub = _CAP_MANUAL.match(txt), _SUB_MANUAL.match(txt)
        if en_indice:
            if not (cap and cap.group(1) == "I" and "INTRODUCCI" in cap.group(2).upper()):
                continue                                  # sigue dentro del índice
            en_indice = False
        if cap or sub:
            cerrar()
            m = cap or sub
            titulo = " ".join(m.group(2).split())
            if cap:
                capitulo = f"{m.group(1)}. {titulo}"
            actual = [m.group(1), titulo, [] if cap else [capitulo], [], pag, pag]
        elif actual:
            actual[3].append(txt)
            actual[5] = pag
    cerrar()
    return out


# ---------------------------------------------------------------------------------------------
def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r"\w+", texto.lower()) if len(w) > 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    return round(len(a & b) / len(a | b), 4) if a | b else 0.0


def _frase(texto: str) -> str:
    """Primera frase del texto (subcadena literal), de hasta 200 caracteres."""
    return texto[:200].split(". ")[0].strip()


def _veredicto(marca, k, art, sec) -> Veredicto:
    """Veredicto del guion para el candidato k (0 = el elegido) del artículo."""
    cobertura = {"A": ["total", "parcial", "nula"], "L": ["parcial", "nula", "nula"]}.get(marca, ["nula"] * 3)[k]
    naturaleza = {"P": "informativo", "X": "no_aplica_entidad"}.get(marca, "obligacion")
    faltan = [] if cobertura == "total" or naturaleza != "obligacion" else (
        [f"Plazo o responsable de lo exigido en {art.identificador}"] if cobertura == "parcial" else
        [f"Procedimiento equivalente a {art.identificador}"])
    comentario = {
        "total": f"La sección {sec.identificador} del manual cubre la obligación de {art.identificador}.",
        "parcial": f"La sección {sec.identificador} cubre solo en parte {art.identificador}.",
        "nula": f"La sección {sec.identificador} no contiene lo que exige {art.identificador}.",
    }[cobertura]
    if naturaleza == "informativo":
        comentario = f"{art.identificador} es informativo: no impone una obligación."
    if naturaleza == "no_aplica_entidad":
        comentario = f"{art.identificador} no aplica a la entidad evaluada."
    return Veredicto(naturaleza_articulo=naturaleza, cobertura=cobertura, cita_norma=_frase(art.texto_literal),
                     cita_manual=_frase(sec.texto_literal) if cobertura != "nula" else None,
                     comentario=comentario, elementos_faltantes=faltan, confianza=[0.92, 0.7, 0.6][k])


def armar_entrada(normas: list[tuple[Documento, list[Seccion]]], manual: tuple[Documento, list[Seccion]],
                  max_articulos: int | None = None, conclusion: str = "") -> EntradaPapel:
    """EntradaPapel con textos reales y el guion `GUION`. 3 candidatos por artículo (top-3 por solapamiento)."""
    doc_manual, secs_manual = manual
    palabras_m = {s.id: _palabras(s.texto_literal) for s in secs_manual}
    articulos = [a for _, secs in normas for a in secs][:max_articulos]
    secciones = {s.id: s for s in secs_manual} | {a.id: a for a in articulos}
    filas, pares, con_cobertura = [], [], set()
    for i, art in enumerate(articulos):
        marca = GUION[i % len(GUION)]
        pa = _palabras(art.texto_literal)
        ranking = sorted(secs_manual, key=lambda s: (-_jaccard(pa, palabras_m[s.id]), s.id))[:3]
        del_articulo = []
        for k, sec in enumerate(ranking):
            score = _jaccard(pa, palabras_m[sec.id])
            v = _veredicto(marca, k, art, sec)
            p = Par(id=f"{art.id}|{sec.id}", articulo_id=art.id, seccion_id=sec.id,
                    origen={"v1", "v2"} if k == 0 else ({"v1"} if k == 1 else {"v2"}),
                    score_v1=score if k < 2 else None, rank_v1=k + 1 if k < 2 else None,
                    score_v2=round(score * 0.97, 4) if k != 1 else None, rank_v2=k + 1 if k != 1 else None,
                    veredicto=v, cita_norma_verificada=True, cita_manual_verificada=True,
                    requiere_revision=(i % 7 == 6 and k == 0))
            if p.requiere_revision:                       # caso con aviso: cita no verificada
                p.cita_manual_verificada = v.cita_manual is None
            del_articulo.append(p)
            if v.cobertura != "nula" and v.naturaleza_articulo == "obligacion":
                con_cobertura.add(sec.id)
        pares += del_articulo
        elegido = del_articulo[0]
        con_respaldo = marca not in ("P", "X")
        filas.append(FilaPapel(articulo=art, marca=marca, par=elegido if con_respaldo else None,
                               respaldo=secciones[elegido.seccion_id] if con_respaldo else None,
                               comentario=elegido.veredicto.comentario,
                               elementos_faltantes=elegido.veredicto.elementos_faltantes))
    return EntradaPapel(manual=doc_manual, normativas=[d for d, _ in normas], filas=filas, pares=pares,
                        secciones=secciones, conclusion=conclusion,
                        controles_sin_base=[s for s in secs_manual if s.id not in con_cobertura])


def hostilizar(entrada: EntradaPapel, prefijo: str) -> EntradaPapel:
    """Copia de la entrada con TODO campo de texto empezando por `prefijo` (=, +, -, @, tab, CR)."""
    h = lambda t: prefijo + (t or "")  # noqa: E731

    def sec(s):
        return s.model_copy(update={"identificador": h(s.identificador), "titulo": h(s.titulo),
                                    "ruta": [h(r) for r in s.ruta], "texto_literal": h(s.texto_literal)})

    secciones = {k: sec(v) for k, v in entrada.secciones.items()}

    def veredicto(v):
        return v and v.model_copy(update={"comentario": h(v.comentario), "cita_norma": h(v.cita_norma),
                                          "cita_manual": h(v.cita_manual) if v.cita_manual else None,
                                          "elementos_faltantes": [h(e) for e in v.elementos_faltantes]})

    def par(p):
        return p and p.model_copy(update={"veredicto": veredicto(p.veredicto)})

    filas = [f.model_copy(update={"articulo": secciones[f.articulo.id], "par": par(f.par),
                                  "respaldo": secciones[f.respaldo.id] if f.respaldo else None,
                                  "comentario": h(f.comentario),
                                  "elementos_faltantes": [h(e) for e in f.elementos_faltantes]})
             for f in entrada.filas]
    docs = lambda d: d.model_copy(update={"nombre": h(d.nombre)})  # noqa: E731
    return entrada.model_copy(update={
        "manual": docs(entrada.manual), "normativas": [docs(d) for d in entrada.normativas], "filas": filas,
        "pares": [par(p) for p in entrada.pares], "secciones": secciones,
        "controles_sin_base": [sec(s) for s in entrada.controles_sin_base],
        "conclusion": h(entrada.conclusion), "conclusion_editada": True})
