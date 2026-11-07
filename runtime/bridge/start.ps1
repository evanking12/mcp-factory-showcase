param(
    [switch]$ForceRestart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
& (Join-Path $Root "start.ps1") -BridgeOnly -NoBrowser -ForceRestartBridge:$ForceRestart
if ($?) {
    exit 0
}
exit 1
