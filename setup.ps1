<#
.SYNOPSIS
    One-time setup for MCP Factory.
    Creates the virtual environment, installs all dependencies,
    scaffolds .env from the template, and optionally launches services.

.PARAMETER Force
    Re-create the virtual environment even if it already exists.

.PARAMETER NoStart
    Skip the "start services now?" prompt at the end.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -NoStart
    .\setup.ps1 -Force
#>

param(
    [switch]$Force,
    [switch]$NoStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root    = $PSScriptRoot
$VenvDir = Join-Path $Root ".venv"
$VenvPy  = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
$RuntimeContractModule = Join-Path $Root "runtime\_runtime_contract.ps1"
. $RuntimeContractModule

$runtimeEnvKeys = @(Get-LocalRuntimeRequiredEnvKeys)
$bridgeBaseUrl = Get-LocalRuntimeBaseUrl -Name "bridge" -HostName "127.0.0.1"

# â”€â”€ Pretty output helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function Write-Banner {
    Write-Host ""
    Write-Host "  +-----------------------------------------+" -ForegroundColor Magenta
    Write-Host "  |         MCP Factory  --  Setup          |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------+" -ForegroundColor Magenta
    Write-Host ""
}

function Write-Step  { param([string]$n, [string]$msg) Write-Host "`n  [$n] $msg" -ForegroundColor Cyan }
function Write-OK    { param([string]$msg) Write-Host "       OK  $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "       !!  $msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$msg) Write-Host "        X  $msg" -ForegroundColor Red }
function Write-Note  { param([string]$msg) Write-Host "           $msg" -ForegroundColor Gray }

Write-Banner

# â”€â”€ Step 1: Find Python 3.8+ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "1/8" "Locating Python 3.8+"

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py -3")) {
    try {
        $args = if ($candidate -eq "py -3") { @("-3", "--version") } else { @("--version") }
        $exe  = ($candidate -split " ")[0]
        $ver  = & $exe @args 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 8)) {
                $pythonCmd = $exe
                Write-OK "Found $ver  (command: '$exe')"
                break
            } else {
                Write-Warn "Found $ver but 3.8+ is required -- skipping"
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python 3.8+ not found in PATH."
    Write-Note "Install from https://python.org/downloads/ and tick 'Add Python to PATH'."
    exit 1
}

# â”€â”€ Step 2: Create virtual environment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "2/8" "Setting up virtual environment (.venv)"

if ($Force -and (Test-Path $VenvDir)) {
    Write-Note "Removing existing .venv (--Force specified)..."
    Remove-Item $VenvDir -Recurse -Force
}

if (Test-Path $VenvPy) {
    Write-OK "Virtual environment already exists -- skipping creation"
    Write-Note "Pass -Force to recreate it from scratch."
} else {
    Write-Note "Running: $pythonCmd -m venv .venv"
    & $pythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Fail "venv creation failed."; exit 1 }
    Write-OK "Created .venv"
}

# â”€â”€ Step 3: Upgrade pip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "3/8" "Upgrading pip"
& $VenvPip install --upgrade pip --quiet
Write-OK "pip is up to date"

# â”€â”€ Step 4: Install dependencies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "4/8" "Installing root requirements  (discovery, CLI, tests)"
Write-Note "  pip install -r requirements.txt"
& $VenvPip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Fail "Root requirements install failed."; exit 1 }
Write-OK "Root requirements installed"

Write-Note ""
Write-Note "  pip install -r api/requirements.txt  (FastAPI, OpenAI)"
& $VenvPip install -r (Join-Path $Root "api\requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Fail "API requirements install failed."; exit 1 }
Write-OK "API requirements installed"

# â”€â”€ Step 5: pywin32 post-install â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "5/8" "Running pywin32 post-install (Windows only)"

$postInstall = Join-Path $VenvDir "Scripts\pywin32_postinstall.py"
if (Test-Path $postInstall) {
    & $VenvPy $postInstall -install 2>&1 | Out-Null
    Write-OK "pywin32 post-install complete"
} else {
    Write-OK "No pywin32_postinstall.py found -- this version of pywin32 doesn't need it"
}

# â”€â”€ Step 6: Scaffold .env â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "6/8" "Configuring .env"

$EnvFile    = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"

if (Test-Path $EnvFile) {
    Write-OK ".env already exists -- leaving it unchanged"
    Write-Note "To reconfigure, delete .env and re-run setup.ps1"
} else {
    if (-not (Test-Path $EnvExample)) {
        Write-Fail ".env.example is missing. The repo may be incomplete."
        exit 1
    }

    Write-Host ""
    Write-Host "  No .env found. Let's create one." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  You need an OpenAI API key. Get one at:" -ForegroundColor Gray
    Write-Host "    https://platform.openai.com/api-keys" -ForegroundColor Gray
    Write-Host ""

    $apiKey = Read-Host "  Enter your OPENAI_API_KEY (sk-...)"
    $apiKey = $apiKey.Trim()

    if (-not $apiKey -or $apiKey -match '^\s*$' -or $apiKey -eq 'sk-...') {
        Write-Warn "No API key entered. You'll need to set OPENAI_API_KEY in .env manually."
        $apiKey = "sk-YOUR-KEY-HERE"
    } elseif ($apiKey -notmatch '^sk-') {
        Write-Warn "Key doesn't start with 'sk-' -- double-check it's correct."
    }

    Write-Host ""
    Write-Host "  Strict local runtime mode is the canonical operator path." -ForegroundColor Gray
    Write-Host "  Storage backend will be pinned to local." -ForegroundColor Gray
    $storageBackend = "local"

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"

    $envContent = @"
# MCP Factory -- generated by setup.ps1 on $timestamp
# Edit this file to change settings. Restart services after any change.

# â”€â”€ OpenAI (required) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
OPENAI_API_KEY=$apiKey

# Chat model (gpt-4o is best; gpt-4o-mini is ~15x cheaper, fine for dev)
OPENAI_MODEL=gpt-4o
OPENAI_CHAT_MODEL=gpt-4o-mini

# Explore/probe loop model -- gpt-4o-mini recommended (~`$0.03 per 13-function DLL run)
OPENAI_EXPLORE_MODEL=gpt-4o-mini

# â”€â”€ Storage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 'local' = artifacts on disk under local-data/
MCP_STORAGE_BACKEND=$storageBackend
MCP_LOCAL_DATA_ROOT=local-data

# â”€â”€ GUI / DLL Bridge â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# The bridge is a Windows server that loads DLLs and drives GUIs via ctypes/pywinauto.
# start.ps1 starts it automatically on port 8090.
# The secret must match between the API (GUI_BRIDGE_SECRET) and the bridge (BRIDGE_SECRET).
GUI_BRIDGE_URL=$bridgeBaseUrl
GUI_BRIDGE_SECRET=local-debug

# â”€â”€ Explore engine tuning (leave as defaults for first run) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# EXPLORE_CAP_PROFILE=dev
# EXPLORE_ENABLE_GAP_RESOLUTION=1
# EXPLORE_MAX_ROUNDS=3
# EXPLORE_MAX_TOOL_CALLS=5
# EXPLORE_MAX_FUNCTIONS=50

# â”€â”€ Access guards (leave empty = open access for local dev) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PIPELINE_API_KEY=
# UI_API_KEY=
"@

    Set-Content -Path $EnvFile -Value $envContent -Encoding UTF8
    Write-OK ".env created at $EnvFile"
}

# â”€â”€ Step 7: Create local-data directory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "7/8" "Ensuring local-data/ directory exists"

$LocalData = Join-Path $Root "local-data"
if (-not (Test-Path $LocalData)) {
    New-Item -ItemType Directory -Path $LocalData | Out-Null
    Write-OK "Created local-data/"
} else {
    Write-OK "local-data/ already exists"
}

# â”€â”€ Step 8: Validate .env + smoke-test imports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Step "8/8" "Validating .env and critical imports"

# Parse .env
$envVars = @{}
foreach ($line in Get-Content $EnvFile) {
    $line = $line.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { continue }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { continue }
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()
    $envVars[$key] = $val
}

$issues = @()

$apiKeyVal = $envVars['OPENAI_API_KEY']
if (-not $apiKeyVal -or $apiKeyVal -match '^sk-\.\.\.' -or $apiKeyVal -eq 'sk-YOUR-KEY-HERE' -or $apiKeyVal.Trim() -eq '') {
    $issues += "OPENAI_API_KEY is missing or still a placeholder -- edit .env before starting services"
}

$bridgeSecret = $envVars['GUI_BRIDGE_SECRET']
if (-not $bridgeSecret -or $bridgeSecret -match 'your-bridge-secret-here' -or $bridgeSecret.Trim() -eq '') {
    $issues += "GUI_BRIDGE_SECRET is empty or a placeholder -- set it to any non-empty string (e.g. 'local-debug')"
}

$storageMode = $envVars['MCP_STORAGE_BACKEND']
if (-not $storageMode -or $storageMode -ne 'local') {
    $issues += "MCP_STORAGE_BACKEND must be 'local' for the strict local runtime path"
}

$configuredBridgeUrl = [string]$envVars['GUI_BRIDGE_URL']
if (-not $configuredBridgeUrl -or $configuredBridgeUrl.Trim() -eq '') {
    $issues += "GUI_BRIDGE_URL is missing from .env -- strict local runtime requires $bridgeBaseUrl"
} elseif ($configuredBridgeUrl.Trim() -ne $bridgeBaseUrl) {
    $issues += "GUI_BRIDGE_URL must be the canonical strict local bridge URL ($bridgeBaseUrl)"
}
foreach ($requiredKey in $runtimeEnvKeys) {
    $val = [string]($envVars[$requiredKey])
    if (-not $val -or $val.Trim() -eq '') {
        $issues += "$requiredKey is missing from .env -- the local runtime contract expects it"
    }
}

foreach ($issue in $issues) { Write-Warn $issue }

# Quick import smoke test
$importResult = & $VenvPy -c "import fastapi, uvicorn, openai, pefile, mcp, jinja2; print('OK')" 2>&1
if ("$importResult" -match "OK") {
    Write-OK "Core imports verified (fastapi, uvicorn, openai, pefile, mcp, jinja2)"
} else {
    Write-Warn "Import check had problems:"
    Write-Note "  $importResult"
    Write-Warn "Try: .venv\Scripts\pip install -r requirements.txt -r api\requirements.txt"
}

# â”€â”€ Done â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

Write-Host ""
Write-Host "  +-----------------------------------------+" -ForegroundColor Green
Write-Host "  |          Setup Complete!                |" -ForegroundColor Green
Write-Host "  +-----------------------------------------+" -ForegroundColor Green
Write-Host ""
Write-Host "  What to do next:" -ForegroundColor White

if ($issues.Count -gt 0) {
    Write-Host "    1. Fix the issues listed above in .env" -ForegroundColor Yellow
    Write-Host "    2. Run  .\runtime\validate-local-lane.ps1" -ForegroundColor Gray
} else {
    Write-Host "    1. Run  .\runtime\validate-local-lane.ps1  for the bounded local lane proof" -ForegroundColor Gray
    Write-Host "    2. Run  .\runtime\api\start.ps1  or  .\runtime\bridge\start.ps1  for single-system startup" -ForegroundColor Gray
    Write-Host "    3. Open http://localhost:8080  after  .\start.ps1  if you need the full stack" -ForegroundColor Gray
}
Write-Host ""
Write-Host "  Key files:" -ForegroundColor White
Write-Host "    .env          -- your secrets and configuration" -ForegroundColor Gray
Write-Host "    SETUP.md      -- full setup guide with troubleshooting" -ForegroundColor Gray
Write-Host "    start.ps1     -- run this any time to start services" -ForegroundColor Gray
Write-Host "    runtime\api\README.md      -- API runtime contract and operator note" -ForegroundColor Gray
Write-Host "    runtime\bridge\README.md   -- bridge runtime contract and operator note" -ForegroundColor Gray
Write-Host "    runtime\runners\proving-lane-canary\README.md   -- proving runner contract" -ForegroundColor Gray
Write-Host "    docs\architecture\runtime\LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md   -- authoritative runtime ownership map" -ForegroundColor Gray
Write-Host ""

if (-not $NoStart -and $issues.Count -eq 0) {
    $ans = Read-Host "  Start services now? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[Yy]') {
        & (Join-Path $Root "start.ps1")
    }
}

