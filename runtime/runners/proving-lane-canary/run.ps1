param(
    [string]$OutputRoot = "",
    [ValidateSet("auto", "observe_only")]
    [string]$FreshnessMode = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$RunnerScript = Join-Path $Root "scripts\runs\run_proving_lane_canary.py"

$args = @($RunnerScript)
if ($OutputRoot) {
    $args += @("--output-root", $OutputRoot)
}
$args += @("--freshness-mode", $FreshnessMode)

try {
    & $VenvPy @args
    if (Test-Path variable:LASTEXITCODE) {
        exit $LASTEXITCODE
    }
    if ($?) {
        exit 0
    }
    exit 1
} catch {
    Write-Error $_
    exit 1
}
