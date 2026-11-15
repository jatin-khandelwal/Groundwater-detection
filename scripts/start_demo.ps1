$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$model = Join-Path $projectRoot 'models\v2\model.pkl'
$database = Join-Path $projectRoot 'backend\data\groundwater.sqlite3'
$stateFile = Join-Path $projectRoot 'tmp\demo2_processes.json'
$logDir = Join-Path $projectRoot 'tmp'

foreach ($required in @($python, $model, $database)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required demo file is missing: $required"
    }
}

foreach ($port in @(8000, 8501)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        throw "Port $port is already in use (PID $($listener.OwningProcess)). Close the existing demo server or check it before starting another."
    }
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$backendOut = Join-Path $logDir 'demo_backend.out.log'
$backendErr = Join-Path $logDir 'demo_backend.err.log'
$frontendOut = Join-Path $logDir 'demo_frontend.out.log'
$frontendErr = Join-Path $logDir 'demo_frontend.err.log'
$started = @()
$oldAutoInit = $env:GW_AUTO_INIT_DB

function Wait-ForHttp {
    param([string]$Url, [int]$Attempts = 30)
    for ($try = 0; $try -lt $Attempts; $try++) {
        try { return Invoke-RestMethod -Uri $Url -TimeoutSec 3 }
        catch { Start-Sleep -Seconds 1 }
    }
    throw "Service did not respond in time: $Url"
}

try {
    $env:GW_AUTO_INIT_DB = '0'
    $backend = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr
    $started += $backend.Id

    $health = Wait-ForHttp -Url 'http://127.0.0.1:8000/health'
    if ($health.status -ne 'ok' -or -not $health.model_loaded -or -not $health.database_ready) {
        throw "Backend health check failed: $($health | ConvertTo-Json -Compress)"
    }

    $frontend = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'streamlit', 'run', 'frontend\streamlit_app.py', '--server.headless', 'true', '--server.address', '127.0.0.1', '--server.port', '8501') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr
    $started += $frontend.Id

    $null = Wait-ForHttp -Url 'http://127.0.0.1:8501'
    @{
        backend_pid = $backend.Id
        frontend_pid = $frontend.Id
        started_at = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8

    Write-Host 'Demo services are ready.' -ForegroundColor Green
    Write-Host 'Backend:  http://127.0.0.1:8000'
    Write-Host 'API docs: http://127.0.0.1:8000/docs'
    Write-Host 'Frontend: http://127.0.0.1:8501'
    Write-Host 'Stop both with: .\scripts\stop_demo.ps1'
}
catch {
    foreach ($processId in $started) { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }
    throw
}
finally {
    if ($null -eq $oldAutoInit) { Remove-Item Env:GW_AUTO_INIT_DB -ErrorAction SilentlyContinue }
    else { $env:GW_AUTO_INIT_DB = $oldAutoInit }
}
