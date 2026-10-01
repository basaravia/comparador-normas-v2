# Paquete de especificación — Comparador Normativo de Doble Vía (MVP)

Este paquete contiene la especificación para que Claude Code implemente el MVP.

## Cómo usarlo
1. Copia el contenido de este paquete en la raíz del repositorio de la aplicación (o en un repo nuevo que reutilice módulos del repo existente).
2. `CLAUDE.md` queda en la raíz: Claude Code lo lee automáticamente al iniciar sesión.
3. Pide a Claude Code: *"Lee CLAUDE.md y docs/00-INDEX.md, localiza en el repo los módulos reutilizables y ejecuta el Hito 0 de docs/13-plan-hitos.md."*

## Contenido
| Ruta | Propósito |
|---|---|
| `CLAUDE.md` | Reglas de trabajo para el agente (se carga en cada sesión) |
| `docs/` | Especificación completa por capítulos, diagramas en Mermaid |
| `backend/prompts/` | Prompts del clasificador, el juez y la conclusión, listos para cargar |
| `config/.env.example` | Variables de configuración con valores iniciales |

El PDF "Manual técnico de implementación" es la versión para lectura humana del mismo contenido. **La fuente de verdad es este paquete Markdown.**
