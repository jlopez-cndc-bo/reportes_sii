# Registra Reportes SII (web) como tarea programada que arranca con Windows
# (equivalente ligero a un servicio). Ejecutar como Administrador.
# Uso:  pwsh -File instalar_tarea.ps1  [-Port 8000]
param([int]$Port = 8000)

$script = Join-Path $PSScriptRoot "run_prod.ps1"
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell).Source }

$action = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Port $Port"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "ReportesSII-Web" -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Highest -User "SYSTEM" -Force

Write-Host "Tarea 'ReportesSII-Web' registrada. Iniciar ahora con:"
Write-Host "  Start-ScheduledTask -TaskName ReportesSII-Web"
