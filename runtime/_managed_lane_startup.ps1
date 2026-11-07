Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "_runtime_contract.ps1")

function Get-RepoEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $envPath = Join-Path $RepoRoot ".env"
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

function Write-JsonUtf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 12
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Add-ManagedLaneStartupLogLine {
    param(
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $timestamp = (Get-Date).ToString("o")
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $line = "[$timestamp] $Message" + [Environment]::NewLine
    [System.IO.File]::AppendAllText($LogPath, $line, $utf8NoBom)
}

function Write-ManagedLaneStartupFailurePacket {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$FailureKind,
        [Parameter(Mandatory = $true)][string]$Message,
        [hashtable]$Details = @{}
    )

    $payload = [ordered]@{
        status = "failed"
        stage = $Stage
        failure_kind = $FailureKind
        message = $Message
        generated_at = (Get-Date).ToString("o")
        log_path = $LogPath
        details = $Details
    }
    Write-JsonUtf8NoBom -Path (Join-Path $OutputRoot "lane-startup-failure.json") -Payload $payload
    return $payload
}

function Invoke-ManagedLaneStartup {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [switch]$NoReload
    )

    if (-not (Test-Path $OutputRoot)) {
        New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    }

    $apiBaseUrl = Get-LocalRuntimeBaseUrl -Name "api" -HostName "127.0.0.1"
    $bridgeBaseUrl = Get-LocalRuntimeBaseUrl -Name "bridge" -HostName "127.0.0.1"
    $logPath = Join-Path $OutputRoot "lane-startup.log"
    $startScript = Join-Path $RepoRoot "start.ps1"
    $apiCheckScript = Join-Path $PSScriptRoot "api\check.ps1"
    $bridgeCheckScript = Join-Path $PSScriptRoot "bridge\check.ps1"

    Add-ManagedLaneStartupLogLine -LogPath $logPath -Message "managed-lane-startup begin api=$apiBaseUrl bridge=$bridgeBaseUrl"

    try {
        Add-ManagedLaneStartupLogLine -LogPath $logPath -Message ("starting managed API + bridge lane" + ($(if ($NoReload) { " (no-reload)" } else { "" })))
        if ($NoReload) {
            & $startScript -LaneOnly -NoBrowser -ForceRestartApi -ForceRestartBridge -NoReload
        } else {
            & $startScript -LaneOnly -NoBrowser -ForceRestartApi -ForceRestartBridge
        }
        if (-not $?) {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "lane_startup" `
                -FailureKind "lane_start_failed" `
                -Message "Managed API + bridge lane failed to start."
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        Add-ManagedLaneStartupLogLine -LogPath $logPath -Message "checking API runtime contract"
        & $apiCheckScript
        if (-not $?) {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "api_contract" `
                -FailureKind "api_contract_failed" `
                -Message "API runtime contract check failed."
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        Add-ManagedLaneStartupLogLine -LogPath $logPath -Message "checking bridge runtime contract"
        & $bridgeCheckScript
        if (-not $?) {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "bridge_contract" `
                -FailureKind "bridge_contract_failed" `
                -Message "Bridge runtime contract check failed."
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        Add-ManagedLaneStartupLogLine -LogPath $logPath -Message "checking /api/lab/status promotion safety"
        $apiHeaders = @{}
        $apiKey = [string](Get-RepoEnvValue -RepoRoot $RepoRoot -Name "PIPELINE_API_KEY")
        if ($apiKey) {
            $apiHeaders["X-Pipeline-Key"] = $apiKey
        }

        try {
            $labStatus = Invoke-RestMethod -Uri "$apiBaseUrl/api/lab/status" -Headers $apiHeaders -TimeoutSec 10
        } catch {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "lab_status" `
                -FailureKind "lab_status_request_failed" `
                -Message "Failed to query /api/lab/status." `
                -Details @{ exception = $_.Exception.Message }
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        if ([string]$labStatus.status -ne "valid") {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "lab_status" `
                -FailureKind "lab_status_invalid" `
                -Message "/api/lab/status was not valid." `
                -Details @{ status = [string]$labStatus.status }
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        if (-not [bool]$labStatus.lane_validity.promotion_safe) {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "lab_status" `
                -FailureKind "promotion_not_safe" `
                -Message "/api/lab/status lane_validity.promotion_safe was false." `
                -Details @{ status = [string]$labStatus.status }
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }

        Add-ManagedLaneStartupLogLine -LogPath $logPath -Message "managed-lane-startup passed"
        $packet = [ordered]@{
            status = "passed"
            startup_mode = $(if ($NoReload) { "managed_lane_no_reload" } else { "managed_lane" })
            no_reload = [bool]$NoReload
            generated_at = (Get-Date).ToString("o")
            api_base_url = $apiBaseUrl
            bridge_base_url = $bridgeBaseUrl
            start_wrapper = $startScript
            api_contract_check = @{
                status = "passed"
                script = $apiCheckScript
            }
            bridge_contract_check = @{
                status = "passed"
                script = $bridgeCheckScript
            }
            lab_status = $labStatus
            promotion_safe = [bool]$labStatus.lane_validity.promotion_safe
            log_path = $logPath
        }
        $packetPath = Join-Path $OutputRoot "lane-startup.json"
        Write-JsonUtf8NoBom -Path $packetPath -Payload $packet
        return @{
            output_root = $OutputRoot
            packet_path = $packetPath
            log_path = $logPath
            packet = $packet
        }
    } catch {
        if (-not (Test-Path (Join-Path $OutputRoot "lane-startup-failure.json"))) {
            $failure = Write-ManagedLaneStartupFailurePacket `
                -OutputRoot $OutputRoot `
                -LogPath $logPath `
                -Stage "managed_lane_startup" `
                -FailureKind "managed_lane_startup_failed" `
                -Message $_.Exception.Message
            throw ($failure | ConvertTo-Json -Depth 8 -Compress)
        }
        throw
    }
}
