# Lanza Reportes SII (web) en modo producción, accesible desde la red interna.
# Uso:  pwsh -File run_prod.ps1  [-Port 8000]
param([int]$Port = 8000)

$backend = Join-Path $PSScriptRoot "..\backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "No existe el venv del backend ($python). Cree el venv e instale requirements.txt."
    exit 1
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Error "Falta backend\.env (ORACLE_USER/ORACLE_PASSWORD/ORACLE_DSN)."
    exit 1
}
if (-not (Test-Path (Join-Path $backend "..\frontend\dist\index.html"))) {
    Write-Warning "No hay build del frontend (frontend\dist). Ejecute: cd ..\frontend; npm run build"
}

Set-Location $backend
& $python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
