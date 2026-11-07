$ErrorActionPreference = "Stop"

param(
    [switch]$OpenBrowser
)

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

Write-Warning "sessions/restart_local_services.ps1 is a legacy wrapper. Use start.ps1 as the canonical runtime entrypoint."

$args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $repo "start.ps1"),
    "-LaneOnly",
    "-ForceRestartApi",
    "-ForceRestartBridge"
)

if (-not $OpenBrowser) {
    $args += "-NoBrowser"
}

& powershell @args
exit $LASTEXITCODE
