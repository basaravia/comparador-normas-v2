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


class JobOut(BaseModel):
    job_id: str
    tipo: Literal["procesamiento", "comparacion"]
    estado: Literal["en_cola", "en_curso", "listo", "error"]
    etapa: str = ""                         # texto de negocio: "Extrayendo el texto", "Juzgando pares"…
    doc_actual: str = ""
    progreso: float = 0.0                   # 0-1
    mensaje: str = ""
    errores: list[ErrorNegocio] = []
    documentos: dict[str, str] = {}         # doc_id -> estado (procesamiento)
    comparacion_id: Optional[str] = None    # comparación (cuando tipo == "comparacion")


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
    estado: Literal["en_curso", "listo", "error"]
    conteos: dict[str, int] = {}
    via1: list[FilaVia1] = []
    via2: list[FilaVia2] = []
    conclusion: str = ""
    conclusion_editada: bool = False
    pares_juzgados: int = 0
    pares_a_revision: int = 0
    avisos: list[str] = []


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
