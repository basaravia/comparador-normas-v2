# Golden por requisito (norma LA/FT, arts. 31-63, 89 y 90, contra el manual sintético ARLAFT V14)

Construido el 16 oct 2026 por **doble etiquetado independiente** (dos etiquetadores sin ver el trabajo del otro, protocolo de `qa-ia`): descomposición de cada artículo en requisitos atómicos con ancla literal, obligatorio o enunciativo, estado frente al manual (cubierto, parcial, no cubierto), secciones de respaldo y cita literal. Anclas y citas validadas como subcadenas del texto fuente. Fusión con `scripts/fusionar_golden.py`.

| Dato | Valor |
|---|---|
| Artículos etiquetados | 35 (naturaleza coincide en 35/35, kappa 1,00; 57 `no_aplica_entidad`; 61 y 62 `informativo`) |
| Requisitos | A: 96 · B: 89 · emparejados: 85 · solo en uno: 15 |
| Estado en los emparejados | acuerdo 69/85 (81 %), kappa 0,71 |
| Requisitos con acuerdo (entran al golden) | 69: 33 cubiertos, 18 parciales, 18 no cubiertos |
| Por confirmar (el usuario decide) | 31 |
| Pares derivados `tests/golden_arlaft_v2.csv` | 71 (53 cubiertos, 18 parciales) + 5 artículos de omisión |

**Limitaciones:** 71 pares < 100 positivos del protocolo (subirá al resolver los `por_confirmar`); un solo manual sintético y una sola norma; ambos etiquetadores son modelos (no hay etiquetador humano auditor: el usuario debe validar `por_confirmar` y una muestra de los acordados). Zonas grises que ambos marcaron como dudosas: plazo del reporte de operaciones inusuales (4 días en 9.3 frente a 6 en 5.4.6.3), aprobación por "alta gerencia" frente a Directorio o Gerente Regional, umbrales 8 % y 10 % frente al 25 % de la norma.

## Recuperación medida con el golden (sandbox, EMB_BATCH=8, sin simular nada)
| | bge-m3 (umbral 0,50) | qwen3-embedding 0,6B (umbral 0,30) |
|---|---|---|
| recall@candidatos (n=71) | 74,6 % (IC95 63-83) | 73,2 % (IC95 62-82) |
| solo relevancia 2 (n=53) | 75,5 % | 75,5 % |
| recall con 20 por vía, vía 1 / vía 2 | 76 % / 80 % | 79 % / 82 % |
| MRR vía 1 / vía 2 | 0,35 / 0,42 | 0,34 / 0,43 |
| pares a juzgar | 1341 | 1337 |

Misma conclusión que con el golden anterior (74,7 %): lejos del 90 % de L3b.

## Experimento: consultar con cada requisito en lugar del artículo entero (vía 1, sin umbral, top-10)
Usa como consulta la ancla literal de cada requisito (el golden hace de "descomposición ideal": cota superior, no el resultado del LLM).

| | bge-m3 | qwen3-embedding 0,6B |
|---|---|---|
| requisito: alguna sección de respaldo en top-1 / 5 / 10 / 20 (n=50) | 54 / 76 / 86 / 90 % | 34 / 76 / 84 / 92 % |
| MRR por requisito | 0,66 | 0,53 |
| pares, artículo entero (10 candidatos por artículo) | 59,2 % | 63,4 % |
| pares, un top-10 por requisito (15 candidatos por artículo, media) | 76,1 % | 80,3 % |
| pares, unión de ambos (18-19 candidatos por artículo) | 78,9 % | 81,7 % |

Lectura: un artículo suele mezclar varios requisitos y su vector único los diluye. Con 15 candidatos por artículo la consulta por requisito alcanza lo que el sistema actual logra con ~38 pares por artículo (vía 1 + vía 2). Falta medirlo con la descomposición real del LLM del stage.
