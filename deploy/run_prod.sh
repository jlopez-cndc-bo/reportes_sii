#!/usr/bin/env bash
# Lanza Reportes SII (web) en modo producción (red interna).
# Uso: ./run_prod.sh [puerto]   (por defecto 8000)
set -euo pipefail

PORT="${1:-8000}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$DIR/backend"
PY="$BACKEND/.venv/bin/python"

[ -x "$PY" ] || { echo "ERROR: no existe el venv ($PY). Cree el venv e instale requirements.txt." >&2; exit 1; }
[ -f "$BACKEND/.env" ] || { echo "ERROR: falta backend/.env (ORACLE_USER/ORACLE_PASSWORD/ORACLE_DSN)." >&2; exit 1; }
[ -f "$DIR/frontend/dist/index.html" ] || echo "AVISO: no hay build del frontend (frontend/dist). Copie el dist/ compilado." >&2

cd "$BACKEND"
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
