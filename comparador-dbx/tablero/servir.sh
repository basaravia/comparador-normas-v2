#!/usr/bin/env bash
# Sirve el tablero solo en la red local, para verlo desde el navegador o el celular sin publicarlo.
# Solo expone esta carpeta (index.html y datos.js), en la IP de la LAN; no pasa por internet.
# Uso: bash comparador-dbx/tablero/servir.sh [puerto]      Ctrl+C para detenerlo.
set -euo pipefail
PUERTO="${1:-8765}"
IP=$(hostname -I | tr ' ' '\n' | grep -E '^192\.168\.|^10\.' | head -1)
[ -n "$IP" ] || { echo "No encontré una IP de red local (192.168.x / 10.x)."; exit 1; }
echo "Tablero en: http://$IP:$PUERTO/   (misma red Wi-Fi; Ctrl+C para detener)"
exec python3 -m http.server "$PUERTO" --bind "$IP" --directory "$(dirname "$0")"
