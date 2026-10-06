from typing import Literal, List, Optional
from pydantic import BaseModel

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
