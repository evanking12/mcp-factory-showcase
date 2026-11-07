Set-StrictMode -Version Latest

$script:LocalRuntimeContractPath = Join-Path $PSScriptRoot "local-runtime-contract.json"
$script:LocalRuntimeContractCache = $null

function Get-LocalRuntimeContract {
    if (-not $script:LocalRuntimeContractCache) {
        $script:LocalRuntimeContractCache = Get-Content -Path $script:LocalRuntimeContractPath -Raw | ConvertFrom-Json
    }
    return $script:LocalRuntimeContractCache
}

function Get-LocalRuntimeSystem {
    param([Parameter(Mandatory = $true)][string]$Name)
    $contract = Get-LocalRuntimeContract
    $property = $contract.systems.PSObject.Properties | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if (-not $property) {
        throw "unknown_runtime_system:$Name"
    }
    return $property.Value
}

function Get-LocalRuntimePort {
    param([Parameter(Mandatory = $true)][string]$Name)
    $system = Get-LocalRuntimeSystem -Name $Name
    $canonicalPort = [int]$system.port
    $overrideCandidates = switch ($Name) {
        "api" { @($env:MCP_FACTORY_API_PORT, $env:API_PORT) }
        "bridge" { @($env:MCP_FACTORY_BRIDGE_PORT, $env:BRIDGE_PORT) }
        default { @() }
    }
    foreach ($candidate in $overrideCandidates) {
        $text = [string]$candidate
        if (-not $text) {
            continue
        }
        $resolved = 0
        if ([int]::TryParse($text, [ref]$resolved) -and $resolved -gt 0) {
            return $resolved
        }
    }
    return $canonicalPort
}

function Get-LocalRuntimeBaseUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$HostName = ""
    )
    $system = Get-LocalRuntimeSystem -Name $Name
    $scheme = if ($system.scheme) { [string]$system.scheme } else { "http" }
    $resolvedHost = if ($HostName) { $HostName } elseif ($system.host) { [string]$system.host } else { "127.0.0.1" }
    $port = Get-LocalRuntimePort -Name $Name
    return "${scheme}://${resolvedHost}:$port"
}

function Get-LocalRuntimeRequiredEnvKeys {
    param([string[]]$SystemNames = @("api", "bridge"))
    $keys = @()
    foreach ($name in $SystemNames) {
        $system = Get-LocalRuntimeSystem -Name $name
        foreach ($key in @($system.required_env_keys)) {
            $normalized = [string]$key
            if ($normalized -and ($keys -notcontains $normalized)) {
                $keys += $normalized
            }
        }
    }
    return $keys
}

function Get-LocalRuntimeRunnerPackets {
    $runner = Get-LocalRuntimeSystem -Name "runner"
    return @($runner.authoritative_output_packets)
}

function Get-LocalRuntimeAdmissionPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    $system = Get-LocalRuntimeSystem -Name $Name
    if ($system.local_lane_admission_path) {
        return [string]$system.local_lane_admission_path
    }
    return "/local-lane-admission"
}
