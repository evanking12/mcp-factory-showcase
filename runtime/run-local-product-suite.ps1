param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("easy01", "medium01", "medium02", "hard01")]
    [string]$Suite,
    [string]$OutputRoot = "",
    [switch]$StopAfterFirstFailure,
    [int]$PollSec = 2,
    [int]$AnalyzeTimeoutSec = 240,
    [int]$ExploreTimeoutSec = 360,
    [int]$StuckSeconds = 120,
    [string]$TargetNames = "",
    [string]$PriorJobId = "",
    [string]$CrossDllPriorJobIds = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$Args = @(
    (Join-Path $PSScriptRoot "run_local_product_suite.py"),
    "--suite", $Suite,
    "--poll-sec", [string]$PollSec,
    "--analyze-timeout-sec", [string]$AnalyzeTimeoutSec,
    "--explore-timeout-sec", [string]$ExploreTimeoutSec,
    "--stuck-seconds", [string]$StuckSeconds
)
if ($OutputRoot) {
    $Args += @("--output-root", $OutputRoot)
}
if ($StopAfterFirstFailure) {
    $Args += "--stop-after-first-failure"
}
if ($TargetNames) {
    $Args += @("--target-names", $TargetNames)
}
if ($PriorJobId) {
    $Args += @("--prior-job-id", $PriorJobId)
}
if ($CrossDllPriorJobIds) {
    $Args += @("--cross-dll-prior-job-ids", $CrossDllPriorJobIds)
}

& $PythonExe @Args
exit $LASTEXITCODE
