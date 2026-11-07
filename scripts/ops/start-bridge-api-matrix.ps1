param(
    [int]$BridgeBasePort = 8190,
    [int]$ApiBasePort = 8201,
    [int]$Count = 4,
    [string]$BridgeSecret = "",
    [string]$OpenAIApiKey = "",
    [string]$OpenAIEndpoint = "",
    [string]$OpenAIExploreModel = "",
    [string]$OpenAIModel = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $BridgeSecret) {
    $BridgeSecret = [Guid]::NewGuid().ToString("N")
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) { return "" }
    $line = Get-Content $Path | Where-Object { $_ -match ("^\s*{0}\s*=" -f [regex]::Escape($Key)) } | Select-Object -First 1
    if (-not $line) { return "" }
    $parts = $line -split "=", 2
    if ($parts.Count -lt 2) { return "" }
    return $parts[1].Trim()
}

function Get-OpenApiPaths {
    param(
        [string]$BaseUrl
    )
    $candidates = @(
        "$BaseUrl/openapi.json",
        "$BaseUrl/docs/openapi.json"
    )
    foreach ($url in $candidates) {
        try {
            $doc = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5
            if ($doc -and $doc.paths) {
                return @($doc.paths.PSObject.Properties.Name)
            }
        } catch {}
    }
    return @()
}

function Test-BridgeIdentity {
    param(
        [int]$Port
    )
    $base = "http://127.0.0.1:$Port"
    try {
        $null = Invoke-RestMethod -Uri "$base/health" -Method Get -TimeoutSec 5
    } catch {
        return [PSCustomObject]@{
            ok = $false
            reason = "health_unreachable"
        }
    }
    $paths = Get-OpenApiPaths -BaseUrl $base
    if (-not $paths -or $paths.Count -eq 0) {
        return [PSCustomObject]@{
            ok = $false
            reason = "openapi_unavailable"
        }
    }
    $hasExecute = $paths -contains "/execute"
    $apiLike = $paths -contains "/api/jobs/{job_id}"
    if (-not $hasExecute) {
        return [PSCustomObject]@{
            ok = $false
            reason = "missing_execute_route"
        }
    }
    if ($apiLike) {
        return [PSCustomObject]@{
            ok = $false
            reason = "api_shaped_endpoint"
        }
    }
    return [PSCustomObject]@{
        ok = $true
        reason = "ok"
    }
}

function Test-ApiIdentity {
    param(
        [int]$Port
    )
    $base = "http://127.0.0.1:$Port"
    try {
        $null = Invoke-RestMethod -Uri "$base/health" -Method Get -TimeoutSec 5
    } catch {
        return [PSCustomObject]@{
            ok = $false
            reason = "health_unreachable"
        }
    }
    $paths = Get-OpenApiPaths -BaseUrl $base
    if (-not $paths -or $paths.Count -eq 0) {
        return [PSCustomObject]@{
            ok = $false
            reason = "openapi_unavailable"
        }
    }
    $hasJobs = $paths -contains "/api/jobs/{job_id}"
    $hasExecute = $paths -contains "/execute"
    if (-not $hasJobs) {
        return [PSCustomObject]@{
            ok = $false
            reason = "missing_api_jobs_route"
        }
    }
    if ($hasExecute -and $paths.Count -lt 15) {
        return [PSCustomObject]@{
            ok = $false
            reason = "bridge_shaped_endpoint"
        }
    }
    return [PSCustomObject]@{
        ok = $true
        reason = "ok"
    }
}

if (-not $OpenAIApiKey) {
    if ($env:OPENAI_API_KEY) {
        $OpenAIApiKey = $env:OPENAI_API_KEY
    } else {
        $OpenAIApiKey = Get-DotEnvValue -Path (Join-Path $repoRoot ".env") -Key "OPENAI_API_KEY"
    }
}
if (-not $OpenAIEndpoint) {
    if ($env:AZURE_OPENAI_ENDPOINT) {
        $OpenAIEndpoint = $env:AZURE_OPENAI_ENDPOINT
    } else {
        $OpenAIEndpoint = Get-DotEnvValue -Path (Join-Path $repoRoot ".env") -Key "AZURE_OPENAI_ENDPOINT"
    }
}
if (-not $OpenAIExploreModel) {
    if ($env:OPENAI_EXPLORE_MODEL) {
        $OpenAIExploreModel = $env:OPENAI_EXPLORE_MODEL
    } else {
        $OpenAIExploreModel = Get-DotEnvValue -Path (Join-Path $repoRoot ".env") -Key "OPENAI_DEPLOYMENT"
    }
}
if (-not $OpenAIModel) {
    if ($env:OPENAI_MODEL) {
        $OpenAIModel = $env:OPENAI_MODEL
    } else {
        $OpenAIModel = Get-DotEnvValue -Path (Join-Path $repoRoot ".env") -Key "OPENAI_DEPLOYMENT"
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path $repoRoot "sessions\matrix\$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$rows = @()

for ($i = 0; $i -lt $Count; $i++) {
    $bridgePort = $BridgeBasePort + $i
    $apiPort = $ApiBasePort + $i

    $bridgeOut = Join-Path $outDir ("bridge-" + $bridgePort + ".out.log")
    $bridgeErr = Join-Path $outDir ("bridge-" + $bridgePort + ".err.log")
    $apiOut = Join-Path $outDir ("api-" + $apiPort + ".out.log")
    $apiErr = Join-Path $outDir ("api-" + $apiPort + ".err.log")

    $bridgePy = Join-Path $repoRoot "scripts\bridge\gui_bridge.py"
    $bridgeCmd = 'set "BRIDGE_SECRET={0}" && set "BRIDGE_PORT={1}" && "{2}" "{3}"' -f $BridgeSecret, $bridgePort, $python, $bridgePy
    $bridgeProc = Start-Process -FilePath "cmd.exe" -ArgumentList @(
        "/c", $bridgeCmd
    ) -WorkingDirectory $repoRoot -RedirectStandardOutput $bridgeOut -RedirectStandardError $bridgeErr -PassThru

    Start-Sleep -Milliseconds 750

    $apiEnvParts = @(
        ('set "GUI_BRIDGE_URL=http://127.0.0.1:{0}"' -f $bridgePort),
        ('set "GUI_BRIDGE_SECRET={0}"' -f $BridgeSecret)
    )
    if ($OpenAIApiKey) { $apiEnvParts += ('set "OPENAI_API_KEY={0}"' -f $OpenAIApiKey) }
    if ($OpenAIEndpoint) { $apiEnvParts += ('set "AZURE_OPENAI_ENDPOINT={0}"' -f $OpenAIEndpoint) }
    if ($OpenAIExploreModel) { $apiEnvParts += ('set "OPENAI_EXPLORE_MODEL={0}"' -f $OpenAIExploreModel) }
    if ($OpenAIModel) { $apiEnvParts += ('set "OPENAI_MODEL={0}"' -f $OpenAIModel) }
    $apiEnvCmd = [string]::Join(" && ", $apiEnvParts)
    $apiCmd = '{0} && "{1}" -m uvicorn api.routes.main:app --host 127.0.0.1 --port {2}' -f $apiEnvCmd, $python, $apiPort
    $apiProc = Start-Process -FilePath "cmd.exe" -ArgumentList @(
        "/c", $apiCmd
    ) -WorkingDirectory $repoRoot -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru

    $rows += [PSCustomObject]@{
        bridge_port = $bridgePort
        bridge_pid = $bridgeProc.Id
        api_port = $apiPort
        api_pid = $apiProc.Id
    }
}

Start-Sleep -Seconds 3

$health = @()
foreach ($r in $rows) {
    $bridgeIdentity = Test-BridgeIdentity -Port $r.bridge_port
    $apiIdentity = Test-ApiIdentity -Port $r.api_port
    $health += [PSCustomObject]@{
        bridge_port = $r.bridge_port
        bridge_ok = [bool]$bridgeIdentity.ok
        bridge_identity_reason = [string]$bridgeIdentity.reason
        api_port = $r.api_port
        api_ok = [bool]$apiIdentity.ok
        api_identity_reason = [string]$apiIdentity.reason
    }
}

$manifest = [PSCustomObject]@{
    started_at = (Get-Date).ToString("o")
    repo_root = $repoRoot
    matrix_dir = $outDir
    bridge_secret = $BridgeSecret
    openai_api_key_configured = [bool]($OpenAIApiKey)
    azure_openai_endpoint_configured = [bool]($OpenAIEndpoint)
    openai_explore_model = $OpenAIExploreModel
    instances = $rows
    health = $health
}

$manifestPath = Join-Path $outDir "matrix-manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $manifestPath

Write-Host "Started bridge/API matrix."
Write-Host "Manifest: $manifestPath"
$rows | Format-Table -AutoSize
$health | Format-Table -AutoSize
Write-Host ("BRIDGE_SECRET={0}" -f $BridgeSecret)
