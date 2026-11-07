param(
    [string]$OutputRoot = "",
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "_managed_lane_startup.ps1")

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedOutputRoot = if ($OutputRoot) {
    $OutputRoot
} else {
    Join-Path $Root "sessions\managed_lane_startup\$timestamp"
}

try {
    $result = Invoke-ManagedLaneStartup -RepoRoot $Root -OutputRoot $resolvedOutputRoot -NoReload:$NoReload
    Write-Host "Managed lane startup validated." -ForegroundColor Green
    Write-Host "  output_root=$resolvedOutputRoot" -ForegroundColor Gray
    Write-Host "  packet_path=$($result.packet_path)" -ForegroundColor Gray
    Write-Host "  promotion_safe=$($result.packet.promotion_safe)" -ForegroundColor Gray
    Write-Host "  no_reload=$($result.packet.no_reload)" -ForegroundColor Gray
    exit 0
} catch {
    $failurePath = Join-Path $resolvedOutputRoot "lane-startup-failure.json"
    if (Test-Path $failurePath) {
        $failure = Get-Content -Path $failurePath -Raw | ConvertFrom-Json
        Write-Error "Managed lane startup failed [$($failure.failure_kind)]: $($failure.message)"
    } else {
        Write-Error "Managed lane startup failed: $($_.Exception.Message)"
    }
    exit 1
}
