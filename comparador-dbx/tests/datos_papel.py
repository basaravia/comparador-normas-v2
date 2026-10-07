"""Datos de entrada del papel de trabajo, construidos a mano (sin modelo ni L4).

Las marcas A/L/R/X/P vienen de un GUION: son las que L4 (`aggregate`) calculará cuando exista.
Aquí solo son entrada de código determinista.
"""
from backend.models.schemas import Documento, Par, Seccion, Veredicto
from backend.output.workpaper import EntradaPapel, FilaPapel


def seccion(id_, doc_id, ident, pag=1, tipo="normativa", ruta=None, texto="Texto literal.", titulo=None,
            incierto=False, pag_fin=None):
    return Seccion(id=id_, doc_id=doc_id, tipo_doc=tipo, nivel="articulo", identificador=ident, titulo=titulo,
                   ruta=ruta if ruta is not None else ["Libro I", "Título II", "Capítulo III"],
                   texto_literal=texto, pagina_inicio=pag, pagina_fin=pag_fin or pag,
                   seccionado_incierto=incierto, estrategia="patron", es_hoja=True)


def veredicto(nat="obligacion", cob="total", conf=0.9, comentario="Comentario del juez.", cita_manual="cita del manual"):
    return Veredicto(naturaleza_articulo=nat, cobertura=cob, cita_norma="cita norma",
                     cita_manual=None if cob == "nula" else cita_manual, comentario=comentario,
                     confianza=conf)


def par(id_, art, sec, v=None, s1=None, r1=None, s2=None, r2=None, origen=("v1",), cn=True, cm=True, rev=False):
    return Par(id=id_, articulo_id=art, seccion_id=sec, origen=set(origen), score_v1=s1, rank_v1=r1, score_v2=s2,
               rank_v2=r2, veredicto=v, cita_norma_verificada=cn, cita_manual_verificada=cm, requiere_revision=rev)


def entrada(**cambios) -> EntradaPapel:
    """6 artículos (A, L, R, X, P en N1 y A en N2) y 12 pares; 2 controles sin base."""
    n1 = Documento(id="N1", nombre="Norma Uno.pdf", tipo_doc="normativa", sha256="a" * 64, paginas=10)
    n2 = Documento(id="N2", nombre="Norma Dos.pdf", tipo_doc="normativa", sha256="b" * 64, paginas=5)
    m1 = Documento(id="M1", nombre="Manual Interno.pdf", tipo_doc="manual_control", sha256="c" * 64, paginas=20)
    a1 = seccion("N1-a1", "N1", "Art. 1", pag=1)
    a2 = seccion("N1-a2", "N1", "Art. 2", pag=2, titulo="Reporte", incierto=True)
    a3 = seccion("N1-a3", "N1", "Art. 3", pag=3)
    a4 = seccion("N1-a4", "N1", "Art. 4", pag=4)
    a5 = seccion("N1-a5", "N1", "Art. 5", pag=5, pag_fin=6)
    b1 = seccion("N2-b1", "N2", "Art. 9", pag=1, ruta=["Libro IX"])
    s1 = seccion("M1-s1", "M1", "3.1", pag=7, tipo="manual_control", ruta=["Capítulo 3"], titulo="Conciliación")
    s2 = seccion("M1-s2", "M1", "3.2", pag=8, tipo="manual_control", ruta=["Capítulo 3"], pag_fin=9)
    s3 = seccion("M1-s3", "M1", "4.1", pag=10, tipo="manual_control", ruta=["Capítulo 4"])
    c1 = seccion("M1-c1", "M1", "9.1", pag=15, tipo="manual_control", ruta=["Capítulo 9"], texto="Control huérfano 1")
    c2 = seccion("M1-c2", "M1", "9.2", pag=16, tipo="manual_control", ruta=["Capítulo 9"], texto="Control huérfano 2",
                 pag_fin=17)
    secs = {s.id: s for s in [a1, a2, a3, a4, a5, b1, s1, s2, s3, c1, c2]}
    pares = [
        # a1 = A: respaldo p1 (total .9); p2 parcial; p3 total pero menos confianza; p4 sin veredicto
        par("P1", "N1-a1", "M1-s1", veredicto(), s1=0.81, r1=1, s2=0.84, r2=2, origen=("v1", "v2")),
        par("P2", "N1-a1", "M1-s2", veredicto(cob="parcial", conf=0.95), s1=0.7, r1=2),
        par("P3", "N1-a1", "M1-s3", veredicto(conf=0.5), s2=0.6, r2=5, origen=("v2",)),
        par("P4", "N1-a1", "M1-c1", None),
        # a2 = L: respaldo p5 (parcial .7); p6 parcial menos confianza; p7 nula
        par("P5", "N1-a2", "M1-s2", veredicto(cob="parcial", conf=0.7), s1=0.66, r1=1, cm=False),
        par("P6", "N1-a2", "M1-s1", veredicto(cob="parcial", conf=0.4), s1=0.5, r1=3, rev=True),
        par("P7", "N1-a2", "M1-s3", veredicto(cob="nula", conf=0.8), s1=0.4, r1=4),
        # a3 = R: todos nula
        par("P8", "N1-a3", "M1-s1", veredicto(cob="nula", conf=0.9), s1=0.45, r1=1, cn=False),
        # a4 = X ; a5 = P
        par("P9", "N1-a4", "M1-s1", veredicto(nat="no_aplica_entidad", cob="nula"), s1=0.3, r1=1),
        par("P10", "N1-a5", "M1-s1", veredicto(nat="informativo", cob="nula"), s1=0.3, r1=1),
        # b1 = A (solo vía 2 del motor: sin rank_v1)
        par("P11", "N2-b1", "M1-s3", veredicto(conf=0.85), s2=0.77, r2=1, origen=("v2",)),
    ]
    filas = [
        FilaPapel(articulo=b1, marca="A", par=pares[10], respaldo=s3, comentario="Cumple b1."),   # fuera de orden a propósito
        FilaPapel(articulo=a5, marca="P"),
        FilaPapel(articulo=a3, marca="R", par=pares[7], respaldo=s1, comentario="Brecha.",
                  elementos_faltantes=["plazo", "responsable"]),
        FilaPapel(articulo=a1, marca="A", par=pares[0], respaldo=s1, comentario="Cumple a1."),
        FilaPapel(articulo=a4, marca="X", par=pares[8]),
        FilaPapel(articulo=a2, marca="L", par=pares[4], respaldo=s2, comentario="Parcial.",
                  elementos_faltantes=["periodicidad"]),
    ]
    base = dict(manual=m1, normativas=[n1, n2], filas=filas, pares=pares, secciones=secs,
                controles_sin_base=[c1, c2], conclusion="Texto de conclusión.")
    base.update(cambios)
    return EntradaPapel(**base)
