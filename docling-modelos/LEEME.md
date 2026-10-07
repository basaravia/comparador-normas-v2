# Modelos de Docling (copia temporal)

Rama auxiliar, **temporal**: contiene los modelos públicos que Docling descarga de Hugging Face (`ds4sd/docling-layout-heron` y `ds4sd/docling-models`, ~470 MB), partidos en trozos de 90 MB porque GitHub rechaza archivos de más de 100 MB. Se borra tras copiarla. No tiene código ni secretos.

## Descargar y armar (en el equipo donde Hugging Face está bloqueado)

```
git clone --depth 1 --branch aux/docling-modelos --single-branch https://github.com/basaravia/comparador-normas-v2.git docling-modelos-tmp
cd docling-modelos-tmp/docling-modelos
cat parte-* > ~/docling-modelos.tar.gz
shasum -a 256 ~/docling-modelos.tar.gz        # debe coincidir con SHA256.txt
mkdir -p ~/.cache/huggingface/hub
tar xzf ~/docling-modelos.tar.gz -C ~/.cache/huggingface/hub
```

Luego, en `config/.env` del proyecto: `HF_HUB_OFFLINE=1`. Más detalle en `documentos/LEEME.md` de la rama `main`.

Al terminar: borra la carpeta `docling-modelos-tmp` y el archivo `~/docling-modelos.tar.gz`.
