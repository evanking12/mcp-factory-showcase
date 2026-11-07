Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $Root "runtime\_runtime_contract.ps1")

function Get-RepoEnvValue {
    param([string]$Name)
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path $envPath)) {
        return ""
    }
    foreach ($line in Get-Content $envPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) { continue }
        if ($trimmed.Substring(0, $idx).Trim() -ne $Name) { continue }
        return $trimmed.Substring($idx + 1).Trim()
    }
    return ""
}

$bridge = Get-LocalRuntimeSystem -Name "bridge"
$baseUrl = Get-LocalRuntimeBaseUrl -Name "bridge" -HostName "127.0.0.1"
$admissionPath = Get-LocalRuntimeAdmissionPath -Name "bridge"
$headers = @{}
$bridgeKey = [string](Get-RepoEnvValue -Name "GUI_BRIDGE_SECRET")
if ($bridgeKey) {
    $headers[$bridge.auth_header] = $bridgeKey
}

try {
    $admission = Invoke-RestMethod -Uri "$baseUrl$admissionPath" -Headers $headers -TimeoutSec 5
} catch {
    Write-Error "Bridge runtime check failed: $($_.Exception.Message)"
    exit 1
}

if ($admission.component -ne $bridge.component) { throw "bridge_component_mismatch" }
if ($admission.role -ne $bridge.role) { throw "bridge_role_mismatch" }
if ($admission.contract_version -ne "local_lane_admission_v1") { throw "bridge_local_lane_admission_version_mismatch" }
if (-not [bool]$admission.admitted) {
    throw "bridge_local_lane_admission_red:$([string]($admission.blocking_reasons -join ','))"
}

Write-Host "Bridge runtime contract OK -> $baseUrl" -ForegroundColor Green
Write-Host ("  admitted={0} freshness_verdict={1}" -f [bool]$admission.admitted, [string]$admission.freshness_verdict) -ForegroundColor Gray
