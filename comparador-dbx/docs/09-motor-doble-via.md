# 09 · Motor de doble vía

```mermaid
flowchart LR
    N["N artículos<br/>normativa seleccionada"] --> R1["Recuperación vía 1<br/>norma → índice manual<br/>top-K sub-chunks"]
    M["M secciones<br/>manual seleccionado"] --> R2["Recuperación vía 2<br/>manual → índice norma<br/>top-K sub-chunks"]
    R1 --> U{"Unión + dedup<br/>llave (art_id, sec_id)<br/>origen v1 · v2 · ambas"}
    R2 --> U
    N --> D["Descomposición GPT-5.6<br/>1 vez por artículo<br/>naturaleza + requisitos literales"]
    D --> J
    U --> J["Juez GPT-5.6<br/>1 vez por par<br/>estado de cada requisito"]
    J --> C["Verificación<br/>de citas y fragmentos literales"]
    C --> AG["Agregación en Python<br/>requisitos de todas las secciones<br/>marca + brechas por artículo<br/>vía 2: fragmentos sin base"]
```

## 1. Recuperación de candidatos
```python
K_SUBCHUNKS  = 10    # vecinos por sub-chunk consultado      [CALIBRAR]
SIM_THRESHOLD = 0.30 # similitud coseno mínima               [CALIBRAR]
MIN_FLOOR    = 3     # siempre pasan al menos 3 secciones
MAX_CANDIDATES = 10  # tope de secciones candidatas por origen

def candidatos(seccion_origen, indice_destino) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for sc in subchunks(seccion_origen):
        D, I = indice_destino.search(sc.vec, K_SUBCHUNKS)
        for s, i in zip(D[0], I[0]):
            if i < 0: continue
            sec = indice_destino.mapa[i]
            scores[sec] = max(scores.get(sec, 0.0), float(s))   # colapso: mejor score por sección
    orden = sorted(scores.items(), key=lambda x: -x[1])
    sobre = [x for x in orden if x[1] >= SIM_THRESHOLD][:MAX_CANDIDATES]
    return sobre if len(sobre) >= MIN_FLOOR else orden[:MIN_FLOOR]
```
El **piso** garantiza que ninguna sección desaparezca: si nada supera el umbral, el juez recibe los 3 mejores y declara explícitamente "sin cobertura".

## 2. Pares únicos (deduplicación) — decisión clave de costo
Problema: si el Art. 5 recupera la sección 3.2 y la 3.2 recupera el Art. 5, ingenuamente se juzga dos veces (doble costo y posibles veredictos contradictorios).

Solución: la recuperación en ambas direcciones **solo construye candidatos**; luego se unen, se deduplican por `(articulo_id, seccion_id)` y **cada par se juzga exactamente una vez**.

```python
pares: dict[tuple[str, str], Par] = {}
for art in articulos_sel:                                   # vía 1
    for sec, s in candidatos(art, idx_manual):
        p = pares.setdefault((art.id, sec), Par(art.id, sec))
        p.score_v1, p.rank_v1 = s, rank; p.origen.add("v1")
for sec in secciones_sel:                                   # vía 2
    for art, s in candidatos(sec, idx_norma):
        p = pares.setdefault((art, sec.id), Par(art, sec.id))
        p.score_v2, p.rank_v2 = s, rank; p.origen.add("v2")
# p.score_max = max(score_v1, score_v2)
# log: n_pares_ingenuo vs n_pares_unicos
```
Las vías reaparecen **solo al reportar**: vía 1 = agrupar pares por artículo; vía 2 = agrupar los mismos pares por sección. Mismo veredicto, dos vistas, sin reconciliación. 50 × 40 secciones: ~900 juicios ingenuos → típicamente la mitad o menos.

## 3. Juez auditor normativo
Dos pasos con el LLM; todo lo demás es Python (decisión del usuario, 15 oct 2026, docs/14 #28). El objetivo es que el auditor vea **qué parte exacta** del artículo no está cubierta por el manual.

### 3a. Descomposición del artículo en requisitos (1 llamada por artículo seleccionado)
- Prompt: `backend/prompts/requisitos.md` (nuevo). Entrada: texto literal completo del artículo + ruta + documento.
- Salida: la **naturaleza** del artículo (se decide aquí, una sola vez, y no por mayoría entre pares) y su lista de **requisitos atómicos**: cada uno con un id estable (`R1`, `R2`…), su **fragmento literal** del artículo y si es **obligatorio** (deber, prohibición, plazo, condición) o enunciativo (definición, finalidad, remisión).
- Un literal a), b)… es al menos un requisito (sustituye a `elementos_faltantes` como texto libre, docs/14 #6).
- Artículos `informativo` o `no_aplica_entidad`: sin requisitos; no pasan por el paso 3b (ahorra llamadas).

### 3b. Juicio por par (1 vez por par, como antes)
- Prompt: [`backend/prompts/juez.md`](../backend/prompts/juez.md).
- Entrada por par: texto literal **completo** del artículo y de la sección del manual + **la lista de requisitos del artículo** (3a) + rutas jerárquicas + nombres de documento.
- Para **cada requisito**: `cubierto`, `parcial` o `no_cubierto` **por esta sección**, la cita literal del manual que lo respalda y, si no está cubierto del todo, qué falta.
- Vía 2: los **fragmentos literales de la sección** que no responden a ningún requisito de este artículo.
- Concurrencia `asyncio` con semáforo `LLM_CONCURRENCY` (6). Progreso: "Par 128 de 412".

```python
class Requisito(BaseModel):                 # paso 3a, uno por requisito atómico del artículo
    id: str                                 # "R1", "R2"… estable dentro del artículo
    fragmento: str                          # literal del artículo (se verifica como una cita)
    obligatorio: bool                       # deber/prohibición/plazo/condición; False = enunciativo

class Descomposicion(BaseModel):            # paso 3a, una por artículo
    naturaleza_articulo: Literal["obligacion", "informativo", "no_aplica_entidad"]
    requisitos: list[Requisito] = []

class EstadoRequisito(BaseModel):           # paso 3b, uno por requisito y par
    requisito_id: str
    estado: Literal["cubierto", "parcial", "no_cubierto"]
    cita_manual: str | None = None          # literal de la sección que lo respalda (si cubierto o parcial)
    falta: str | None = None                # qué le falta (si parcial o no_cubierto); texto del juez, no del documento

class Veredicto(BaseModel):                 # paso 3b, uno por par
    requisitos: list[EstadoRequisito]       # todos los requisitos del artículo, sin omitir ninguno
    fragmentos_sin_base: list[str] = []     # vía 2: literales de la sección que no responden a ningún requisito de este artículo
    comentario: str
    confianza: float = Field(ge=0, le=1)

class Par(BaseModel):
    id: str
    articulo_id: str
    seccion_id: str
    origen: set[Literal["v1", "v2"]]
    score_v1: float | None = None; rank_v1: int | None = None
    score_v2: float | None = None; rank_v2: int | None = None
    veredicto: Veredicto | None = None
    cita_norma_verificada: bool = False
    cita_manual_verificada: bool = False
    requiere_revision: bool = False
```

## 4. Validación de la respuesta
1. Validar con Pydantic. JSON inválido → 1 reintento con el error adjunto → si persiste: `requiere_revision=True`, listado en el anexo.
2. **Verificación de citas** (cada cita contra su texto fuente):
   - normalizar espacios y saltos de línea; comprobar subcadena exacta → verificada.
   - si no: buscar el fragmento más parecido con `difflib.SequenceMatcher` sobre ventanas del texto fuente; si ratio ≥ `CITATION_FUZZY_MIN` (0.90) → **reemplazar por el fragmento real** y marcar verificada.
   - si no y ratio ≥ `CITATION_SHOW_MIN` (0.75): `cita_*_verificada=False`, `requiere_revision=True`; el papel muestra el fragmento real más cercano con aviso.
   - si ratio < 0.75: `cita_*_verificada=False`, `requiere_revision=True`; celda vacía con aviso.
3. Se verifican así: el `fragmento` de cada requisito (contra el artículo), cada `cita_manual` y cada `fragmentos_sin_base` (contra la sección). La verificación además guarda la **posición** (inicio y fin) del fragmento en el texto literal: con ella se pinta el Excel.
4. Un fragmento que no se verifica **no se pinta** (ni rojo ni nada) y el par o el artículo queda `requiere_revision=True`; el texto completo sigue en la celda.
5. Si la lista de requisitos de un par no trae todos los ids de 3a, o trae ids que no existen: 1 reintento; si persiste, `requiere_revision=True`.
6. El texto que llega al Excel **siempre** proviene del documento fuente, nunca del modelo; el resaltado lo decide Python con las posiciones verificadas.

## 5. Agregación de marcas y brechas (Python, sin tokens)
Marcas del banco: **A** sí cumple · **L** parcialmente · **R** no cumple · **X** no aplica · **P** información obtenida de la normativa.
La marca es propiedad del **artículo** (fila del papel) y se deriva de **sus requisitos combinando todas las secciones juzgadas** (decisión del usuario, 15 oct 2026: varias secciones del manual pueden respaldar un mismo artículo; reemplaza docs/14 #5).

```python
ORDEN = {"cubierto": 2, "parcial": 1, "no_cubierto": 0}

def estado_requisitos(desc: Descomposicion, pares: list[Par]) -> dict[str, tuple[str, list[Par]]]:
    """Por requisito: el mejor estado entre todas las secciones y los pares que lo respaldan (cubierto o parcial)."""
    out = {}
    for r in desc.requisitos:
        estados = [(e, p) for p in pares if p.veredicto for e in p.veredicto.requisitos if e.requisito_id == r.id]
        mejor = max((e.estado for e, _ in estados), key=ORDEN.get, default="no_cubierto")
        out[r.id] = (mejor, [p for e, p in estados if e.estado != "no_cubierto"])
    return out

def marca_articulo(desc, pares) -> tuple[str, list[Requisito]]:
    if desc.naturaleza_articulo == "informativo":       return "P", []
    if desc.naturaleza_articulo == "no_aplica_entidad": return "X", []
    est = estado_requisitos(desc, pares)
    oblig = [r for r in desc.requisitos if r.obligatorio]
    brechas = [r for r in oblig if est[r.id][0] != "cubierto"]      # se pintan en rojo (docs/10)
    if not brechas:                                                  return "A", []
    if any(est[r.id][0] != "no_cubierto" for r in oblig):            return "L", brechas
    return "R", brechas                                              # R: solo los requisitos obligatorios van en rojo

# `secciones_sel` son solo las secciones INCLUIDAS (las excluidas como no comparables no son controles sin base: van aparte, con su motivo, en el anexo).
def controles_sin_base(secciones_sel, pares) -> dict[str, list[tuple[int, int]]]:
    # Vía 2, por sección:
    # - sin ningún par con algún requisito cubierto o parcial de un artículo "obligacion" -> la sección entera es control sin base;
    # - si no, los tramos (posiciones verificadas) que aparecen en `fragmentos_sin_base` en TODOS los pares de la sección con
    #   artículos "obligacion" (intersección): ningún artículo juzgado los respalda. Se pintan en rojo en el bloque vía 2.
```

- **Varias secciones, un artículo:** un requisito está cubierto si **alguna** sección lo cubre. El respaldo del artículo son **todas** las secciones que cubren o cubren parcialmente algún requisito, no una sola.
- **Lo que se resalta es solo la brecha:** el texto de los requisitos obligatorios no cubiertos o cubiertos parcialmente. Lo cubierto **no se resalta**: marcar algo como "cumple" equivale a aprobarlo, y aprobar el control es responsabilidad del dueño del manual y del proceso, no de auditoría (usuario, 15 oct 2026).
- **Criterio conservador:** dos coberturas parciales del **mismo** requisito en secciones distintas no suman una total: el requisito queda `parcial` (en rojo) y el juez explica qué falta en cada una.
- **Costo:** +1 llamada por artículo (paso 3a) y una salida más larga por par. Se mide contra RNF-11.

