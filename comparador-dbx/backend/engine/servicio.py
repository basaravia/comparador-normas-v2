"""Servicio de la app: encadena ingesta, extracción, índices, doble vía, juez, agregación y papel de trabajo (L6, docs/03 §Flujo y docs/11).

Sin HTTP: lo usan la API (`backend/api/`) y el notebook `06_e2e.ipynb`. Los modelos son siempre los reales del stage.
"""
import asyncio
import json
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable

from backend.api.schemas import (ArbolDocOut, ComparacionOut, DocumentoOut, ErrorNegocio, FilaVia1, FilaVia2, JobOut, Metadatos,
                                 NodoOut, ParVia2, SeccionOut)
from backend.config import RAIZ, Settings, settings
from backend.core.errors import ComparadorError
from backend.core.sesiones import Comparacion, Doc, Sesion, error_negocio
from backend.engine.agregacion import controles_sin_base, marca_articulo, naturaleza_articulo
from backend.engine.juez import juzgar_pares
from backend.engine.pares import construir_pares
from backend.extraction import docling_extractor
from backend.extraction.sectioner import parsear_bloques
from backend.ingest.classifier import ingerir
from backend.ingest.validation import nombre_seguro
from backend.llm.client import ModelClient
from backend.models import Documento, Seccion
from backend.output.conclusion import generar_borrador
from backend.output.workpaper import EntradaPapel, FilaPapel, SeccionExcluida, generar_papel
from backend.retrieval.exclusion import clasificar_secciones
from backend.retrieval.index import construir_indice
from backend.retrieval.tabla import titulo_visible

log = logging.getLogger(__name__)
SAMPLES = RAIZ / "samples"
_PROCESO = ThreadPoolExecutor(max_workers=1)        # procesamiento de documentos: Docling nunca en paralelo (CLAUDE.md regla 7)
_COMPARACION = ThreadPoolExecutor(max_workers=2)
_INGESTA = ThreadPoolExecutor(max_workers=4)        # clasificación de varios PDF a la vez (I/O al LLM)


class ComparacionError(ComparadorError):
    """Selección o límites de la comparación: el mensaje ya es de negocio."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo, self.mensaje_negocio = codigo, mensaje


# ───────────────────────── ingesta ─────────────────────────

def subir(sesion: Sesion, nombre: str, contenido: bytes, cliente: ModelClient) -> DocumentoOut:
    """Valida y clasifica un PDF. El tipo queda sugerido solo si el modelo está seguro; si no, el auditor elige."""
    with sesion.lock:
        if len(sesion.docs) >= settings.MAX_DOCS_SESION:
            raise ComparacionError("ERR-ING-004", f"Puedes cargar hasta {settings.MAX_DOCS_SESION} documentos por sesión. Reinicia la sesión para empezar de nuevo.")
        doc_id = sesion.nuevo_id("D")
    seguro = nombre_seguro(nombre)
    carpeta = sesion.dir / doc_id
    carpeta.mkdir(mode=0o700)
    ruta = carpeta / seguro
    ruta.write_bytes(contenido)
    r = ingerir(ruta, cliente)
    if not r["ok"]:
        out = DocumentoOut(id=doc_id, nombre=seguro, estado="error", error=ErrorNegocio(codigo=r["codigo"], mensaje=r["mensaje"]))
        doc = Doc(out=out)
    else:
        meta = Metadatos(**{k: str(v) for k, v in r["metadatos"].items() if k in Metadatos.model_fields})
        out = DocumentoOut(id=doc_id, nombre=seguro, paginas=r["paginas"], tipo=r["tipo"], tipo_sugerido=r["tipo"] is not None, metadatos=meta,
                           advertencias=[r["advertencia"]] if r.get("advertencia") else [])
        doc = Doc(out=out, ruta=ruta, sha256=r["sha256"])
    with sesion.lock:
        sesion.docs[doc_id] = doc
    return out


def subir_varios(sesion: Sesion, archivos: list[tuple[str, bytes]], cliente: ModelClient) -> list[DocumentoOut]:
    futuros = [_INGESTA.submit(subir, sesion, n, c, cliente) for n, c in archivos]
    return [f.result() for f in futuros]


# ───────────────────────── procesamiento ─────────────────────────

def _job(sesion: Sesion, tipo: str, **campos) -> JobOut:
    j = JobOut(job_id=uuid.uuid4().hex, tipo=tipo, estado="en_cola", **campos)
    with sesion.lock:
        sesion.jobs[j.job_id] = j
    return j


def _arbol_avisos(doc: Doc) -> list[str]:
    hojas = [s for s in doc.secciones if s.es_hoja]
    excl = [s for s in hojas if not doc.clasificacion.get(s.id, (True, ""))[0]]
    avisos = []
    if excl:
        avisos.append(f"Se excluyeron {len(excl)} secciones que no son cuerpo del documento (carátula, índice, anexos…). Puedes volver a marcarlas.")
    if hojas and 100 * len(excl) / len(hojas) > settings.EXCLUSION_MAX_PCT:
        avisos.append(f"Se excluyó el {100 * len(excl) / len(hojas):.0f} % de las hojas: confirma que sean carátulas, preámbulos o anexos.")
    return avisos


def _procesar_doc(doc: Doc, job: JobOut, base: float, peso: float) -> None:
    o = doc.out
    job.doc_actual = o.nombre

    def cb(hechos: int, total: int) -> None:
        job.progreso = round(base + peso * 0.8 * hechos / max(total, 1), 3)

    o.estado = "extrayendo"; job.documentos[o.id] = o.estado; job.etapa = "Extrayendo el texto"
    bloques = docling_extractor.extraer(doc.ruta, cb)
    o.estado = "seccionando"; job.documentos[o.id] = o.estado; job.etapa = "Detectando artículos y secciones"
    avisos: list[str] = []
    doc.secciones = parsear_bloques(bloques, o.id, o.tipo, pdf=doc.ruta, avisos=avisos)
    doc.clasificacion = clasificar_secciones(doc.secciones)
    doc.avisos_arbol = _arbol_avisos(doc)
    o.advertencias = [*o.advertencias, *avisos][:10]
    job.progreso = round(base + peso * 0.9, 3)


def asegurar_indices(sesion: Sesion, cliente: ModelClient, progreso: Callable[[int, int], None] | None = None) -> None:
    """Índices FAISS de normas y de manuales con TODAS las hojas de los documentos listos (la selección se filtra después con `Indice.filtrar`)."""
    with sesion.lock:
        listos = {i for i, d in sesion.docs.items() if d.out.estado in ("listo", "indexando")}
        if listos == sesion.indexados and sesion.indice_norma and sesion.indice_manual:
            return
        nombres = {i: d.out.nombre for i, d in sesion.docs.items()}
        por_tipo = {t: [s for i in sorted(listos) for s in sesion.docs[i].secciones if sesion.docs[i].out.tipo == t] for t in ("normativa", "manual_control")}
    if not por_tipo["normativa"] or not por_tipo["manual_control"]:
        raise ComparacionError("ERR-CMP-001", "Para comparar necesitas al menos una normativa y un manual de control ya procesados.")
    t0 = time.perf_counter()
    sesion.indice_norma = construir_indice(por_tipo["normativa"], cliente, nombres, progreso)
    sesion.indice_manual = construir_indice(por_tipo["manual_control"], cliente, nombres, progreso)
    sesion.indexados = listos
    log.info("Índices listos en %.0f s", time.perf_counter() - t0)


def procesar(sesion: Sesion, doc_ids: list[str], cliente: ModelClient) -> JobOut:
    """Encola extracción + seccionado + indexación de los documentos. Devuelve el job (poll con `GET /api/jobs/{id}`)."""
    with sesion.lock:
        docs = []
        for i in doc_ids:
            d = sesion.docs.get(i)
            if d is None or d.ruta is None:
                raise ComparacionError("ERR-DOC-001", "Uno de los documentos ya no está disponible. Vuelve a cargarlo.")
            if d.out.tipo is None:
                raise ComparacionError("ERR-DOC-002", f"Elige el tipo de «{d.out.nombre}» (normativa o manual de control) antes de procesar.")
            docs.append(d)
        job = _job(sesion, "procesamiento", documentos={d.out.id: "en_cola" for d in docs})
        for d in docs:
            d.out.estado = "en_cola"

    def correr() -> None:
        job.estado = "en_curso"
        t0, n = time.perf_counter(), len(docs)
        for k, d in enumerate(docs):
            try:
                _procesar_doc(d, job, k / (n + 1), 1 / (n + 1))
                d.out.estado = "listo"
            except Exception as e:                           # un documento con error no detiene a los demás
                err = error_negocio(e)
                d.out.estado, d.out.error = "error", err
                job.errores.append(ErrorNegocio(codigo=err.codigo, mensaje=f"«{d.out.nombre}»: {err.mensaje}"))
            job.documentos[d.out.id] = d.out.estado
        ok = [d for d in docs if d.out.estado == "listo"]
        with sesion.lock:
            tipos = {d.out.tipo for d in sesion.docs.values() if d.out.estado == "listo"}
        if ok and tipos == {"normativa", "manual_control"}:      # con un solo tipo todavía no hay qué indexar: se hará al comparar
            job.etapa, job.doc_actual = "Preparando la búsqueda de coincidencias", ""
            for d in ok:
                d.out.estado = job.documentos[d.out.id] = "indexando"
            try:
                with sesion.lock:
                    sesion.indexados, sesion.indice_norma, sesion.indice_manual = set(), None, None      # reconstruir con los documentos nuevos
                asegurar_indices(sesion, cliente, lambda h, t: setattr(job, "progreso", round((n + h / max(t, 1)) / (n + 1), 3)))
                nuevo = "listo"
            except Exception as e:
                err = error_negocio(e)
                job.errores.append(err)
                nuevo = "error"
            for d in ok:
                d.out.estado = job.documentos[d.out.id] = nuevo
                if nuevo == "error":
                    d.out.error = job.errores[-1]
        job.progreso = 1.0
        job.estado = "listo" if any(d.out.estado == "listo" for d in docs) else "error"
        job.etapa = "Documentos listos" if job.estado == "listo" else "No se pudo procesar ningún documento"
        log.info("Procesamiento: %d documentos en %.0f s", n, time.perf_counter() - t0)

    _PROCESO.submit(correr)
    return job


# ───────────────────────── árbol y selección ─────────────────────────

def _nodo(s: Seccion, doc: Doc) -> NodoOut:
    incluir, motivo = doc.clasificacion.get(s.id, (True, ""))
    texto = " ".join(s.texto_literal.split())
    return NodoOut(id=s.id, identificador=s.identificador, titulo=titulo_visible(s), preview=texto[:120] if s.es_hoja else "", hoja=s.es_hoja,
                   incierto=s.seccionado_incierto, excluida=s.es_hoja and not incluir, motivo=motivo, seleccionada=s.es_hoja and incluir,
                   pagina_inicio=s.pagina_inicio)


def arbol(sesion: Sesion, tipo: str) -> list[ArbolDocOut]:
    salida = []
    for d in sesion.docs.values():
        if d.out.tipo != tipo or d.out.estado != "listo":
            continue
        raiz: list[NodoOut] = []
        pila: list[tuple[int, NodoOut]] = []                  # (profundidad, nodo) de los ancestros abiertos
        for s in d.secciones:
            n, prof = _nodo(s, d), len(s.ruta)
            while pila and pila[-1][0] >= prof:
                pila.pop()
            (pila[-1][1].hijos if pila else raiz).append(n)
            pila.append((prof, n))
        salida.append(ArbolDocOut(doc_id=d.out.id, nombre=d.out.nombre, nodos=raiz, avisos=d.avisos_arbol))
    return salida


def seccion(sesion: Sesion, sid: str) -> SeccionOut:
    for d in sesion.docs.values():
        for s in d.secciones:
            if s.id == sid:
                return SeccionOut(id=s.id, doc_nombre=d.out.nombre, identificador=s.identificador, titulo=titulo_visible(s), ruta=s.ruta,
                                  texto=s.texto_literal, pagina_inicio=s.pagina_inicio, pagina_fin=s.pagina_fin, incierto=s.seccionado_incierto)
    raise ComparacionError("ERR-SEC-404", "No encontramos esa sección. Puede que la sesión se haya reiniciado.")


# ───────────────────────── comparación ─────────────────────────

def _seleccion(sesion: Sesion, articulo_ids: list[str], seccion_ids: list[str]) -> tuple[dict[str, Seccion], dict[str, Seccion], list[Doc]]:
    todas = sesion.secciones()
    docs = {s.id: d for d in sesion.docs.values() for s in d.secciones}
    try:
        arts = {i: todas[i] for i in dict.fromkeys(articulo_ids)}
        secs = {i: todas[i] for i in dict.fromkeys(seccion_ids)}
    except KeyError:
        raise ComparacionError("ERR-CMP-002", "Una de las secciones elegidas ya no está disponible. Vuelve a seleccionar.")
    if not arts or not secs:
        raise ComparacionError("ERR-CMP-002", "Elige al menos un artículo de una normativa y una sección de un manual.")
    if any(s.tipo_doc != "normativa" or not s.es_hoja for s in arts.values()) or any(s.tipo_doc != "manual_control" or not s.es_hoja for s in secs.values()):
        raise ComparacionError("ERR-CMP-002", "La selección no es válida: los artículos deben ser de normativas y las secciones de manuales.")
    manuales = {docs[i].out.id: docs[i] for i in secs}
    if len(manuales) > 1:
        raise ComparacionError("ERR-CMP-003", "Por ahora el papel de trabajo compara un manual a la vez. Selecciona secciones de un solo manual.")
    return arts, secs, [*manuales.values()]


def comparar(sesion: Sesion, articulo_ids: list[str], seccion_ids: list[str], cliente: ModelClient) -> JobOut:
    """Valida la selección y encola la comparación. Devuelve el job (con `comparacion_id`)."""
    arts, secs, _ = _seleccion(sesion, articulo_ids, seccion_ids)
    cid = uuid.uuid4().hex
    comp = Comparacion(out=ComparacionOut(id=cid, estado="en_curso"))
    job = _job(sesion, "comparacion", comparacion_id=cid, etapa="En cola")
    with sesion.lock:
        sesion.comparaciones[cid] = comp

    def correr() -> None:
        job.estado = "en_curso"
        t0 = time.perf_counter()
        try:
            _ejecutar(sesion, comp, arts, secs, job, cliente)
            comp.out.estado, job.estado, job.progreso, job.etapa = "listo", "listo", 1.0, "Comparación lista"
        except Exception as e:
            err = error_negocio(e)
            comp.out.estado, job.estado = "error", "error"
            job.errores.append(err)
            job.mensaje = err.mensaje
        log.info("Comparación: %d artículos x %d secciones en %.0f s", len(arts), len(secs), time.perf_counter() - t0)

    _COMPARACION.submit(correr)
    return job


def _comentario(par) -> tuple[str, list[str]]:
    v = par.veredicto if par else None
    return (v.comentario, v.elementos_faltantes) if v else ("", [])


def _ejecutar(sesion: Sesion, comp: Comparacion, arts: dict[str, Seccion], secs: dict[str, Seccion], job: JobOut, cliente: ModelClient) -> None:
    job.etapa, job.progreso = "Preparando la búsqueda de coincidencias", 0.02
    asegurar_indices(sesion, cliente, lambda h, t: setattr(job, "progreso", round(0.02 + 0.2 * h / max(t, 1), 3)))
    job.etapa, job.progreso = "Buscando coincidencias en las dos vías", 0.25
    pares, stats = construir_pares(sesion.indice_norma, sesion.indice_manual, set(arts), set(secs))
    if len(pares) > settings.MAX_PARES:
        raise ComparacionError("ERR-CMP-004", f"La selección genera {len(pares)} comparaciones y el máximo es {settings.MAX_PARES}. Selecciona menos artículos o secciones.")
    todas = sesion.secciones()
    nombres = {i: d.out.nombre for i, d in sesion.docs.items()}
    job.etapa = "Juzgando cada par artículo–sección"

    def cb(h: int, t: int) -> None:
        job.progreso, job.mensaje = round(0.3 + 0.55 * h / max(t, 1), 3), f"Par {h} de {t}"

    asyncio.run(juzgar_pares(pares, todas, nombres, cliente, progreso=cb))
    job.mensaje, job.etapa, job.progreso = "", "Calculando marcas y armando el papel", 0.86

    por_art: dict[str, list] = {}
    for p in pares:
        por_art.setdefault(p.articulo_id, []).append(p)
    filas, docs_norma = [], {}
    for aid, art in arts.items():
        ps = por_art.get(aid, [])
        marca, respaldo = marca_articulo(ps)
        par = respaldo[0] if respaldo else None
        if not par and marca in ("X", "P"):                       # el comentario sale del par que decidió la naturaleza
            par = max((p for p in ps if p.veredicto and p.veredicto.naturaleza_articulo == naturaleza_articulo(ps)),
                      key=lambda p: p.veredicto.confianza, default=None)
        coment, faltantes = _comentario(par)
        filas.append(FilaPapel(articulo=art, marca=marca, par=par if marca in ("A", "L", "R") else None,
                               respaldo=todas[par.seccion_id] if par and marca in ("A", "L", "R") else None, comentario=coment, elementos_faltantes=faltantes))
        docs_norma[art.doc_id] = sesion.docs[art.doc_id]
    sin_base = controles_sin_base(list(secs), pares)
    doc_manual = sesion.docs[next(iter(secs.values())).doc_id]
    excluidas = [SeccionExcluida(documento=doc_manual.out.nombre, identificador=s.identificador, titulo=titulo_visible(s), ruta=" › ".join(s.ruta),
                                 paginas=str(s.pagina_inicio) if s.pagina_fin == s.pagina_inicio else f"{s.pagina_inicio}-{s.pagina_fin}", motivo=doc_manual.clasificacion[s.id][1])
                 for s in doc_manual.secciones if s.es_hoja and s.id not in secs and not doc_manual.clasificacion.get(s.id, (True, ""))[0]]

    def documento(d: Doc) -> Documento:
        return Documento(id=d.out.id, nombre=d.out.nombre, tipo_doc=d.out.tipo, sha256=d.sha256, paginas=d.out.paginas, metadatos=d.out.metadatos.model_dump(exclude_none=True))

    entrada = EntradaPapel(manual=documento(doc_manual), normativas=[documento(d) for d in docs_norma.values()], filas=filas, pares=pares,
                           secciones={i: todas[i] for i in {*arts, *secs}}, controles_sin_base=[todas[i] for i in sin_base], excluidas=excluidas,
                           fecha_ejecucion=date.today())
    job.etapa, job.progreso = "Redactando el borrador de conclusión", 0.92
    try:
        entrada.conclusion = generar_borrador(entrada, cliente)
    except ComparadorError as e:                                  # el borrador es opcional: el auditor lo escribe
        log.warning("Sin borrador de conclusión: %s", e.codigo)
        comp.out.avisos.append("No pudimos redactar el borrador de la conclusión; escríbelo tú antes de descargar el papel.")
    comp.entrada = entrada
    comp.out = _resultado(comp.out.id, entrada, secs, pares, comp.out.avisos)


def _resultado(cid: str, e: EntradaPapel, secs: dict[str, Seccion], pares: list, avisos: list[str]) -> ComparacionOut:
    nombres = {d.id: d.nombre for d in [e.manual, *e.normativas]}
    via1 = []
    for f in e.filas:
        v = f.par.veredicto if f.par else None
        mias = [p for p in e.pares if p.articulo_id == f.articulo.id]
        via1.append(FilaVia1(articulo_id=f.articulo.id, documento=nombres.get(f.articulo.doc_id, ""), identificador=f.articulo.identificador,
                             ruta=" › ".join(f.articulo.ruta), texto_articulo=f.articulo.texto_literal, marca=f.marca, comentario=f.comentario,
                             cita_norma=(v.cita_norma if v else ""), cita_manual=(v.cita_manual or "" if v else ""),
                             seccion_respaldo_id=f.respaldo.id if f.respaldo else None,
                             seccion_respaldo=f"{f.respaldo.identificador} · {titulo_visible(f.respaldo)}" if f.respaldo else "",
                             confianza=v.confianza if v else None,
                             requiere_revision=(f.par.requiere_revision if f.par else False) or not any(p.veredicto for p in mias),
                             elementos_faltantes=f.elementos_faltantes))
    sin = {s.id for s in e.controles_sin_base}
    via2 = []
    for sid, s in secs.items():
        ps = [ParVia2(articulo_id=p.articulo_id, identificador=e.secciones[p.articulo_id].identificador, cobertura=p.veredicto.cobertura)
              for p in e.pares if p.seccion_id == sid and p.veredicto]
        via2.append(FilaVia2(seccion_id=sid, identificador=s.identificador, titulo=titulo_visible(s), sin_base=sid in sin, pares=ps))
    conteos = {m: sum(1 for f in e.filas if f.marca == m) for m in "ALRXP"}
    return ComparacionOut(id=cid, estado="listo", conteos=conteos, via1=via1, via2=via2, conclusion=e.conclusion, conclusion_editada=e.conclusion_editada,
                          pares_juzgados=sum(1 for p in pares if p.veredicto), pares_a_revision=sum(1 for p in pares if p.requiere_revision), avisos=avisos)


def guardar_conclusion(comp: Comparacion, texto: str) -> ComparacionOut:
    comp.entrada.conclusion, comp.entrada.conclusion_editada = texto.strip(), True
    comp.out.conclusion, comp.out.conclusion_editada = texto.strip(), True
    return comp.out


def excel(sesion: Sesion, comp: Comparacion) -> Path:
    destino = sesion.dir / f"papel_{comp.out.id[:8]}.xlsx"
    generar_papel(comp.entrada, destino)
    return destino


# ───────────────────────── ejemplos precargados (docs/13 D2) ─────────────────────────

def cargar_ejemplo(sesion: Sesion) -> list[DocumentoOut]:
    """Carga `samples/ejemplo.json` (secciones ya extraídas): sin Docling. Los índices se arman al comparar."""
    archivo = SAMPLES / "ejemplo.json"
    if not archivo.exists():
        raise ComparacionError("ERR-SMP-001", "El ejemplo no está disponible en esta instalación.")
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    salida = []
    for d in datos["documentos"]:
        with sesion.lock:
            doc_id = sesion.nuevo_id("D")
        viejo = d["doc_id"]
        secs = [Seccion.model_validate({**s, "doc_id": doc_id, "id": doc_id + s["id"][len(viejo):]}) for s in d["secciones"]]
        out = DocumentoOut(id=doc_id, nombre=d["nombre"], paginas=d["paginas"], tipo=d["tipo"], metadatos=Metadatos(**d.get("metadatos", {})), estado="listo",
                           advertencias=["Documento de ejemplo."])
        doc = Doc(out=out, secciones=secs, sha256=d.get("sha256", ""))
        doc.clasificacion = clasificar_secciones(secs)
        doc.avisos_arbol = _arbol_avisos(doc)
        with sesion.lock:
            sesion.docs[doc_id] = doc
        salida.append(out)
    return salida
