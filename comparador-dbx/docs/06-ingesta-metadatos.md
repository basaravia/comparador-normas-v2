# 06 · Ingesta y metadatos

## 1. Validación
```python
def validar_pdf(path: Path) -> ResultadoValidacion:
    doc = fitz.open(path)
    if doc.page_count > MAX_PAGES or path.stat().st_size > MAX_MB * 1024**2:
        return rechazo("limites")
    # Detección de escaneo: proporción de páginas con texto útil
    con_texto = sum(len(p.get_text("text").strip()) >= 50 for p in doc)
    if con_texto / doc.page_count < SCAN_TEXT_RATIO:          # 0.6 [CALIBRAR]
        return rechazo("escaneado")
    return ok(sha256=hash_archivo(path))                       # clave de caché por sesión
```

## 2. Metadatos nativos (sin tokens)
Leer `doc.metadata` de PyMuPDF: `title, author, subject, keywords, creationDate, modDate, producer`.
Sirven para completar o contrastar lo que proponga el modelo. **Nunca sobrescriben un valor editado por el auditor.**

## 3. Clasificación y metadatos con GPT-5.6
- **Una llamada por documento.** Entrada: nombre del archivo + metadatos nativos + texto de las 2 primeras páginas (truncado ~6.000 caracteres).
- Prompt: [`backend/prompts/clasificador.md`](../backend/prompts/clasificador.md). Salida: solo JSON.
- **La decisión de preseleccionar la toma el backend**, no el modelo.

```python
class MetadatosLLM(BaseModel):
    tipo_documento: Literal["normativa", "manual_control", "desconocido"]
    confianza_tipo: float = Field(ge=0, le=1)
    entidad_emisora: str | None = None
    titulo_oficial: str | None = None
    libro: str | None = None
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None
    numero_norma: str | None = None
    fecha_emision: date | None = None
    fecha_vigencia: date | None = None
    version: str | None = None
    area_responsable: str | None = None
    evidencia_tipo: str
```

```python
# Lógica determinista
if r.tipo_documento != "desconocido" and r.confianza_tipo >= TYPE_CONFIDENCE:  # 0.75 [CALIBRAR]
    fila.tipo, fila.tipo_sugerido = r.tipo_documento, True
else:
    fila.tipo = None            # el auditor elige; la fila se resalta

# Prioridad de metadatos: editado por auditor > LLM > nativo del PDF > vacío
# Fechas validadas con datetime; si no parsean -> None.
# JSON inválido: 1 reintento con el error adjunto; si vuelve a fallar, todo vacío sin bloquear la carga.
```
