from typing import Literal, List, Optional
from pydantic import BaseModel, Field

class Seccion(BaseModel):
    id: str                      
    doc_id: str
    tipo_doc: Literal["normativa", "manual_control"]
    nivel: str                   
    identificador: str           
    titulo: Optional[str] = None
    ruta: List[str]              
    texto_literal: str           
    pagina_inicio: int
    pagina_fin: int
    seccionado_incierto: bool
    estrategia: Literal["patron", "tipografia", "longitud"]
    es_hoja: bool                


# --- Contrato compartido por los tres desarrolladores (docs/07 §3, docs/08, docs/09 §3) ---
# Lo define el agente principal para poder trabajar en paralelo; se amplía solo por acuerdo.

class Documento(BaseModel):
    id: str                                        # "N1", "M1"
    nombre: str                                    # nombre de archivo ya saneado
    tipo_doc: Literal["normativa", "manual_control"]
    sha256: str
    paginas: int
    metadatos: dict = {}


class SubChunk(BaseModel):
    id: str
    seccion_id: str
    texto: str
    orden: int
    # el vector se guarda aparte en numpy (float32, normalizado L2)


class Veredicto(BaseModel):
    naturaleza_articulo: Literal["obligacion", "informativo", "no_aplica_entidad"]
    cobertura: Literal["total", "parcial", "nula"]
    cita_norma: str
    cita_manual: Optional[str] = None
    comentario: str
    elementos_faltantes: List[str] = []
    confianza: float = Field(ge=0, le=1)


class Par(BaseModel):
    id: str
    articulo_id: str
    seccion_id: str
    origen: set[Literal["v1", "v2"]]
    score_v1: Optional[float] = None
    rank_v1: Optional[int] = None
    score_v2: Optional[float] = None
    rank_v2: Optional[int] = None
    veredicto: Optional[Veredicto] = None
    cita_norma_verificada: bool = False
    cita_manual_verificada: bool = False
    requiere_revision: bool = False
