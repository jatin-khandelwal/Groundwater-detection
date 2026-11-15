$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $projectRoot 'tmp\demo2_processes.json'

if (-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) {
    Write-Host 'No demo process record found; nothing was stopped.'
    exit 0
}

$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$targets = @(
    @{ Port = 8000; RecordedId = [int]$state.backend_pid; Pattern = 'uvicorn backend\.app\.main:app' },
    @{ Port = 8501; RecordedId = [int]$state.frontend_pid; Pattern = 'streamlit.*frontend\\streamlit_app\.py' }
)

foreach ($target in $targets) {
    $candidateIds = @($target.RecordedId)
    $candidateIds += @(Get-NetTCPConnection -State Listen -LocalPort $target.Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($processId in ($candidateIds | Where-Object { $_ } | Sort-Object -Unique)) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($processInfo -and $processInfo.Name -match '^python(w)?\.exe$' -and $processInfo.CommandLine -match $target.Pattern) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped verified demo process $processId on port $($target.Port)."
        }
    }
}

for ($attempt = 0; $attempt -lt 10; $attempt++) {
    $remaining = Get-NetTCPConnection -State Listen -LocalPort 8000,8501 -ErrorAction SilentlyContinue
    if (-not $remaining) { break }
    Start-Sleep -Milliseconds 500
}

Remove-Item -LiteralPath $stateFile -Force
Write-Host 'Demo services stopped.' -ForegroundColor Green
