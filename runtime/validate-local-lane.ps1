param(
    [string]$OutputRoot = "",
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "_runtime_contract.ps1")
. (Join-Path $PSScriptRoot "_managed_lane_startup.ps1")

$runner = Get-LocalRuntimeSystem -Name "runner"
$apiBaseUrl = Get-LocalRuntimeBaseUrl -Name "api" -HostName "127.0.0.1"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedOutputRoot = if ($OutputRoot) {
    $OutputRoot
} else {
    Join-Path $Root "sessions\proving_lane_validation\$timestamp"
}
if (-not (Test-Path $resolvedOutputRoot)) {
    New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
}

function Write-ValidatorFailurePacket {
    param(
        [string]$Stage,
        [string]$FailureKind,
        [string]$Message,
        [hashtable]$Details = @{}
    )

    $payload = [ordered]@{
        stage = $Stage
        failure_kind = $FailureKind
        message = $Message
        generated_at = (Get-Date).ToString("o")
        details = $Details
    }
    $failurePath = Join-Path $resolvedOutputRoot "lane-validator-failure.json"
    $json = $payload | ConvertTo-Json -Depth 8
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($failurePath, $json, $utf8NoBom)
}

Write-Host "Starting managed API + bridge lane..." -ForegroundColor Cyan
try {
    $startupResult = Invoke-ManagedLaneStartup -RepoRoot $Root -OutputRoot $resolvedOutputRoot -NoReload:$NoReload
    $labStatus = $startupResult.packet.lab_status
} catch {
    $startupFailurePath = Join-Path $resolvedOutputRoot "lane-startup-failure.json"
    $startupFailure = $null
    if (Test-Path $startupFailurePath) {
        $startupFailure = Get-Content -Path $startupFailurePath -Raw | ConvertFrom-Json
    }
    $details = @{
        startup_failure_path = $(if (Test-Path $startupFailurePath) { $startupFailurePath } else { "" })
        startup_log_path = $(if ($startupFailure -and $startupFailure.log_path) { [string]$startupFailure.log_path } else { Join-Path $resolvedOutputRoot "lane-startup.log" })
    }
    if ($startupFailure -and $startupFailure.details) {
        foreach ($property in $startupFailure.details.PSObject.Properties) {
            $details[$property.Name] = $property.Value
        }
    }
    Write-ValidatorFailurePacket `
        -Stage $(if ($startupFailure) { [string]$startupFailure.stage } else { "lane_startup" }) `
        -FailureKind $(if ($startupFailure) { [string]$startupFailure.failure_kind } else { "managed_lane_startup_failed" }) `
        -Message $(if ($startupFailure) { [string]$startupFailure.message } else { $_.Exception.Message }) `
        -Details $details
    exit 1
}

Write-Host "Running proving-lane canary..." -ForegroundColor Cyan
$freshnessMode = "observe_only"
& (Join-Path $PSScriptRoot "runners\proving-lane-canary\run.ps1") -OutputRoot $resolvedOutputRoot -FreshnessMode $freshnessMode
$canaryExitCode = if (Test-Path variable:LASTEXITCODE) { [int]$LASTEXITCODE } else { if ($?) { 0 } else { 1 } }
if ($canaryExitCode -ne 0) {
    $laneCanaryLogPath = Join-Path $resolvedOutputRoot "lane-canary.log"
    Write-ValidatorFailurePacket `
        -Stage "proving_lane_canary" `
        -FailureKind "proving_lane_canary_failed" `
        -Message "Proving lane canary failed before lane packet completion." `
        -Details @{
            exit_code = $canaryExitCode
            freshness_mode = $freshnessMode
            restart_suppressed = ($freshnessMode -eq "observe_only")
            canary_log_path = $(if (Test-Path $laneCanaryLogPath) { $laneCanaryLogPath } else { "" })
        }
    exit 1
}

$requiredPackets = @(Get-LocalRuntimeRunnerPackets)
foreach ($packet in $requiredPackets) {
    $packetPath = Join-Path $resolvedOutputRoot $packet
    if (-not (Test-Path $packetPath)) {
        Write-ValidatorFailurePacket -Stage "packet_completeness" -FailureKind "missing_required_lane_packet" -Message "Missing required runner packet: $packet" -Details @{ packet = $packet; packet_path = $packetPath }
        Write-Error "Missing required runner packet: $packetPath"
        exit 1
    }
}

$laneTrustPath = Join-Path $resolvedOutputRoot "lane-trust-packet.json"
$laneTrust = Get-Content -Path $laneTrustPath -Raw | ConvertFrom-Json
$expectedVerdict = [string]$runner.pass_verdict
if ([string]$laneTrust.canary_verdict -ne $expectedVerdict) {
    Write-ValidatorFailurePacket -Stage "lane_verdict" -FailureKind "unexpected_canary_verdict" -Message "Lane canary verdict did not match expected pass verdict." -Details @{ observed = [string]$laneTrust.canary_verdict; expected = $expectedVerdict }
    Write-Error "Lane canary verdict was '$($laneTrust.canary_verdict)', expected '$expectedVerdict'."
    exit 1
}

Write-Host "Local runtime lane validated." -ForegroundColor Green
Write-Host "  output_root=$resolvedOutputRoot" -ForegroundColor Gray
Write-Host "  no_reload=$NoReload" -ForegroundColor Gray
Write-Host "  lab_status=$($labStatus.status) promotion_safe=$($labStatus.lane_validity.promotion_safe)" -ForegroundColor Gray
Write-Host "  canary_verdict=$($laneTrust.canary_verdict)" -ForegroundColor Gray
