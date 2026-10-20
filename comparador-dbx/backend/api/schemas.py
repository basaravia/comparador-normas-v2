"""Contrato JSON de la API (docs/11). Lo que ve el frontend; nunca texto técnico ni trazas."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Tipo = Literal["normativa", "manual_control"]
Marca = Literal["A", "L", "R", "X", "P"]


class ErrorNegocio(BaseModel):
    codigo: str
    mensaje: str


class Metadatos(BaseModel):
    entidad_emisora: Optional[str] = None
    titulo_oficial: Optional[str] = None
    libro: Optional[str] = None
    titulo: Optional[str] = None
    capitulo: Optional[str] = None
    numero_norma: Optional[str] = None
    fecha_vigencia: Optional[str] = None


class DocumentoOut(BaseModel):
    id: str
    nombre: str
    paginas: int = 0
    tipo: Optional[Tipo] = None            # lo sugerido por el sistema o lo elegido por el auditor; None = el auditor debe elegir
    tipo_sugerido: bool = False            # True mientras el tipo viene del sistema (indicador "sugerido")
    metadatos: Metadatos = Metadatos()
    estado: Literal["cargado", "en_cola", "extrayendo", "seccionando", "indexando", "listo", "error"] = "cargado"
    advertencias: list[str] = []
    error: Optional[ErrorNegocio] = None


class DocumentoPatch(BaseModel):
    tipo: Optional[Tipo] = None
    metadatos: Optional[Metadatos] = None


class ProcesarIn(BaseModel):
    doc_ids: list[str] = Field(max_length=100)


class ProgresoDoc(BaseModel):
    """Avance real de la lectura de un documento (docs/ux/mejora-experiencia-v1.md §d). `lote`: páginas [ini, fin] de la tanda que Docling está leyendo."""
    etapa: str = ""
    paginas_hechas: int = 0
    paginas_total: int = 0
    lote: list[int] = []


class IndiceDoc(BaseModel):
    """Lo que se encontró al armar el índice del documento (conteos reales del seccionado)."""
    secciones: int = 0
    articulos: int = 0              # hojas que se comparan
    excluidas: int = 0
    por_revisar: int = 0            # secciones detectadas por longitud


class FragmentoOut(BaseModel):
    identificador: str
    documento: str
    pagina: int = 0
    preview: str = Field(default="", max_length=200)      # texto LITERAL del documento (≤160 letras)


class ParEnCurso(BaseModel):
    par_id: str
    articulo: FragmentoOut
    seccion: FragmentoOut
    score: float = 0.0
    origen: list[str] = []
    desde_ts: float = 0.0


class VeredictoVivo(BaseModel):
    """Un par ya juzgado, para la vista en vivo. `comentario` es salida del modelo: el frontend lo muestra como texto plano y bajo demanda."""
    seq: int
    par_id: str
    articulo: str
    seccion: str
    cobertura: Literal["total", "parcial", "nula", "sin_veredicto"]
    naturaleza: str = ""
    confianza: float = 0.0
    cita_norma_ok: bool = False
    cita_manual_ok: bool = False
    requiere_revision: bool = False
    comentario: str = Field(default="", max_length=300)


class EsperaLimite(BaseModel):
    """El proveedor del modelo pidió esperar (límite de tasa, 429)."""
    activa: bool = False
    hasta_ts: float = 0.0
    intento: int = 0
    max: int = 0


class JobOut(BaseModel):
    job_id: str
    tipo: Literal["procesamiento", "comparacion"]
    estado: Literal["en_cola", "en_curso", "listo", "error", "cancelado"]
    etapa: str = ""                         # texto de negocio: "Extrayendo el texto", "Juzgando pares"…
    doc_actual: str = ""
    progreso: float = 0.0                   # 0-1
    mensaje: str = ""
    errores: list[ErrorNegocio] = []
    documentos: dict[str, str] = {}         # doc_id -> estado (procesamiento)
    comparacion_id: Optional[str] = None    # comparación (cuando tipo == "comparacion")
    # Progreso detallado (todo real y en memoria; sin llamadas extra al LLM ni a Docling)
    ahora_ts: float = 0.0                                      # reloj del servidor al responder: el frontend calcula tiempos sin depender de su propio reloj
    inicio_ts: float = 0.0
    ultimo_evento_ts: float = 0.0
    cancelable: bool = False
    por_documento: dict[str, ProgresoDoc] = {}                 # procesamiento
    indice: dict[str, IndiceDoc] = {}                          # procesamiento: al terminar el seccionado de cada documento
    indexacion_hechos: int = 0                                 # procesamiento: lotes de embeddings
    indexacion_total: int = 0
    fase: str = ""                                             # comparación: recuperando / juzgando / armando
    pares_total: int = 0
    pares_hechos: int = 0
    pares_en_curso: list[ParEnCurso] = []
    ultimos_veredictos: list[VeredictoVivo] = []               # anillo de los últimos 20
    conteo_cobertura: dict[str, int] = {}                      # provisional: total / parcial / nula / sin_veredicto
    a_revision: int = 0
    espera_limite: EsperaLimite = EsperaLimite()


class NodoOut(BaseModel):
    id: str
    identificador: str
    titulo: str = ""
    preview: str = ""                       # primeras ~120 letras del texto (solo hojas)
    hoja: bool = False
    incierto: bool = False                  # seccionado por longitud: "revísala"
    excluida: bool = False                  # no comparable (carátula, índice, anexo…)
    motivo: str = ""                        # por qué se excluyó
    seleccionada: bool = True
    pagina_inicio: int = 0
    hijos: list["NodoOut"] = []


class ArbolDocOut(BaseModel):
    doc_id: str
    nombre: str
    nodos: list[NodoOut]
    avisos: list[str] = []                  # "Se excluyeron 14 secciones que no son cuerpo del manual"


class SeccionOut(BaseModel):
    id: str
    doc_nombre: str
    identificador: str
    titulo: str = ""
    ruta: list[str] = []
    texto: str
    pagina_inicio: int
    pagina_fin: int
    incierto: bool = False


class ComparacionIn(BaseModel):
    articulo_ids: list[str] = Field(max_length=2000)
    seccion_ids: list[str] = Field(max_length=2000)


class FilaVia1(BaseModel):
    articulo_id: str
    documento: str
    identificador: str
    ruta: str = ""
    texto_articulo: str
    marca: Marca
    comentario: str = ""
    cita_norma: str = ""
    cita_manual: str = ""
    seccion_respaldo_id: Optional[str] = None
    seccion_respaldo: str = ""              # "3.2 · Reporte de operaciones"
    confianza: Optional[float] = None
    requiere_revision: bool = False
    elementos_faltantes: list[str] = []


class ParVia2(BaseModel):
    articulo_id: str
    identificador: str
    cobertura: Literal["total", "parcial", "nula"]


class FilaVia2(BaseModel):
    seccion_id: str
    identificador: str
    titulo: str = ""
    sin_base: bool = False                  # control del manual sin respaldo normativo
    pares: list[ParVia2] = []


class ComparacionOut(BaseModel):
    id: str
    estado: Literal["en_curso", "listo", "error", "cancelado"]
    conteos: dict[str, int] = {}
    via1: list[FilaVia1] = []
    via2: list[FilaVia2] = []
    conclusion: str = ""
    conclusion_editada: bool = False
    pares_juzgados: int = 0
    pares_a_revision: int = 0
    avisos: list[str] = []
    ajustes: dict[str, float] = {}           # valores de los ajustes (RF-19) con los que se hizo esta comparación


class ConclusionIn(BaseModel):
    texto: str = Field(max_length=20000)


class SesionOut(BaseModel):
    documentos: list[DocumentoOut] = []
    comparacion_id: Optional[str] = None


class HealthOut(BaseModel):
    estado: Literal["ok", "degradado"]
    stage: str
    llm: bool
    mensaje: str = ""


class AjusteOut(BaseModel):
    clave: str
    etiqueta: str
    ayuda: str
    tipo: Literal["entero", "decimal"]
    valor: float
    defecto: float
    minimo: float
    maximo: float
    paso: float
    avanzado: bool = False


class AjustesOut(BaseModel):
    parametros: list[AjusteOut]


class AjustesIn(BaseModel):
    valores: dict[str, float]               # se descartan las claves que no están en la lista blanca (config/ajustes.json)
