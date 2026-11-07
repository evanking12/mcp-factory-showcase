# Agent Overnight Checklist (Copy/Paste)

## Goal
Run overnight regression campaigns with a less-capable autonomous agent and produce a morning-ready status on progress back to `12/12`.

## Canonical Source Of Truth
- `.cursorrules`
- `docs/architecture/HARNESS-OPERATIONS-RUNBOOK.md`
- `scripts/ops/start-nightly-groundtruth.ps1`

Use this checklist as the execution card. If any conflict appears, prefer `.cursorrules` and the runbook.

## Preconditions
- Start from repo root.
- API and bridge are reachable.
- Secrets are available in env or local runtime config.

## Step 1: Health Check
```powershell
.\runtime\validate-local-lane.ps1
Write-Host "Managed API + bridge + proving-lane checks passed."
```

Ownership note:
- The strict local operator path is owned by `runtime/*`, `start.ps1`, and `setup.ps1`.
- Treat [docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](../architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md) as the authority when older docs or scripts disagree.

## Step 2: Launch Overnight Nightly Harness (gpt-4o-mini)
```powershell
$env:OPENAI_EXPLORE_MODEL="gpt-4o-mini"
powershell -ExecutionPolicy Bypass -File scripts/ops/start-nightly-groundtruth.ps1 -Hours 8 -MaxRuns 20 -ApiUrl "http://127.0.0.1:8201"
```

Optional API key:
```powershell
$env:MCP_FACTORY_API_KEY="<your_api_key>"
```

## Step 3: Monitor Logs
```powershell
$log = Get-ChildItem sessions/nightly/nightly-groundtruth-*.out.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $log.FullName -Wait
```

## Step 4: Inspect Latest Campaign State
```powershell
$date = Get-Date -Format "yyyy-MM-dd"
$campaign = Get-ChildItem "sessions/nightly/$date" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $campaign.FullName "harness_state.json") -Raw
Get-Content (Join-Path $campaign.FullName "kpi_nightly_summary.json") -Raw
```

## Step 5: Read Morning Artifacts
```powershell
$date = Get-Date -Format "yyyy-MM-dd"
Get-Content "docs/bugs/nightly/$date.md" -Raw
Get-Content "sessions/reports/morning-$date.json" -Raw
```

## Step 6: Extract Remaining Non-Verified Functions
```powershell
$date = Get-Date -Format "yyyy-MM-dd"
$report = Get-Content "sessions/reports/morning-$date.json" -Raw | ConvertFrom-Json
$remaining = @{}
foreach ($run in @($report.runs)) {
    $statuses = $run.latest_status_map
    if (-not $statuses) { continue }
    foreach ($prop in $statuses.PSObject.Properties) {
        if ($prop.Value -ne "verified_success") {
            $remaining[$prop.Name] = $prop.Value
        }
    }
}
$remaining.GetEnumerator() | Sort-Object Name | Format-Table Name, Value
```

## Required Morning Summary Format
Report these fields:
- `campaign_id`
- `runs_total`, `runs_ok`, `runs_failed`, `runs_valid`, `runs_invalid`
- current verified count out of 12
- list of non-verified functions
- top run-validity reasons
- top failed transitions (if present)
- explicit blockers to reaching `12/12`

## Lightweight Alternative Loop
If full nightly is not needed, run:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/runs/autopilot_transition_loop.ps1 -ApiUrl "http://127.0.0.1:8201"
```

