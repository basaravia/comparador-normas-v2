# Fuentes alojadas en el repositorio

**IBM Plex Sans** (pesos 400, 600 y 700), formato `.woff2`. Licencia **SIL Open Font License 1.1** (texto en `OFL.txt`; «Copyright © 2017 IBM Corp. with Reserved Font Name "Plex"»): se pueden redistribuir con el repositorio; si se modifican o se recortan hay que cambiarles el nombre.

- **Origen:** https://github.com/IBM/plex, carpeta `packages/plex-sans/fonts/complete/woff2/` (descargadas el 25 nov 2026 con permiso del usuario, D-64).
- **Por qué aquí:** la política de seguridad (`default-src 'self'`) no admite fuentes de otro sitio; Vite las empaqueta en `/assets` al compilar.
- **SHA-256:**
  - `IBMPlexSans-Bold.woff2`: `0ee7512b5d3b040fe7c0b874df0965b357777d3929f627dfea202ff63834d05d`
  - `IBMPlexSans-Regular.woff2`: `78efbe80177406a1b80d5925e706e3366290bf0d5309d7b0bd2d7f0d607f3c4c`
  - `IBMPlexSans-SemiBold.woff2`: `0fe2655c3c88b0b4c578b0046333fde7fb60d18419b9d07b4a1e115ac893e7f6`

Para usar otra tipografía (la del banco) basta con cambiar `--fuente` en `:root` de `estilos.css` y quitar estos archivos y los `@font-face`.
