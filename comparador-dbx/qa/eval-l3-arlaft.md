# Golden ARLAFT (8 oct 2026) y medición de la recuperación con un manual real

**Golden:** `tests/golden_arlaft.csv`. 35 artículos del proyecto de ley LA/FT (31–63, 89 y 90) contra `MANUAL-ARLAFT-V14.pdf` (local, sintético muy similar al real). 81 filas: 76 pares con sección (relevancia 2 = cubre el artículo, 1 = apoyo) y 5 omisiones.
**Etiquetas: PROPUESTA del modelo, sin confirmar por el auditor.** Hay que revisarlas antes de usarlas como criterio de aceptación (qa-ia: ≥100 positivos, doble etiquetado de una muestra).
**Medición:** `STAGE=sandbox EMB_BATCH=8 python scripts/medir_recuperacion.py tests/golden_arlaft.csv <norma.pdf> <manual.pdf>` (bge-m3 real, toda la ley como norma, SIM 0,50, K 10, tope 10).

## Resultado (sandbox, bge-m3)
Pares a juzgar: 1341 (ingenuos 1723) · SIM_THRESHOLD=0.5 K=10 MAX=10
AVISO: filas del golden con sección que no está entre las incluidas (id cambió o fue excluida): ['G-009']
[todas (relevancia 1 y 2)] n=75
  recall@candidatos (unión): 56/75 = 74.7 %  (IC95 64–83 %)
  vía 1: k=1: 23 %  k=3: 39 %  k=5: 45 %  k=10: 59 %  k=20: 76 %  MRR=0.346  peor rango=81
  vía 2: k=1: 27 %  k=3: 47 %  k=5: 55 %  k=10: 68 %  k=20: 80 %  MRR=0.407  peor rango=86
[solo relevancia 2] n=37
  recall@candidatos (unión): 31/37 = 83.8 %  (IC95 69–92 %)
  vía 1: k=1: 35 %  k=3: 65 %  k=5: 70 %  k=10: 76 %  k=20: 84 %  MRR=0.515  peor rango=45
  vía 2: k=1: 49 %  k=3: 70 %  k=5: 78 %  k=10: 81 %  k=20: 86 %  MRR=0.621  peor rango=52
[estrato larga] n=11
  recall@candidatos (unión): 7/11 = 63.6 %  (IC95 35–85 %)
  vía 1: k=1: 0 %  k=3: 9 %  k=5: 27 %  k=10: 45 %  k=20: 64 %  MRR=0.128  peor rango=31
  vía 2: k=1: 9 %  k=3: 9 %  k=5: 9 %  k=10: 36 %  k=20: 55 %  MRR=0.154  peor rango=54
[estrato tabla] n=4
  recall@candidatos (unión): 4/4 = 100.0 %  (IC95 51–100 %)
  vía 1: k=1: 25 %  k=3: 50 %  k=5: 75 %  k=10: 100 %  k=20: 100 %  MRR=0.450  peor rango=10
  vía 2: k=1: 50 %  k=3: 50 %  k=5: 50 %  k=10: 75 %  k=20: 75 %  MRR=0.548  peor rango=40
[estrato parcial] n=24
  recall@candidatos (unión): 19/24 = 79.2 %  (IC95 60–91 %)
  vía 1: k=1: 25 %  k=3: 33 %  k=5: 42 %  k=10: 62 %  k=20: 83 %  MRR=0.349  peor rango=80
  vía 2: k=1: 25 %  k=3: 46 %  k=5: 50 %  k=10: 71 %  k=20: 79 %  MRR=0.378  peor rango=86
[estrato cumple] n=51
  recall@candidatos (unión): 37/51 = 72.5 %  (IC95 59–83 %)
  vía 1: k=1: 22 %  k=3: 41 %  k=5: 47 %  k=10: 57 %  k=20: 73 %  MRR=0.345  peor rango=81
  vía 2: k=1: 27 %  k=3: 47 %  k=5: 57 %  k=10: 67 %  k=20: 80 %  MRR=0.421  peor rango=52
Omisiones (5 artículos): candidatos por artículo, media 9.2 (piso 3, tope 10)
Fallos (id, artículo, sección, rango vía 1, rango vía 2):
   ('G-002', 'Artículo 31', '4.4', 25, 18)
   ('G-004', 'Artículo 31', 'VI', 44, 29)
   ('G-006', 'Artículo 31', '4.3', 81, 43)
   ('G-007', 'Artículo 31', '5.5.1', 78, 6)
   ('G-011', 'Artículo 32', '4.4', 29, 44)
   ('G-018', 'Artículo 35', '4.4', 30, 14)
   ('G-020', 'Artículo 36', '3.1', 60, 46)
   ('G-025', 'Artículo 38', '5.4.1', 13, 11)
   ('G-027', 'Artículo 39', '5.4.2', 36, 28)
   ('G-028', 'Artículo 39', '5.4.5.1', 57, 18)
   ('G-029', 'Artículo 40', '5.4.5.10', 25, 18)
   ('G-040', 'Artículo 44', '5.4.6.3', 38, 26)
   ('G-044', 'Artículo 45', '5.4.1', 25, 50)
   ('G-072', 'Artículo 60', '4.4', 31, 33)
   ('G-073', 'Artículo 60', '5.4.6.3', 18, 20)
   ('G-077', 'Artículo 89', '5.3.10.2', 13, 24)
   ('G-078', 'Artículo 89', '5.4.6.1', 45, 52)
   ('G-080', 'Artículo 90', '5.4.5.5', 80, 86)
   ('G-081', 'Artículo 90', '5.3.9', 10, 28)

## Lectura
- Con un manual real el recall@candidatos baja a **74,7 %** (83,8 % si solo cuenta relevancia 2), frente a 93,3 % con los MOCK (escritos para coincidir con la norma). No cumple el criterio de L3 (≥ 90 %).
- Las secciones largas (varios temas en una, como 4.4 Oficial de Cumplimiento) son las peores: 63,6 %.
- El umbral 0,50 casi no filtra: 1.341 pares únicos y 9,2 candidatos por artículo en las omisiones.
- Hallazgo del golden: "III. ASPECTOS GENERALES" se excluía como preámbulo y trae 3.1 y 3.2 (cumplen arts. 31, 33, 36). Se quitó del catálogo.
