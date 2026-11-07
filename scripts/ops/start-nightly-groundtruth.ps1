param(
    [double]$Hours = 8,
    [int]$MaxRuns = 20,
    [string]$ApiUrl = "",
    [string]$ApiKey = "",
    [ValidateSet("strict_dll","greybox_dll","full_surface")][string]$AnalysisProfile = "strict_dll",
    [ValidateSet("full","compact")][string]$SnapshotProfile = "full"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$harness = Join-Path $repoRoot "scripts\harness.ps1"
if (-not (Test-Path $harness)) { throw "Missing harness wrapper: $harness" }

$api = $ApiUrl
if (-not $api) {
    if ($env:MCP_FACTORY_API_URL) { $api = $env:MCP_FACTORY_API_URL }
    else { $api = "http://127.0.0.1:8201" }
}
$key = $ApiKey
if (-not $key -and $env:MCP_FACTORY_API_KEY) { $key = $env:MCP_FACTORY_API_KEY }

$logs = Join-Path $repoRoot "sessions\nightly"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outLog = Join-Path $logs ("nightly-groundtruth-" + $stamp + ".out.log")
$errLog = Join-Path $logs ("nightly-groundtruth-" + $stamp + ".err.log")

$args = @(
    "run",
    "--profile", "nightly",
    "--",
    "--hours", "$Hours",
    "--max-runs", "$MaxRuns",
    "--api-url", "$api",
    "--analysis-profile", "$AnalysisProfile",
    "--snapshot-profile", "$SnapshotProfile"
)
if ($key) {
    $args += @("--api-key", "$key")
}

$procArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $harness
) + $args
$proc = Start-Process -FilePath "powershell" -ArgumentList $procArgs -WorkingDirectory $repoRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru

Write-Host "Started nightly ground-truth campaign."
Write-Host "PID     : $($proc.Id)"
Write-Host "Stdout  : $outLog"
Write-Host "Stderr  : $errLog"
Write-Host "API URL : $api"
Write-Host "Profile : $AnalysisProfile / $SnapshotProfile"
