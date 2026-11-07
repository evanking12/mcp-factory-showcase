$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$envLines = Get-Content ".env" | Where-Object {
    $_ -and -not $_.StartsWith("#") -and $_ -match "="
}
foreach ($line in $envLines) {
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
}

if (-not $env:BRIDGE_SECRET -and $env:GUI_BRIDGE_SECRET) {
    [System.Environment]::SetEnvironmentVariable("BRIDGE_SECRET", $env:GUI_BRIDGE_SECRET, "Process")
}

$py = Join-Path $repo ".venv\Scripts\python.exe"
$uvicorn = Join-Path $repo ".venv\Scripts\uvicorn.exe"
$bridgePort = if ($env:BRIDGE_PORT) { [int]$env:BRIDGE_PORT } else { 8090 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8201 }

function Stop-TrackedProcess {
    param(
        [int]$ProcessId
    )
    if (-not $ProcessId -or $ProcessId -le 0) {
        return
    }
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    } catch {}
}

foreach ($port in $bridgePort, $apiPort) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-TrackedProcess -ProcessId $_ }
}

Get-CimInstance Win32_Process |
    Where-Object {
        ($_.CommandLine -like "*scripts\\bridge\\gui_bridge.py*") -or
        ($_.CommandLine -like "*dashboard.main:app*--port $apiPort*") -or
        ($_.CommandLine -like "*api.routes.main:app*--port $apiPort*")
    } |
    ForEach-Object {
        Stop-TrackedProcess -ProcessId $_.ProcessId
    }

Start-Sleep -Seconds 2

Start-Process -FilePath $py `
    -ArgumentList "scripts\\bridge\\gui_bridge.py" `
    -WorkingDirectory $repo `
    -WindowStyle Hidden

Start-Process -FilePath $uvicorn `
    -ArgumentList "api.routes.main:app","--host","0.0.0.0","--port",$apiPort `
    -WorkingDirectory $repo `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    try {
        $bridge = Invoke-RestMethod -Uri "http://127.0.0.1:$bridgePort/health" -Method Get -TimeoutSec 5
        $api = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -Method Get -TimeoutSec 5
        if ($bridge.status -eq "ok" -and $api.status -eq "ok") {
            Write-Output "services-ready"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}

Write-Error "services-not-ready"
exit 1
