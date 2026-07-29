# Despliegue de Reportes SII (web) — servidor Linux, red interna, sin autenticación

La app es un solo proceso: FastAPI sirve la API **y** el frontend compilado
(`frontend/dist`) en el mismo puerto. No requiere nginx ni Docker (opcional).

## Requisitos en el servidor (Linux)
- Python 3.11+ (el driver `oracledb` en modo *thin* no necesita Oracle Client).
- Acceso de red al Oracle (puerto 1521).
- Node.js **no** es necesario: el frontend se compila en la máquina de
  desarrollo y se copia la carpeta `frontend/dist`.

## Pasos
1. Compilar el frontend en la máquina de desarrollo (Windows):
   ```powershell
   cd web\frontend
   npm run build        # genera frontend\dist
   ```
2. Copiar al servidor (omitir `backend/.venv` y `frontend/node_modules`;
   `frontend/` solo necesita `dist/`):
   ```bash
   sudo mkdir -p /opt/reportes-sii
   # copiar backend/ y frontend/dist/ p.ej. con scp o rsync:
   # rsync -av --exclude .venv --exclude node_modules web/ usuario@servidor:/opt/reportes-sii/
   ```
3. Crear el venv e instalar dependencias:
   ```bash
   cd /opt/reportes-sii/backend
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
4. Configurar `/opt/reportes-sii/backend/.env` (ver `.env.example`):
   ```
   ORACLE_USER=<cuenta_solo_lectura>
   ORACLE_PASSWORD=<clave>
   ORACLE_DSN=<host>:1521/<servicio>
   ```
   ⚠ En producción usar una **cuenta Oracle de solo lectura real**
   (no `desa/desa`). Pedir al DBA grants de SELECT sobre: `dc_eventos`,
   `dc_prog_mant`, `objetos`, `objetos_objetos`, `dw_relaciones`,
   `sm_energia_cen_dia`, las funciones `ri_*`, `pkg_objetos` y el paquete
   `smec.smec_potencia_api`.
5. Probar manualmente:
   ```bash
   /opt/reportes-sii/deploy/run_prod.sh      # sirve en http://<servidor>:8000
   curl http://localhost:8000/health         # {"status":"ok","oracle":"conectado"}
   ```
6. Dejar como servicio (systemd):
   ```bash
   sudo useradd -r -s /usr/sbin/nologin reportes   # si no existe
   sudo chown -R reportes: /opt/reportes-sii
   sudo cp /opt/reportes-sii/deploy/reportes-sii.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now reportes-sii
   systemctl status reportes-sii
   ```
7. Abrir el puerto si el firewall está activo:
   ```bash
   sudo firewall-cmd --permanent --add-port=8000/tcp && sudo firewall-cmd --reload
   # o con ufw:  sudo ufw allow 8000/tcp
   ```

## Autenticación
Decisión actual: **sin autenticación** (red interna, BD de solo lectura).
Si más adelante se quiere restringir, definir en el `.env`:
```
APP_USER=<usuario>
APP_PASSWORD=<clave>
```
y reiniciar (`sudo systemctl restart reportes-sii`) — se activa HTTP Basic.

## Actualizar la app
1. Reemplazar `backend/app` y/o `frontend/dist` en el servidor.
2. `sudo systemctl restart reportes-sii`

## Automatización con GitHub Actions

El repositorio debe crearse desde la carpeta `web/` para versionar sólo la
solución web, sin los proyectos WinForms/.NET legacy de la raíz.

Incluye `.github/workflows/deploy-web.yml`. No se ejecuta automáticamente por
push; se lanza manualmente desde GitHub Actions cuando se quiere generar un
paquete descargable.

El pipeline:

1. instala dependencias del backend;
2. ejecuta `pytest`;
3. instala dependencias del frontend;
4. ejecuta `npm run build`;
5. publica un artefacto `.tgz` descargable desde GitHub.

Para generarlo:

1. GitHub → `Actions`.
2. `Build web package`.
3. `Run workflow`.
4. Descargar el artefacto `reportes-sii-web`.

Como `proyectos.cndc.bo` es un servidor interno, los runners públicos de GitHub
no pueden conectarse por SSH hacia él. El despliegue se completa manualmente
descargando el artefacto en el servidor y ejecutando:

```bash
chmod +x deploy/install_package.sh
./deploy/install_package.sh /ruta/reportes-sii-web-<sha>.tgz
```

El script sincroniza `/opt/reportes-sii` conservando `backend/.env` y
`backend/.venv`, instala/actualiza dependencias Python y reinicia `systemd`.

Configurar en GitHub → Settings → Secrets and variables → Actions → Variables:

| Variable | Default |
|---|---|
| `DEPLOY_PATH` | `/opt/reportes-sii` |
| `DEPLOY_SERVICE` | `reportes-sii` |
| `DEPLOY_RUN_USER` | `reportes` |

El archivo `backend/.env` debe crearse una sola vez en el servidor y no se sube
a GitHub. El pipeline falla explícitamente si no existe.

## Salud y diagnóstico
- `http://<servidor>:8000/health` → estado de la conexión Oracle.
- Documentación interactiva de la API en `/docs`.
- Logs: `journalctl -u reportes-sii -f`

## Alternativa Windows
Si algún día se despliega en Windows, están `run_prod.ps1` (lanzamiento
manual) e `instalar_tarea.ps1` (tarea programada al arranque).
