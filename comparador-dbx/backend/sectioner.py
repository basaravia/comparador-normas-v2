import re
from typing import List, Dict, Any, Literal
from backend.models import Seccion

PATRONES = [
    ("libro",    re.compile(r"^\s*LIBRO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b", re.IGNORECASE | re.MULTILINE)),
    ("titulo",   re.compile(r"^\s*T[IÍ]TULO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b", re.IGNORECASE | re.MULTILINE)),
    ("capitulo", re.compile(r"^\s*CAP[IÍ]TULO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b", re.IGNORECASE | re.MULTILINE)),
    ("seccion",  re.compile(r"^\s*(SECCI[OÓ]N|SEC\.?)\s+([IVXLCDM]+|\d+(\.\d+)*|[A-Z])\b", re.IGNORECASE | re.MULTILINE)),
    ("articulo", re.compile(r"^\s*(ART[IÍ]CULO|ART\.?)\s*(\d+(\.\d+)*|[IVXLCDM]+|[A-Z]+)(\s*\.?-|\.|:|\s)", re.IGNORECASE | re.MULTILINE)),
    ("articulo", re.compile(r"^\s*(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[EÉ]PTIMA|OCTAVA|NOVENA|D[EÉ]CIMA)\s*\.?-?\s", re.IGNORECASE | re.MULTILINE)),
    ("numeral",  re.compile(r"^\s*(\d+(\.\d+){0,4})\.?\s+[A-ZÁÉÍÓÚ]", re.IGNORECASE | re.MULTILINE)),
]

JERARQUIA = ["libro", "titulo", "capitulo", "seccion", "articulo", "numeral"]

def extraer_jerarquia():
    pass

def aplicar_cascada():
    pass

def parsear_bloques(bloques: List[Dict[str, Any]], doc_id: str, tipo_doc: Literal["normativa", "manual_control"]) -> List[Seccion]:
    secciones_resultado = []
    
    estado_jerarquia = {}
    
    # Variables para la sección hoja actual (generalmente artículo)
    seccion_actual = None
    texto_acumulado = []
    
    conteo_ids = {} # Para manejar duplicados
    
    def cerrar_seccion_actual():
        if seccion_actual:
            seccion_actual.texto_literal = "\n".join(texto_acumulado).strip()
            secciones_resultado.append(seccion_actual)
            
    for bloque in bloques:
        texto = bloque["texto"]
        pagina = bloque.get("pagina", 1)
        
        # Buscar el mejor patrón que coincida
        coincidencia = None
        nivel_coincidencia = None
        
        for nivel_patron, regex in PATRONES:
            match = regex.search(texto)
            if match:
                coincidencia = match
                nivel_coincidencia = nivel_patron
                break
                
        if nivel_coincidencia:
            # Encontramos un nuevo nodo en la jerarquía
            identificador = coincidencia.group(0).strip().rstrip(".-:")
            
            # Limpiar niveles inferiores en el estado
            idx_nivel = JERARQUIA.index(nivel_coincidencia)
            for nivel_inferior in JERARQUIA[idx_nivel:]:
                estado_jerarquia.pop(nivel_inferior, None)
            
            if nivel_coincidencia == "articulo":
                # Es una hoja (en normativas)
                cerrar_seccion_actual()
                
                # Armar ruta
                ruta = [estado_jerarquia[n] for n in JERARQUIA[:idx_nivel] if n in estado_jerarquia]
                
                # Generar ID base
                # Ej: N1:L1/T2/ART-1
                # Simplificaremos el ID para la prueba
                id_limpio = identificador.replace(" ", "-").replace(".", "").replace("Í", "I").upper()
                id_base = f"{doc_id}:" + "/".join(ruta + [id_limpio])
                
                # Manejo de duplicados
                conteo_ids[id_base] = conteo_ids.get(id_base, 0) + 1
                if conteo_ids[id_base] > 1:
                    id_final = f"{id_base}#{conteo_ids[id_base]}"
                else:
                    id_final = id_base
                
                seccion_actual = Seccion(
                    id=id_final,
                    doc_id=doc_id,
                    tipo_doc=tipo_doc,
                    nivel="articulo",
                    identificador=identificador,
                    ruta=ruta,
                    texto_literal="",
                    pagina_inicio=pagina,
                    pagina_fin=pagina,
                    seccionado_incierto=False,
                    estrategia="patron",
                    es_hoja=True
                )
                texto_acumulado = [texto]
                estado_jerarquia["articulo"] = identificador
            else:
                # Nodo padre (libro, título, etc)
                estado_jerarquia[nivel_coincidencia] = identificador
                if seccion_actual:
                    # El texto que no es artículo pero cayó aquí, podría ser 
                    # texto introductorio. Como simplificación para los tests, 
                    # si hay una sección abierta (no debería, el padre cierra?), la mantenemos o cerramos.
                    cerrar_seccion_actual()
                    seccion_actual = None
        else:
            # Si no coincide con un nivel superior (ej. literales, párrafos sueltos)
            if seccion_actual:
                texto_acumulado.append(texto)
                seccion_actual.pagina_fin = pagina

    cerrar_seccion_actual()
    return secciones_resultado
