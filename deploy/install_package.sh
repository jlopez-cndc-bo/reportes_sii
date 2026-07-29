#!/usr/bin/env bash
# Instala manualmente un paquete generado por GitHub Actions.
# Uso:
#   ./deploy/install_package.sh /ruta/reportes-sii-web-<sha>.tgz
set -euo pipefail

PKG="${1:-}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/reportes-sii}"
DEPLOY_SERVICE="${DEPLOY_SERVICE:-reportes-sii}"
DEPLOY_RUN_USER="${DEPLOY_RUN_USER:-reportes}"
STAGE="/tmp/reportes-sii-web-manual-$$"

if [ -z "$PKG" ]; then
  echo "Uso: $0 /ruta/reportes-sii-web-<sha>.tgz" >&2
  exit 2
fi

if [ ! -f "$PKG" ]; then
  echo "ERROR: no existe el paquete: $PKG" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
tar -xzf "$PKG" -C "$STAGE"

sudo mkdir -p "$DEPLOY_PATH"
sudo rsync -a --delete \
  --exclude 'backend/.env' \
  --exclude 'backend/.venv' \
  "$STAGE/web/" "$DEPLOY_PATH/"

if [ ! -f "$DEPLOY_PATH/backend/.env" ]; then
  echo "ERROR: falta $DEPLOY_PATH/backend/.env en el servidor." >&2
  exit 1
fi

sudo chown -R "$DEPLOY_RUN_USER":"$DEPLOY_RUN_USER" "$DEPLOY_PATH"

if [ ! -x "$DEPLOY_PATH/backend/.venv/bin/python" ]; then
  sudo -u "$DEPLOY_RUN_USER" python3 -m venv "$DEPLOY_PATH/backend/.venv"
fi

sudo -u "$DEPLOY_RUN_USER" "$DEPLOY_PATH/backend/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$DEPLOY_RUN_USER" "$DEPLOY_PATH/backend/.venv/bin/pip" install -r "$DEPLOY_PATH/backend/requirements.txt"

sudo systemctl restart "$DEPLOY_SERVICE"
sudo systemctl --no-pager --full status "$DEPLOY_SERVICE"

rm -rf "$STAGE"
