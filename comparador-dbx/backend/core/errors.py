"""Errores del dominio: qué aborta la corrida y qué solo degrada una fila.

Adaptado de `errors.py` de la v6, simplificado.

- `LLMUnavailableError` / `ProviderConfigError`: el modelo no responde o está mal
  configurado. Ninguna fila siguiente saldrá mejor → **abortar**.
- `LLMOutputError`: el modelo respondió pero su JSON no vale ni tras el reintento → la
  fila queda `requiere_revision` y la corrida **sigue**.

Cada error lleva un código y un mensaje de negocio para la pantalla (`docs/05`); el
detalle técnico va solo a los logs.
"""


class ComparadorError(Exception):
    codigo = "ERR-GEN-001"
    mensaje_negocio = "Ocurrió un problema inesperado. Intenta de nuevo o consulta con soporte."

    def para_usuario(self) -> dict:
        return {"codigo": self.codigo, "mensaje": self.mensaje_negocio}


class LLMUnavailableError(ComparadorError):
    codigo = "ERR-LLM-001"
    mensaje_negocio = "No pudimos conectarnos al servicio de análisis. Intenta de nuevo en un momento."


class ProviderConfigError(LLMUnavailableError):
    codigo = "ERR-CFG-001"
    mensaje_negocio = "El servicio de análisis no está configurado correctamente. Consulta con soporte."


class LLMOutputError(ComparadorError):
    codigo = "ERR-LLM-010"
    mensaje_negocio = "Algunos resultados no se pudieron interpretar y quedaron marcados para revisión."


def clasificar(exc: Exception) -> ComparadorError:
    """Traduce una excepción del SDK `openai` a uno de los errores de arriba.

    Los reintentos ante 429/5xx ya los hizo el SDK; si llega aquí, se agotaron.
    """
    if isinstance(exc, ComparadorError):
        return exc
    nombre = type(exc).__name__
    if nombre in ("AuthenticationError", "PermissionDeniedError", "NotFoundError"):
        # Clave inválida o modelo/deployment inexistente: se arregla en la configuración.
        return ProviderConfigError(f"{nombre}: {exc}")
    # Conexión, timeout, límite de tasa, 5xx o algo desconocido: ante la duda, abortar.
    return LLMUnavailableError(f"{nombre}: {exc}")
