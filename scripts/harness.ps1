param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$harnessPy = Join-Path $PSScriptRoot "harness.py"
if (-not (Test-Path $harnessPy)) {
    throw "Missing harness entrypoint: $harnessPy"
}

& $pythonExe $harnessPy @Args
exit $LASTEXITCODE
