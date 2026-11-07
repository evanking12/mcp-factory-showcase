param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$target = Join-Path $PSScriptRoot "ops\save-session.ps1"
if (-not (Test-Path $target)) { throw "Missing target script: $target" }
Write-Warning "Deprecated wrapper. Use `scripts/harness.ps1 capture`."
& $target @Args
exit $LASTEXITCODE
