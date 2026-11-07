param(
    [string]$DefaultJobId = "",
    [string]$ComponentPattern = "SoundTouch",
    [switch]$NoAutoResume,
    [switch]$ListJobs
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$artifactRoot = Join-Path $root "local-data\artifacts"

function Get-ShowcaseArtifactJobs {
    param(
        [string]$ArtifactRoot,
        [string]$ComponentPattern = ""
    )

    if (-not (Test-Path $ArtifactRoot)) {
        return @()
    }

    $rows = foreach ($dir in Get-ChildItem $ArtifactRoot -Directory) {
        $macroVerdict = Join-Path $dir.FullName "macro_verdict.json"
        $statusPath = Join-Path $dir.FullName "status.json"
        if (-not (Test-Path $macroVerdict) -or -not (Test-Path $statusPath)) {
            continue
        }
        try {
            $verdict = Get-Content $macroVerdict -Raw | ConvertFrom-Json
            $status = Get-Content $statusPath -Raw | ConvertFrom-Json
            $component = [string]($status.component_name)
            if ($ComponentPattern -and $component -notmatch $ComponentPattern) {
                continue
            }
            [PSCustomObject]@{
                JobId     = $dir.Name
                Component = $component
                Coverage  = [double]($verdict.coverage_pct)
                Verified  = [int]($verdict.verified_count)
                Total     = [int]($verdict.total_count)
                Status    = [string]($verdict.status)
            }
        } catch {
            continue
        }
    }

    return @($rows | Sort-Object -Property `
        @{Expression = "Verified"; Descending = $true}, `
        @{Expression = "Total"; Descending = $true}, `
        @{Expression = "Coverage"; Descending = $true})
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment python not found at $venvPython"
}

$candidateJobs = Get-ShowcaseArtifactJobs -ArtifactRoot $artifactRoot -ComponentPattern $ComponentPattern

if ($ListJobs) {
    if ($candidateJobs.Count -eq 0) {
        Write-Host "No matching artifact-backed jobs found."
    } else {
        $candidateJobs | Select-Object -First 12 | Format-Table -AutoSize
    }
    return
}

$selectedJob = $null
if ($DefaultJobId) {
    $selectedJob = $candidateJobs | Where-Object { $_.JobId -eq $DefaultJobId } | Select-Object -First 1
    if (-not $selectedJob) {
        $selectedJob = [PSCustomObject]@{
            JobId     = $DefaultJobId
            Component = ""
            Coverage  = 0.0
            Verified  = 0
            Total     = 0
            Status    = ""
        }
    }
} elseif (-not $NoAutoResume) {
    $selectedJob = $candidateJobs | Select-Object -First 1
}

if ($selectedJob) {
    $env:SHOWCASE_DEFAULT_JOB_ID = [string]$selectedJob.JobId
    $env:SHOWCASE_AUTO_GENERATE_SCHEMA = "1"
    Write-Host ("Showcase default job: {0} ({1}/{2}, {3}%)" -f `
        $selectedJob.JobId, $selectedJob.Verified, $selectedJob.Total, $selectedJob.Coverage)
} else {
    Remove-Item Env:SHOWCASE_DEFAULT_JOB_ID -ErrorAction SilentlyContinue
    Remove-Item Env:SHOWCASE_AUTO_GENERATE_SCHEMA -ErrorAction SilentlyContinue
    Write-Host "Showcase will start without a preloaded job."
}

Set-Location $root
& $venvPython -m ui.showcase_app
