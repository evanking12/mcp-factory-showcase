<#
.SYNOPSIS
    Starts all MCP Factory local services in separate PowerShell windows:
      - GUI/DLL Bridge   (port 8090)  -- DLL ctypes calls, GUI UIA walks, COM
      - Pipeline API     (port 8201)  -- FastAPI discovery + explore + generate
      - Web UI           (port 8080)  -- upload wizard, chat, session viewer
      - Dashboard        (port 8082)  -- GitLab-style pipeline monitor (NEW)

    All windows stay open and stream logs. Close them to stop services.

.PARAMETER NoBridge
    Skip starting the bridge. Discovery still works; DLL/GUI tool EXECUTION
    won't (you'll get 503 on /execute calls from the chat UI).

.PARAMETER NoBrowser
    Don't auto-open http://localhost:8082/simple once the API is healthy.

.PARAMETER NoReload
    Disable uvicorn --reload (faster startup, no auto-restart on file changes).

.PARAMETER ApiOnly
    Start only the pipeline API. Implies -NoBridge and -NoBrowser.

.PARAMETER LaneOnly
    Start only the GUI/DLL bridge plus pipeline API. Implies -NoBrowser and
    skips the UI and dashboard.

.PARAMETER BridgeOnly
    Start only the GUI/DLL bridge. Implies -NoBrowser and skips the API, UI,
    and dashboard.

.PARAMETER ForceRestartApi
    Stop and relaunch the managed MCP Factory API lane before startup checks
    continue. Unknown API port owners still fail safe.

.PARAMETER ForceRestartBridge
    Stop and relaunch the managed MCP Factory bridge lane before startup checks
    continue. Unknown bridge port owners still fail safe.

.EXAMPLE
    .\start.ps1
    .\start.ps1 -NoBridge
    .\start.ps1 -BridgeOnly -ForceRestartBridge
    .\start.ps1 -NoReload -NoBrowser
#>

param(
    [switch]$NoBridge,
    [switch]$NoBrowser,
    [switch]$NoReload,
    [switch]$ApiOnly,
    [switch]$LaneOnly,
    [switch]$BridgeOnly,
    [switch]$ForceRestartApi,
    [switch]$ForceRestartBridge
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (($ApiOnly -and $BridgeOnly) -or ($LaneOnly -and ($ApiOnly -or $BridgeOnly))) {
    Write-Err "Use exactly one of -ApiOnly, -LaneOnly, or -BridgeOnly."
    exit 1
}
if ($ApiOnly) { $NoBridge = $true; $NoBrowser = $true }
if ($LaneOnly) { $NoBrowser = $true }
if ($BridgeOnly) { $NoBrowser = $true }
$SkipApi = $BridgeOnly
$SkipUi = $ApiOnly -or $BridgeOnly -or $LaneOnly

$Root    = $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
$VenvDir = Join-Path $Root ".venv"
$VenvPy  = Join-Path $VenvDir "Scripts\python.exe"
$RuntimeContractModule = Join-Path $Root "runtime\_runtime_contract.ps1"

# Full paths to venv executables -- no activation needed in child windows
$Uvicorn    = Join-Path $VenvDir "Scripts\uvicorn.exe"
$EscRoot    = $Root -replace "'", "''"       # path safe for single-quoted PS strings
$EscVenvPy  = $VenvPy -replace "'", "''"
. $RuntimeContractModule

$apiRuntime = Get-LocalRuntimeSystem -Name "api"
$bridgeRuntime = Get-LocalRuntimeSystem -Name "bridge"
$apiRuntimeRole = [string]$apiRuntime.role
$apiRuntimeComponent = [string]$apiRuntime.component
$bridgeRuntimeRole = [string]$bridgeRuntime.role
$bridgeRuntimeComponent = [string]$bridgeRuntime.component
$apiAlivePath = if ($apiRuntime.alive_path) { [string]$apiRuntime.alive_path } else { "/alive" }
$apiHealthPath = if ($apiRuntime.health_path) { [string]$apiRuntime.health_path } else { "/health" }
$apiIdentityPath = if ($apiRuntime.identity_path) { [string]$apiRuntime.identity_path } else { "/identity" }
$apiReadinessPath = if ($apiRuntime.readiness_path) { [string]$apiRuntime.readiness_path } else { "/readiness" }
$apiAdmissionPath = Get-LocalRuntimeAdmissionPath -Name "api"
$bridgeAlivePath = if ($bridgeRuntime.alive_path) { [string]$bridgeRuntime.alive_path } else { "/alive" }
$bridgeHealthPath = if ($bridgeRuntime.health_path) { [string]$bridgeRuntime.health_path } else { "/health" }
$bridgeIdentityPath = if ($bridgeRuntime.identity_path) { [string]$bridgeRuntime.identity_path } else { "/identity" }
$bridgeReadinessPath = if ($bridgeRuntime.readiness_path) { [string]$bridgeRuntime.readiness_path } else { "/readiness" }
$bridgeAdmissionPath = Get-LocalRuntimeAdmissionPath -Name "bridge"
$runtimeTrustContractVersion = [string](Get-LocalRuntimeContract).trust_contract_version
$bridgeRequiredCapabilities = @($bridgeRuntime.required_capabilities | ForEach-Object { [string]$_ })

# ── Pretty output helpers ────────────────────────────────────────────────────

function Write-Banner {
    Write-Host ""
    Write-Host "  +-----------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |      MCP Factory  --  Start Services    |" -ForegroundColor Cyan
    Write-Host "  +-----------------------------------------+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info  { param([string]$msg) Write-Host "  [>] $msg" -ForegroundColor Cyan }
function Write-OK    { param([string]$msg) Write-Host "  [+] $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$msg) Write-Host "  [X] $msg" -ForegroundColor Red }

function Normalize-CommandMarkerText {
    param([string]$Text)
    if (-not $Text) { return "" }
    $normalized = $Text.ToLowerInvariant().Replace('/', '\')
    while ($normalized.Contains('\\')) {
        $normalized = $normalized.Replace('\\', '\')
    }
    return $normalized
}

Write-Banner

# ── Pre-flight checks ────────────────────────────────────────────────────────

if (-not (Test-Path $VenvPy)) {
    Write-Host "  [X] Virtual environment not found at: $VenvPy" -ForegroundColor Red
    Write-Host "      Run  .\setup.ps1  first." -ForegroundColor Gray
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "  [X] .env not found." -ForegroundColor Red
    Write-Host "      Run  .\setup.ps1  first." -ForegroundColor Gray
    exit 1
}

if (-not (Test-Path $Uvicorn)) {
    Write-Host "  [X] uvicorn not found at: $Uvicorn" -ForegroundColor Red
    Write-Host "      Run:  .venv\Scripts\pip install uvicorn[standard]" -ForegroundColor Gray
    exit 1
}

# ── Load .env ────────────────────────────────────────────────────────────────

Write-Info "Loading .env..."

$envVars = @{}
foreach ($line in Get-Content $EnvFile) {
    $line = $line.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { continue }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { continue }
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()
    # Strip surrounding quotes if present
    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or
        ($val.StartsWith("'") -and $val.EndsWith("'"))) {
        $val = $val.Substring(1, $val.Length - 2)
    }
    $envVars[$key] = $val
}

# Soft warnings -- don't block startup, just let the user know
$openAIKey    = $envVars['OPENAI_API_KEY']
$bridgeSecret = $envVars['GUI_BRIDGE_SECRET']
$storageMode  = if ($envVars['MCP_STORAGE_BACKEND']) { $envVars['MCP_STORAGE_BACKEND'] } else { 'local' }

if (-not $openAIKey -or $openAIKey -match '^sk-\.\.\.' -or $openAIKey -eq 'sk-YOUR-KEY-HERE') {
    Write-Warn "OPENAI_API_KEY looks like a placeholder -- LLM features won't work."
    Write-Warn "Edit .env and restart with .\start.ps1"
}
if (-not $bridgeSecret -or $bridgeSecret.Trim() -eq '') {
    Write-Warn "GUI_BRIDGE_SECRET is empty -- bridge auth will fail. Set it in .env."
}

Write-OK ".env loaded  ($($envVars.Count) variables)"
function Get-PortOwnerInfo {
    param([int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = ""
    $startTime = $null
    if ($proc) {
        $commandLine = [string]$proc.CommandLine
        if ($proc.CreationDate) {
            try {
                $startTime = [System.Management.ManagementDateTimeConverter]::ToDateTime($proc.CreationDate)
            } catch {
                $startTime = $null
            }
        }
    }
    [pscustomobject]@{
        Port        = $Port
        ProcessId   = $listener.OwningProcess
        Name        = if ($proc) { [string]$proc.Name } else { "unknown" }
        CommandLine = $commandLine
        StartTime   = $startTime
    }
}

function Test-ManagedPortOwner {
    param(
        [object]$PortInfo,
        [string]$Marker
    )
    if (-not $PortInfo) {
        return $false
    }
    $normalizedCommand = Normalize-CommandMarkerText -Text ([string]$PortInfo.CommandLine)
    $normalizedMarker = Normalize-CommandMarkerText -Text $Marker
    if ($normalizedCommand -like "*$normalizedMarker*") {
        return $true
    }
    return (@(Get-ManagedPowerShellControllers -Marker $Marker)).Count -gt 0
}

function Get-ProcessChain {
    param([int]$ProcessId)
    $chain = @()
    $seen = @{}
    $currentId = $ProcessId
    while ($currentId -gt 0 -and -not $seen.ContainsKey($currentId)) {
        $seen[$currentId] = $true
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $currentId" -ErrorAction SilentlyContinue
        if (-not $proc) {
            break
        }
        $chain += $proc
        $parentId = 0
        try {
            $parentId = [int]($proc.ParentProcessId)
        } catch {
            $parentId = 0
        }
        if ($parentId -le 0) {
            break
        }
        $currentId = $parentId
    }
    return $chain
}

function Test-EncodedCommandContainsMarker {
    param(
        [string]$CommandLine,
        [string]$Marker
    )
    if (-not $CommandLine -or -not $Marker) {
        return $false
    }
    $match = [regex]::Match($CommandLine, '-EncodedCommand\s+([A-Za-z0-9+/=]+)')
    if (-not $match.Success) {
        return $false
    }
    try {
        $decoded = [System.Text.Encoding]::Unicode.GetString(
            [Convert]::FromBase64String($match.Groups[1].Value)
        )
        $normalizedDecoded = Normalize-CommandMarkerText -Text $decoded
        $normalizedMarker = Normalize-CommandMarkerText -Text $Marker
        return $normalizedDecoded -like "*$normalizedMarker*"
    } catch {
        return $false
    }
}

function Get-ManagedPowerShellControllers {
    param([string]$Marker)
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    return @(
        $all | Where-Object {
            [string]$_.Name -eq "powershell.exe" -and
            (Test-EncodedCommandContainsMarker -CommandLine ([string]$_.CommandLine) -Marker $Marker)
        }
    )
}

function Get-ProcessDescendants {
    param([int[]]$RootProcessIds)
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $seen = @{}
    foreach ($procId in $RootProcessIds) {
        if ($procId -gt 0 -and -not $seen.ContainsKey($procId)) {
            $seen[$procId] = $true
            $queue.Enqueue($procId)
        }
    }
    $descendants = @()
    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()
        $children = $all | Where-Object { [int]($_.ParentProcessId) -eq $parentId }
        foreach ($child in $children) {
            $childPid = [int]$child.ProcessId
            if (-not $seen.ContainsKey($childPid)) {
                $seen[$childPid] = $true
                $descendants += $child
                $queue.Enqueue($childPid)
            }
        }
    }
    return $descendants
}

function Get-ManagedStopCandidates {
    param(
        [object]$PortInfo,
        [string]$Marker
    )
    if (-not $PortInfo) {
        return @()
    }
    $chain = @(Get-ProcessChain -ProcessId $PortInfo.ProcessId)
    $serviceNames = @("python.exe", "uvicorn.exe", "powershell.exe")
    $serviceChain = @(
        $chain | Where-Object {
            $serviceNames -contains [string]$_.Name
        }
    )
    $rootIds = @($serviceChain | ForEach-Object { [int]$_.ProcessId })
    if (-not $rootIds) {
        $rootIds = @([int]$PortInfo.ProcessId)
    }
    $controllers = @(Get-ManagedPowerShellControllers -Marker $Marker)
    if ($controllers) {
        $rootIds += @($controllers | ForEach-Object { [int]$_.ProcessId })
    }
    $descendants = @(Get-ProcessDescendants -RootProcessIds $rootIds)
    $candidates = @($serviceChain + $controllers + $descendants)
    $unique = @{}
    foreach ($candidate in $candidates) {
        $candidateId = [int]$candidate.ProcessId
        if ($candidateId -gt 0 -and -not $unique.ContainsKey($candidateId)) {
            $unique[$candidateId] = $candidate
        }
    }
    return @($unique.Values)
}

function Stop-ManagedPortOwner {
    param(
        [object]$PortInfo,
        [string]$ServiceName,
        [string]$Marker
    )
    if (-not $PortInfo) {
        return $true
    }
    if (-not (Test-ManagedPortOwner -PortInfo $PortInfo -Marker $Marker)) {
        Write-Err "$ServiceName cannot be force-restarted because port $($PortInfo.Port) is owned by an unmanaged process."
        if ($PortInfo.CommandLine) {
            Write-Host "      $($PortInfo.CommandLine)" -ForegroundColor Gray
        } elseif ((@(Get-ManagedPowerShellControllers -Marker $Marker)).Count -gt 0) {
            Write-Host "      Managed controller windows were found, but the direct port owner command line was unavailable." -ForegroundColor Gray
        }
        return $false
    }
    Write-Warn "Stopping managed $ServiceName on port $($PortInfo.Port) (PID $($PortInfo.ProcessId)) before relaunch."
    $stopCandidates = @(Get-ManagedStopCandidates -PortInfo $PortInfo -Marker $Marker)
    if (-not $stopCandidates) {
        $stopCandidates = @($PortInfo)
    }
    $orderedStops = @(
        $stopCandidates |
            Sort-Object @{ Expression = { [int]($_.ProcessId) }; Descending = $true }
    )
    foreach ($candidate in $orderedStops) {
        $candidatePid = [int]$candidate.ProcessId
        try {
            Stop-Process -Id $candidatePid -Force -ErrorAction Stop
        } catch {
            # Ignore already-exited members of the managed family.
        }
    }
    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 500
        $owner = Get-PortOwnerInfo -Port $PortInfo.Port
        if (-not $owner) {
            return $true
        }
    } while ((Get-Date) -lt $deadline)
    Write-Err "$ServiceName did not release port $($PortInfo.Port) within 15 seconds."
    return $false
}

function Invoke-JsonProbe {
    param(
        [string]$Url,
        [hashtable]$Headers = @{}
    )
    try {
        $resp = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) {
            return $null
        }
        if (-not $resp.Content) {
            return [pscustomobject]@{}
        }
        return ($resp.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Test-ApiLaneContract {
    param(
        [string]$BaseUrl,
        [bool]$RequireReady = $true
    )
    $admissionPath = Get-LocalRuntimeAdmissionPath -Name "api"
    $admission = Invoke-JsonProbe -Url "$BaseUrl$admissionPath"
    if (-not $admission) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "local_lane_admission_unavailable"
            Identity  = $null
            Readiness = $null
            Admission = $null
        }
    }
    if ($admission.component -ne $apiRuntimeComponent) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "identity_component_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    if ($admission.role -ne $apiRuntimeRole) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "identity_role_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    if ($admission.contract_version -ne "local_lane_admission_v1") {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "local_lane_admission_version_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    $ready = [bool]$admission.admitted
    if ($RequireReady -and -not $ready) {
        $reason = if (@($admission.blocking_reasons).Count -gt 0) {
            "local_lane_admission_red:$([string]$admission.blocking_reasons[0])"
        } else {
            "local_lane_admission_red"
        }
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = $reason
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    return [pscustomobject]@{
        Valid     = $true
        Ready     = $ready
        Reason    = if ($ready) { "ready" } else { "local_lane_admission_degraded" }
        Identity  = $null
        Readiness = $null
        Admission = $admission
    }
}

function Test-BridgeLaneContract {
    param(
        [string]$BaseUrl,
        [string]$BridgeKey
    )
    $headers = @{}
    if ($BridgeKey) {
        $headers["X-Bridge-Key"] = $BridgeKey
    }
    $admissionPath = Get-LocalRuntimeAdmissionPath -Name "bridge"
    $admission = Invoke-JsonProbe -Url "$BaseUrl$admissionPath" -Headers $headers
    if (-not $admission) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "local_lane_admission_unavailable"
            Identity  = $null
            Readiness = $null
            Admission = $null
        }
    }
    if ($admission.component -ne $bridgeRuntimeComponent) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "identity_component_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    if ($admission.role -ne $bridgeRuntimeRole) {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "identity_role_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    if ($admission.contract_version -ne "local_lane_admission_v1") {
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = "local_lane_admission_version_mismatch"
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    $ready = [bool]$admission.admitted
    if (-not $ready) {
        $reason = if (@($admission.blocking_reasons).Count -gt 0) {
            "local_lane_admission_red:$([string]$admission.blocking_reasons[0])"
        } else {
            "local_lane_admission_red"
        }
        return [pscustomobject]@{
            Valid     = $false
            Ready     = $false
            Reason    = $reason
            Identity  = $null
            Readiness = $null
            Admission = $admission
        }
    }
    return [pscustomobject]@{
        Valid     = $true
        Ready     = $true
        Reason    = "ready"
        Identity  = $null
        Readiness = $null
        Admission = $admission
    }
}

function Start-ApiMonitorWindow {
    param(
        [int]$Port,
        [string]$Marker
    )
    $escMarker = $Marker -replace "'", "''"
    $monitorCommands = @"
function Get-PortOwnerInfo {
    param([int]`$Port)
    `$listener = Get-NetTCPConnection -State Listen -LocalPort `$Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not `$listener) { return `$null }
    `$proc = Get-CimInstance Win32_Process -Filter "ProcessId = `$(`$listener.OwningProcess)" -ErrorAction SilentlyContinue
    `$commandLine = ""
    `$startTime = `$null
    if (`$proc) {
        `$commandLine = [string]`$proc.CommandLine
        if (`$proc.CreationDate) {
            try {
                `$startTime = [System.Management.ManagementDateTimeConverter]::ToDateTime(`$proc.CreationDate)
            } catch {
                `$startTime = `$null
            }
        }
    }
    [pscustomobject]@{
        Port = `$Port
        ProcessId = `$listener.OwningProcess
        Name = if (`$proc) { [string]`$proc.Name } else { "unknown" }
        CommandLine = `$commandLine
        StartTime = `$startTime
    }
}

while (`$true) {
    `$owner = Get-PortOwnerInfo -Port $Port
    `$now = Get-Date
    if (-not `$owner) {
        Write-Host "[`$(`$now.ToString('s'))] API :$Port unavailable" -ForegroundColor Yellow
    } else {
        `$managed = `$false
        if (`$owner.CommandLine) {
            `$normalizedCommand = ([string]`$owner.CommandLine).ToLowerInvariant().Replace('/', '\')
            while (`$normalizedCommand.Contains('\\')) {
                `$normalizedCommand = `$normalizedCommand.Replace('\\', '\')
            }
            `$normalizedMarker = ('$escMarker').ToLowerInvariant().Replace('/', '\')
            while (`$normalizedMarker.Contains('\\')) {
                `$normalizedMarker = `$normalizedMarker.Replace('\\', '\')
            }
            `$managed = (`$normalizedCommand -like "*`$normalizedMarker*")
        }
        `$age = 'unknown'
        if (`$owner.StartTime) {
            `$age = [string]([math]::Round((New-TimeSpan -Start `$owner.StartTime -End `$now).TotalMinutes, 1)) + ' min'
        }
        `$started = if (`$owner.StartTime) { `$owner.StartTime.ToString('s') } else { 'unknown' }
        Write-Host "[`$(`$now.ToString('s'))] API :$Port pid=`$(`$owner.ProcessId) started=`$started age=`$age managed=`$managed" -ForegroundColor Cyan
    }
    Start-Sleep -Seconds 300
}
"@
    Start-ServiceWindow -Title "MCP Factory  |  API Monitor :$Port" -Commands $monitorCommands
}

function Test-PortAvailability {
    param(
        [int]$Port,
        [string]$ServiceName,
        [string]$Marker,
        [string]$HealthUrl = "",
        [ValidateSet("none", "api", "bridge")]
        [string]$ContractMode = "none",
        [bool]$RequireReady = $false,
        [string]$SharedSecret = ""
    )
    $owner = Get-PortOwnerInfo -Port $Port
    if (-not $owner) {
        return [pscustomobject]@{
            Available       = $true
            Reuse           = $false
            Owner           = $null
            RestartRequired = $false
            ContractReason  = ""
        }
    }
    $contractResult = $null
    if ($ContractMode -eq "api") {
        $contractResult = Test-ApiLaneContract -BaseUrl "http://localhost:$Port" -RequireReady:$RequireReady
    } elseif ($ContractMode -eq "bridge") {
        $contractResult = Test-BridgeLaneContract -BaseUrl "http://localhost:$Port" -BridgeKey $SharedSecret
    }
    if ($contractResult -and $contractResult.Valid) {
        Write-Warn "$ServiceName on port $Port passed contract check ($($contractResult.Reason)). Reusing it."
        return [pscustomobject]@{
            Available       = $false
            Reuse           = $true
            Owner           = $owner
            RestartRequired = $false
            ContractReason  = [string]$contractResult.Reason
        }
    }
    if ($contractResult -and -not $contractResult.Valid -and (Test-ManagedPortOwner -PortInfo $owner -Marker $Marker)) {
        Write-Warn "$ServiceName on port $Port is managed but failed contract check ($($contractResult.Reason)). Restarting it."
        return [pscustomobject]@{
            Available       = $true
            Reuse           = $false
            Owner           = $owner
            RestartRequired = $true
            ContractReason  = [string]$contractResult.Reason
        }
    }
    if ($HealthUrl) {
        try {
            $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Warn "$ServiceName on port $Port is already healthy. Reusing it."
                return [pscustomobject]@{
                    Available       = $false
                    Reuse           = $true
                    Owner           = $owner
                    RestartRequired = $false
                    ContractReason  = "health_only"
                }
            }
        } catch {}
    }
    if (Test-ManagedPortOwner -PortInfo $owner -Marker $Marker) {
        Write-Warn "$ServiceName on port $Port is already running under MCP Factory (PID $($owner.ProcessId)). Reusing it."
        return [pscustomobject]@{
            Available       = $false
            Reuse           = $true
            Owner           = $owner
            RestartRequired = $false
            ContractReason  = if ($contractResult) { [string]$contractResult.Reason } else { "" }
        }
    }
    Write-Err "$ServiceName cannot start because port $Port is already owned by PID $($owner.ProcessId) [$($owner.Name)]."
    if ($owner.CommandLine) {
        Write-Host "      $($owner.CommandLine)" -ForegroundColor Gray
    } else {
        Write-Host "      No command line was available for the owning process." -ForegroundColor Gray
    }
    return [pscustomobject]@{
        Available       = $false
        Reuse           = $false
        Owner           = $owner
        RestartRequired = $false
        ContractReason  = if ($contractResult) { [string]$contractResult.Reason } else { "" }
    }
}

function Warn-OnLegacyApiLane {
    param(
        [int]$PrimaryPort,
        [int]$LegacyPort = 8001
    )
    if ($PrimaryPort -eq $LegacyPort) {
        return
    }
    $legacyOwner = Get-PortOwnerInfo -Port $LegacyPort
    if (-not $legacyOwner) {
        return
    }
    $legacyContract = Test-ApiLaneContract -BaseUrl "http://127.0.0.1:$LegacyPort" -RequireReady:$false
    if ($legacyContract -and $legacyContract.Valid) {
        Write-Warn "A second local pipeline API is active on port $LegacyPort. Local runner defaults now target http://127.0.0.1:$PrimaryPort; stop the legacy lane to avoid ambiguous runs."
    }
}

$bridgePort = Get-LocalRuntimePort -Name "bridge"
$apiPort = Get-LocalRuntimePort -Name "api"
$dashboardPort = if ($env:DASHBOARD_PORT) { [int]$env:DASHBOARD_PORT } else { 8082 }
$canonicalBridgePort = [int]$bridgeRuntime.port
$canonicalApiPort = [int]$apiRuntime.port
if ($bridgePort -ne $canonicalBridgePort) {
    Write-Warn "Bridge port override active: canonical=$canonicalBridgePort effective=$bridgePort"
}
if ($apiPort -ne $canonicalApiPort) {
    Write-Warn "API port override active: canonical=$canonicalApiPort effective=$apiPort"
}
$apiBaseUrl = Get-LocalRuntimeBaseUrl -Name "api" -HostName "127.0.0.1"
$bridgeBaseUrl = Get-LocalRuntimeBaseUrl -Name "bridge" -HostName "127.0.0.1"
$dashboardBaseUrl = "http://localhost:$dashboardPort"
$bridgeCheck = $null
if (-not $NoBridge) {
    $bridgeCheck = Test-PortAvailability -Port $bridgePort -ServiceName "Bridge" -Marker "scripts\\bridge\\gui_bridge.py" -ContractMode "bridge" -SharedSecret $bridgeSecret
    if ($ForceRestartBridge -or $bridgeCheck.RestartRequired) {
        if ($bridgeCheck.Owner) {
            $restartOk = Stop-ManagedPortOwner -PortInfo $bridgeCheck.Owner -ServiceName "Bridge" -Marker "scripts\\bridge\\gui_bridge.py"
            if (-not $restartOk) {
                exit 1
            }
        }
        $bridgeCheck = [pscustomobject]@{
            Available = $true
            Reuse     = $false
            Owner     = $null
        }
    }
    if (-not $bridgeCheck.Available -and -not $bridgeCheck.Reuse) {
        exit 1
    }
}

$apiCheck = $null
if (-not $SkipApi) {
    $apiRequireReady = (-not $NoBridge) -and (-not $ForceRestartBridge) -and (-not ($bridgeCheck -and $bridgeCheck.RestartRequired))
    $apiCheck = Test-PortAvailability -Port $apiPort -ServiceName "Pipeline API" -Marker "api.routes.main:app --host 0.0.0.0 --port $apiPort" -ContractMode "api" -RequireReady:$apiRequireReady
    if ($ForceRestartApi -or $apiCheck.RestartRequired) {
        if ($apiCheck.Owner) {
            $restartOk = Stop-ManagedPortOwner -PortInfo $apiCheck.Owner -ServiceName "Pipeline API" -Marker "api.routes.main:app --host 0.0.0.0 --port $apiPort"
            if (-not $restartOk) {
                exit 1
            }
        }
        $apiCheck = [pscustomobject]@{
            Available = $true
            Reuse     = $false
            Owner     = $null
        }
    }
    if (-not $apiCheck.Available -and -not $apiCheck.Reuse) {
        exit 1
    }
    Warn-OnLegacyApiLane -PrimaryPort $apiPort
}

$uiCheck = $null
$dashCheck = $null
if (-not $SkipUi) {
    $uiCheck = Test-PortAvailability -Port 8080 -ServiceName "Web UI" -Marker "ui.main:app --host 0.0.0.0 --port 8080"
    if (-not $uiCheck.Available -and -not $uiCheck.Reuse) {
        exit 1
    }
    $dashCheck = Test-PortAvailability -Port $dashboardPort -ServiceName "Dashboard" -Marker "dashboard.main:app --host 0.0.0.0 --port $dashboardPort"
    if (-not $dashCheck.Available -and -not $dashCheck.Reuse) {
        exit 1
    }
}

# ── Build env-assignment block for child windows ─────────────────────────────
# Each spawned PowerShell window gets all vars from .env set before the service starts.

$envBlock = ($envVars.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $escapedVal = $_.Value -replace "'", "''"
    "`$env:$($_.Name) = '$escapedVal'"
}) -join "`n"

$reloadArg = if ($NoReload) { "" } else { "--reload" }
$apiReloadMode = if ($NoReload) { "disabled" } else { "enabled" }
$escUvicorn = $Uvicorn -replace "'", "''"

# ── Helper: spawn a labelled PowerShell window ───────────────────────────────
# Uses -EncodedCommand so paths with spaces and special chars survive correctly.

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$Commands    # PowerShell lines to execute inside the window
    )
    $escapedTitle = $Title -replace "'", "''"

    # Full script that will run in the child window
    $childScript = @"
`$Host.UI.RawUI.WindowTitle = '$escapedTitle'
Set-Location '$EscRoot'
$Commands
"@
    $bytes   = [System.Text.Encoding]::Unicode.GetBytes($childScript)
    $encoded = [Convert]::ToBase64String($bytes)
    Start-Process powershell.exe -ArgumentList "-NoExit", "-EncodedCommand", $encoded
}

# ── Service 1: GUI/DLL Bridge (port 8090) ────────────────────────────────────

if (-not $NoBridge) {
    if ($bridgeCheck -and $bridgeCheck.Reuse) {
        Write-OK "Bridge reuse active on port $bridgePort"
    } else {
        Write-Info "Starting GUI/DLL bridge on port $bridgePort..."

        $escBridgeSecret = ($bridgeSecret -replace "'", "''")
        $bridgePortText  = [string]$bridgePort
        $escBridgePy     = (Join-Path $Root "scripts\bridge\gui_bridge.py") -replace "'", "''"

        $bridgeCommands = @"
$envBlock
# Bridge reads BRIDGE_SECRET (not GUI_BRIDGE_SECRET -- start.ps1 maps them here)
`$env:BRIDGE_SECRET = '$escBridgeSecret'
`$env:BRIDGE_PORT   = '$bridgePortText'
`$env:PYTHONPATH    = '$EscRoot'

Write-Host "  Bridge secret  : [configured]" -ForegroundColor DarkGray
Write-Host "  Bridge port    : `$env:BRIDGE_PORT" -ForegroundColor DarkGray
Write-Host "  PYTHONPATH     : `$env:PYTHONPATH" -ForegroundColor DarkGray
Write-Host ""

& '$EscVenvPy' '$escBridgePy'
"@

        Start-ServiceWindow -Title "MCP Factory  |  Bridge :$bridgePort" -Commands $bridgeCommands
        Write-OK "Bridge window opened"
        Start-Sleep -Milliseconds 1200     # give the bridge a head start before the API tries to reach it
    }
}

# ── Service 2: Pipeline API (port 8201) ──────────────────────────────────────

if (-not $SkipApi) {
    if ($apiCheck.Reuse) {
        Write-OK "API reuse active on port $apiPort"
    } else {
        Write-Info "Starting pipeline API on port $apiPort..."

$apiCommands = @"
$envBlock
`$env:MCP_API_RELOAD_MODE = '$apiReloadMode'

Write-Host "  Storage mode   : `$env:MCP_STORAGE_BACKEND" -ForegroundColor DarkGray
Write-Host "  Explore model  : `$env:OPENAI_EXPLORE_MODEL" -ForegroundColor DarkGray
Write-Host "  Bridge URL     : `$env:GUI_BRIDGE_URL" -ForegroundColor DarkGray
Write-Host "  Reload mode    : `$env:MCP_API_RELOAD_MODE" -ForegroundColor DarkGray
Write-Host ""

& '$EscVenvPy' -m uvicorn api.routes.main:app --host 0.0.0.0 --port $apiPort $reloadArg
"@

        Start-ServiceWindow -Title "MCP Factory  |  API :$apiPort" -Commands $apiCommands
        Write-OK "API window opened"
        Start-Sleep -Milliseconds 800
    }
    if (-not $ForceRestartApi) {
        Start-ApiMonitorWindow -Port $apiPort -Marker "api.routes.main:app --host 0.0.0.0 --port $apiPort"
        Write-OK "API monitor window opened"
    }
}

# ── Service 3: Web UI (port 8080) ────────────────────────────────────────────

if (-not $SkipUi) {
    if ($uiCheck -and $uiCheck.Reuse) {
        Write-OK "UI reuse active on port 8080"
    } else {
        Write-Info "Starting web UI on port 8080..."

        $uiCommands = @"
$envBlock
`$env:PIPELINE_URL = '$apiBaseUrl'

Write-Host "  Pipeline URL   : `$env:PIPELINE_URL" -ForegroundColor DarkGray
Write-Host ""

& '$escUvicorn' ui.main:app --host 0.0.0.0 --port 8080 $reloadArg
"@

        Start-ServiceWindow -Title "MCP Factory  |  UI :8080" -Commands $uiCommands
        Write-OK "UI window opened"
    }
}

# ── Service 4: Pipeline Dashboard ─────────────────────────────────

if (-not $SkipUi) {
    if ($dashCheck -and $dashCheck.Reuse) {
        Write-OK "Dashboard reuse active on port $dashboardPort"
    } else {
        Write-Info "Starting pipeline dashboard on port $dashboardPort..."

        $dashCommands = @"
$envBlock
`$env:PIPELINE_URL = '$apiBaseUrl'

Write-Host "  Pipeline URL   : `$env:PIPELINE_URL" -ForegroundColor DarkGray
Write-Host ""

& '$escUvicorn' dashboard.main:app --host 0.0.0.0 --port $dashboardPort $reloadArg
"@

        Start-ServiceWindow -Title "MCP Factory  |  Dashboard :$dashboardPort" -Commands $dashCommands
        Write-OK "Dashboard window opened"
    }
}

# ── Wait for API health + open browser ───────────────────────────────────────

if (-not $SkipApi) {
    Write-Host ""
    Write-Info "Waiting for authoritative API health (up to 20s)..."

    $ready       = $false
    $attempts    = 0
    $maxAttempts = 40    # 40 x 500ms = 20 seconds
    $lastBlockingReason = ""

    while (-not $ready -and $attempts -lt $maxAttempts) {
        Start-Sleep -Milliseconds 500
        $attempts++
        try {
            $resp = Invoke-WebRequest -Uri "$apiBaseUrl$apiHealthPath" `
                -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            $payload = $resp.Content | ConvertFrom-Json
            if ($resp.StatusCode -eq 200 -and $payload.healthy) {
                $ready = $true
            } elseif ($payload.blocking_reason) {
                $lastBlockingReason = [string]$payload.blocking_reason
            }
        } catch { }

        if (-not $ready -and -not $lastBlockingReason) {
            try {
                $readinessResp = Invoke-WebRequest -Uri "$apiBaseUrl$apiReadinessPath" `
                    -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($readinessResp.StatusCode -eq 200) {
                    $readinessPayload = $readinessResp.Content | ConvertFrom-Json
                    if ($readinessPayload.blocking_reason) {
                        $lastBlockingReason = [string]$readinessPayload.blocking_reason
                    }
                }
            } catch { }
        }
    }

    if ($ready) {
        if (-not $NoBrowser) {
            Write-OK "API health green after ~$([math]::Round($attempts * 0.5, 1))s -- opening browser"
            Start-Process "$dashboardBaseUrl/simple"
        } else {
            Write-OK "API health green after ~$([math]::Round($attempts * 0.5, 1))s"
        }
    } else {
        if ($lastBlockingReason) {
            Write-Warn "API health stayed red: $lastBlockingReason"
            Write-Warn "Check $apiBaseUrl$apiAdmissionPath and $apiBaseUrl$apiReadinessPath before launching local runs."
        } else {
            Write-Warn "API health did not turn green within 20s."
            Write-Warn "Check $apiBaseUrl$apiAdmissionPath and $apiBaseUrl$apiReadinessPath before launching local runs."
        }
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  Services launched:" -ForegroundColor White
if (-not $NoBridge) {
    Write-Host "    Bridge     ->  $bridgeBaseUrl   (alive: $bridgeAlivePath, health: $bridgeHealthPath, identity: $bridgeIdentityPath, readiness: $bridgeReadinessPath, admission: $bridgeAdmissionPath)" -ForegroundColor Gray
}
if (-not $SkipApi) {
    Write-Host "    API        ->  $apiBaseUrl   (alive: $apiAlivePath, health: $apiHealthPath, identity: $apiIdentityPath, readiness: $apiReadinessPath, admission: $apiAdmissionPath)" -ForegroundColor Gray
}
if (-not $SkipUi) {
    Write-Host "    UI         ->  http://localhost:8080   (upload / discover / chat)" -ForegroundColor Gray
    Write-Host "    Dashboard  ->  $dashboardBaseUrl/simple   (pipeline monitor) ← opens in browser" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "  Storage mode : $storageMode" -ForegroundColor Gray
if ($storageMode -eq 'local') {
    Write-Host "  Artifacts    : $Root\local-data\" -ForegroundColor Gray
}
Write-Host ""
Write-Host "  To stop: close the 'MCP Factory' PowerShell windows." -ForegroundColor DarkGray
Write-Host "  To restart: run  .\start.ps1  again." -ForegroundColor DarkGray
Write-Host ""
