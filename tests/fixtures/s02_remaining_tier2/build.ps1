param(
    [string]$OutputRoot = ".tmp/stage-breakpoint-fixtures/s02_remaining_tier2"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..\..")
$sourcePath = Join-Path $scriptDir "s02_remaining_tier2.c"

if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $outputRootPath = [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    $outputRootPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
}

$binDir = Join-Path $outputRootPath "bin"
$objDir = Join-Path $outputRootPath ".obj"
$dllPath = Join-Path $binDir "s02_remaining_tier2.dll"
$objPath = Join-Path $objDir "s02_remaining_tier2.obj"

New-Item -ItemType Directory -Path $binDir -Force | Out-Null
New-Item -ItemType Directory -Path $objDir -Force | Out-Null

$vsDevCandidates = @()
$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    if ($installPath) {
        $vsDevCandidates += (Join-Path $installPath "Common7\Tools\VsDevCmd.bat")
    }
}
$vsDevCandidates += @(
    "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\Tools\VsDevCmd.bat"
)

$vsDevCmd = $null
foreach ($cand in $vsDevCandidates) {
    if (Test-Path $cand) {
        $vsDevCmd = $cand
        break
    }
}

$cmdLine = "cl /nologo /O2 /GS- /LD /W3 `"$sourcePath`" /Fo`"$objPath`" /Fe:`"$dllPath`""
if ($vsDevCmd) {
    cmd /c "`"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && $cmdLine" | Out-Host
} else {
    $cl = Get-Command cl.exe -ErrorAction SilentlyContinue
    if (-not $cl) {
        throw "Build failed: no usable MSVC toolchain found."
    }
    & cl.exe /nologo /O2 /GS- /LD /W3 $sourcePath /Fo$objPath /Fe:$dllPath | Out-Host
}

if (-not (Test-Path $dllPath)) {
    throw "Failed to build $dllPath"
}

Write-Host "Built S-02 remaining Tier 2 DLL: $dllPath"
Write-Output $dllPath
