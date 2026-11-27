#!/usr/bin/env bash
# Actualiza producción con el último paquete que armó GitHub Actions («Build web package»),
# sin scp: el servidor lo baja de GitHub (salida HTTPS) y lo instala con install_package.sh.
#
# Uso (como administrador, NO con sudo: el script pide sudo donde hace falta):
#   reportes-actualizar             # último build exitoso de main, pide confirmación
#   reportes-actualizar -y          # sin confirmación
#   reportes-actualizar <run-id>    # un build puntual (p. ej. para volver atrás)
#
# Requisito único: gh instalado y autenticado para este usuario con un token de sólo lectura
# (permiso «Actions: read» sobre el repo): gh auth login --with-token < token.txt
set -euo pipefail

REPO="${REPO:-jlopez-cndc-bo/reportes_sii}"
WORKFLOW="deploy-web.yml"
ARTIFACT="reportes-sii-web"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/reportes-sii}"
DEPLOY_RUN_USER="${DEPLOY_RUN_USER:-administrador}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8001/health}"
VERSION_FILE="${VERSION_FILE:-$HOME/.reportes-sii-version}"  # fuera de DEPLOY_PATH: el rsync --delete la borraría

SI=0
RUN_ID=""
for a in "$@"; do
  case "$a" in
    -y) SI=1 ;;
    *) RUN_ID="$a" ;;
  esac
done

command -v gh >/dev/null || { echo "ERROR: falta gh (GitHub CLI)." >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: gh no está autenticado: gh auth login --with-token < token.txt" >&2; exit 1; }

if [ -z "$RUN_ID" ]; then
  RUN_ID="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --branch main --status success -L 1 \
            --json databaseId --jq '.[0].databaseId')"
  [ -n "$RUN_ID" ] || { echo "ERROR: no hay ningún build exitoso de main en GitHub." >&2; exit 1; }
fi

SHA="$(gh run view "$RUN_ID" -R "$REPO" --json headSha --jq .headSha)"
INFO="$(gh run view "$RUN_ID" -R "$REPO" --json displayTitle,createdAt --jq '"\(.createdAt)  \(.displayTitle)"')"
ACTUAL="$(cat "$VERSION_FILE" 2>/dev/null || echo "desconocida")"

echo "Instalada : $ACTUAL"
echo "A instalar: ${SHA:0:7}  (build $RUN_ID, $INFO)"
if [ "$ACTUAL" = "$SHA" ] && [ "$SI" -eq 0 ]; then
  echo "Ya está instalada esa versión."
  exit 0
fi
if [ "$SI" -eq 0 ]; then
  read -r -p "¿Instalar? [s/N] " r
  [ "$r" = "s" ] || [ "$r" = "S" ] || { echo "Cancelado."; exit 0; }
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
gh run download "$RUN_ID" -R "$REPO" --name "$ARTIFACT" --dir "$TMP"
PKG="$(ls "$TMP"/reportes-sii-web-*.tgz)"

sudo DEPLOY_PATH="$DEPLOY_PATH" DEPLOY_RUN_USER="$DEPLOY_RUN_USER" \
  bash "$DEPLOY_PATH/deploy/install_package.sh" "$PKG"

for _ in $(seq 1 20); do  # el servicio tarda unos segundos en abrir el pool de Oracle
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "$SHA" > "$VERSION_FILE"
    echo "OK: ${SHA:0:7} instalada. $(curl -fsS "$HEALTH_URL")"
    exit 0
  fi
  sleep 2
done
echo "ERROR: el servicio no responde en $HEALTH_URL. Revise: journalctl -u reportes-sii -n 50" >&2
exit 1
