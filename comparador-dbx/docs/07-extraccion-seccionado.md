# 07 · Extracción y seccionado

## 1. Extracción con Docling
- **Reutilizar el módulo del repo.** Configuración MVP:
  - `do_ocr=False`
  - estructura de tablas solo si el módulo ya la usa
  - artefactos desde `DOCLING_ARTIFACTS` (`models_cache/docling/`)
- Ejecutar en `ThreadPoolExecutor(max_workers=1)`. El endpoint encola y devuelve `job_id` de inmediato.
- Acotar hilos: `OMP_NUM_THREADS` y `torch.set_num_threads(DOCLING_THREADS)` `[CALIBRAR]`.
- Salida intermedia: bloques `{tipo: encabezado|parrafo|tabla|lista, nivel?, texto, pagina}`.
- Eliminar encabezados y pies de página repetidos.

## 2. Cascada de seccionado
La sección es la **unidad de trabajo del auditor**. Las normativas no siempre usan "Artículo": aparecen ART., Sección, SEC., romanos, letras y numeración jerárquica. Se aplica una cascada y se registra qué nivel produjo cada sección.

| Nivel | Estrategia | Se usa cuando |
|---|---|---|
| 1 · Patrones | Catálogo de regex al inicio de cada bloque + jerarquía de encabezados de Docling | El documento coincide de forma consistente con ≥ 1 patrón |
| 2 · Tipografía | Encabezados por tamaño de fuente y negrita (PyMuPDF `get_text("dict")`) y niveles de Docling | Pocos o ningún patrón coinciden |
| 3 · Longitud | Bloques de ~1.200 caracteres respetando párrafos; `seccionado_incierto=True` | Ni patrones ni tipografía producen estructura |

### Catálogo de patrones (punto de partida)
```python
# Orden: de más específico a más general. Flags: re.IGNORECASE | re.MULTILINE
PATRONES = [
  ("libro",    r"^\s*LIBRO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b"),
  ("titulo",   r"^\s*T[IÍ]TULO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b"),
  ("capitulo", r"^\s*CAP[IÍ]TULO\s+([IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)\b"),
  ("seccion",  r"^\s*(SECCI[OÓ]N|SEC\.?)\s+([IVXLCDM]+|\d+(\.\d+)*|[A-Z])\b"),
  ("articulo", r"^\s*(ART[IÍ]CULO|ART\.?)\s*(\d+(\.\d+)*|[IVXLCDM]+|[A-Z]+)(\s*\.?-|\.|:|\s)"),
  ("articulo", r"^\s*(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[EÉ]PTIMA|OCTAVA|NOVENA|D[EÉ]CIMA)\s*\.?-?\s"),  # disposiciones
  ("numeral",  r"^\s*(\d+(\.\d+){0,4})\.?\s+[A-ZÁÉÍÓÚ]"),   # 3.2.1 Título
  ("literal",  r"^\s*([a-z]|[ivx]+)\)\s"),                  # a)  iv)
]
```
Reglas:
- Un patrón es "del documento" si aparece **≥ 3 veces con numeración creciente**.
- Anidación por precedencia: `libro > titulo > capitulo > seccion > articulo > numeral > literal`.
- Los **literales** se mantienen **dentro** del texto del artículo, no se separan `[CALIBRAR]`.
- Numeración duplicada (ej. dos `ARTÍCULO 12`, error real conocido en una fuente SB): conservar ambos con sufijo `#2` y reportar advertencia. **No fusionar.**

## 3. Esquema de sección
```python
class Seccion(BaseModel):
    id: str                      # f"{doc_id}:{ruta_normalizada}", ej. "N1:L1/T2/C3/ART-15"
    doc_id: str
    tipo_doc: Literal["normativa", "manual_control"]
    nivel: str                   # articulo | seccion | numeral | bloque
    identificador: str           # "Art. 15", "3.2.1", "Sección IV"
    titulo: str | None
    ruta: list[str]              # ["Libro I", "Título II", "Capítulo III"]
    texto_literal: str           # texto exacto extraído, nunca parafraseado
    pagina_inicio: int
    pagina_fin: int
    seccionado_incierto: bool
    estrategia: Literal["patron", "tipografia", "longitud"]
    es_hoja: bool                # solo las hojas se evalúan
```

> **Decisión.** Las secciones evaluables son **hojas** del árbol (artículos en normativas; subsecciones más profundas en manuales). Los nodos padre sirven para agrupar y seleccionar; no se envían al juez.
