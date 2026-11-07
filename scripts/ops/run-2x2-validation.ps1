param(
    [int[]]$ApiPorts = @(8201, 8202, 8203, 8204),
    [double]$Hours = 2.0,
    [ValidateSet("strict_dll","greybox_dll","full_surface")][string]$AnalysisProfile = "strict_dll",
    [ValidateSet("full","compact")][string]$SnapshotProfile = "compact"
)

$ErrorActionPreference = "Stop"

if ($ApiPorts.Count -lt 4) {
    throw "Need 4 API ports (2 contoso + 2 interwoven)."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$harness = Join-Path $repoRoot "scripts\harness.ps1"
if (-not (Test-Path $harness)) { throw "Missing harness wrapper: $harness" }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $repoRoot "sessions\matrix\$stamp-2x2"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$jobs = @(
    @{ name = "contoso-a"; target = "contoso_cs"; api = $ApiPorts[0] },
    @{ name = "contoso-b"; target = "contoso_cs"; api = $ApiPorts[1] },
    @{ name = "interwoven-a"; target = "contoso_cs_interwoven"; api = $ApiPorts[2] },
    @{ name = "interwoven-b"; target = "contoso_cs_interwoven"; api = $ApiPorts[3] }
)

$procs = @()
foreach ($j in $jobs) {
    $suffix = "2x2-" + $j.name
    $outLog = Join-Path $runDir ($j.name + ".out.log")
    $errLog = Join-Path $runDir ($j.name + ".err.log")
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $harness,
        "run",
        "--profile", "nightly",
        "--",
        "--hours", "$Hours",
        "--max-runs", "1",
        "--api-url", ("http://127.0.0.1:{0}" -f $j.api),
        "--targets", $j.target,
        "--campaign-suffix", $suffix,
        "--report-suffix", $suffix,
        "--analysis-profile", $AnalysisProfile,
        "--snapshot-profile", $SnapshotProfile
    )
    $p = Start-Process -FilePath "powershell" -ArgumentList $args -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    $procs += [PSCustomObject]@{
        name = $j.name
        target = $j.target
        api_port = $j.api
        pid = $p.Id
        process = $p
        out_log = $outLog
        err_log = $errLog
    }
}

Write-Host "Launched 2x2 validation jobs."
$procs | Select-Object name, target, api_port, pid, out_log, err_log | Format-Table -AutoSize

$results = @()
foreach ($p in $procs) {
    $p.process.WaitForExit()
    $exitCode = $p.process.ExitCode
    $results += [PSCustomObject]@{
        name = $p.name
        target = $p.target
        api_port = $p.api_port
        pid = $p.pid
        exit_code = $exitCode
        out_log = $p.out_log
        err_log = $p.err_log
    }
}

$resultPath = Join-Path $runDir "2x2-results.json"
$results | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $resultPath

Write-Host "2x2 validation complete."
Write-Host "Results: $resultPath"
$results | Format-Table -AutoSize
