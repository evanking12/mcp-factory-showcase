param(
    [Parameter(Mandatory = $true)][string]$JobId,
    [Parameter(Mandatory = $true)][string]$ApiUrl,
    [string]$Note = "",
    [string]$SessionsRoot = "$PSScriptRoot\..\..\sessions",
    [string]$ApiKey = "",
    [string]$TranscriptPath = "",
    [string]$OutDir = "",
    [ValidateSet("full", "compact")][string]$SnapshotProfile = "full",
    [switch]$CompatibilityMode,
    [switch]$EnforceHardFail
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$harness = Join-Path $repoRoot "scripts\harness.ps1"
if (-not (Test-Path $harness)) {
    throw "Missing harness wrapper: $harness"
}

$args = @(
    "capture",
    "--job-id", $JobId,
    "--api-url", $ApiUrl,
    "--snapshot-profile", $SnapshotProfile
)
if ($Note) {
    $args += @("--note", $Note)
}
if ($SessionsRoot) {
    $args += @("--sessions-root", $SessionsRoot)
}
if ($ApiKey) {
    $args += @("--api-key", $ApiKey)
}
if ($TranscriptPath) {
    $args += @("--transcript-path", $TranscriptPath)
}
if ($OutDir) {
    $args += @("--out-dir", $OutDir)
}
if ($CompatibilityMode) {
    $args += "--compatibility-mode"
}
if ($EnforceHardFail) {
    $args += "--enforce-hard-fail"
}

Write-Host ""
Write-Host "=== MCP Factory - Save Session (Harness) ===" -ForegroundColor Cyan
Write-Host "  Job ID : $JobId"
Write-Host "  API    : $ApiUrl"
Write-Host "  Mode   : $(if ($CompatibilityMode) { 'compatibility' } else { 'strict' })"

& $harness @args
exit $LASTEXITCODE
