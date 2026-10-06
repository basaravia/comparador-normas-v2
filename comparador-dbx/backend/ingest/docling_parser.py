import os
import uuid
import shutil
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from backend.core.errors import ComparadorError

logger = logging.getLogger(__name__)

class DoclingTimeoutError(ComparadorError):
    codigo = "ERR-ING-004"
    mensaje_negocio = "El documento es demasiado complejo y excedió el tiempo límite de procesamiento."

class PDFBombError(ComparadorError):
    codigo = "ERR-ING-005"
    mensaje_negocio = "El documento excede el límite de tamaño permitido por seguridad."

class ExtractionError(ComparadorError):
    codigo = "ERR-ING-006"
    mensaje_negocio = "Ocurrió un error al extraer el texto del documento."

# Simulación de importación de Docling
try:
    from docling.document_converter import DocumentConverter
except ImportError:
    DocumentConverter = None

def _run_docling_extraction(safe_path: str) -> list:
    """Ejecuta docling en el archivo. Esto ocurre dentro del thread aislado."""
    if not DocumentConverter:
        logger.warning("Docling no está instalado. Ejecutando extractor simulado (fallback).")
        return [
            {"texto": "LIBRO I", "pagina": 1, "tipo": "encabezado"},
            {"texto": "TÍTULO II", "pagina": 1, "tipo": "encabezado"},
            {"texto": "CAPÍTULO III", "pagina": 1, "tipo": "encabezado"},
            {"texto": "ARTÍCULO 1.- Mock", "pagina": 1, "tipo": "párrafo"}
        ]
        
    # En producción real
    converter = DocumentConverter()
    doc = converter.convert(safe_path)
    
    # Aquí iría el mapeo de doc.items a nuestro formato {"texto": x, "pagina": p}
    # Por ahora devolvemos lista vacía en entorno real hasta completar el mapeo
    return []

def extraer_con_docling(pdf_path: str, max_mb: int = 10, timeout_secs: int = 30) -> list:
    """
    Extrae el texto de un PDF usando Docling, implementando controles AppSec:
    1. Anti-Bomba (límite MB).
    2. Timeouts.
    3. Sanitización de paths (UUID).
    """
    # 1. Anti-bomba (Límite de tamaño)
    tamano_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if tamano_mb > max_mb:
        raise PDFBombError(f"El archivo excede el límite de {max_mb}MB (tamaño: {tamano_mb:.2f}MB).")
        
    # 3. Sanitización con UUID en /tmp
    safe_id = str(uuid.uuid4())
    safe_path = os.path.join(tempfile.gettempdir(), f"{safe_id}.pdf")
    
    try:
        shutil.copy2(pdf_path, safe_path)
        
        # 2. Timeout estricto usando ThreadPoolExecutor (1 worker para evitar saturación de RAM)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_docling_extraction, safe_path)
            try:
                bloques = future.result(timeout=timeout_secs)
                return bloques
            except TimeoutError:
                raise DoclingTimeoutError(f"El procesamiento excedió el límite de {timeout_secs}s.")
            except Exception as e:
                logger.error(f"Error en extracción Docling: {e}")
                raise ExtractionError(str(e))
    finally:
        if os.path.exists(safe_path):
            os.remove(safe_path)
