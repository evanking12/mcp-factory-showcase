<#
.SYNOPSIS
    Demo PowerShell module for MCP Factory script_analyzer tests.
.DESCRIPTION
    Contains several functions covering the three main PowerShell patterns:
    CmdletBinding, simple param blocks, and .SYNOPSIS-documented helpers.
#>

<#
.SYNOPSIS
    Compress a file using Compress-Archive.
.DESCRIPTION
    Wraps the built-in Compress-Archive cmdlet with progress reporting.
.PARAMETER SourcePath
    The file or directory to compress.
.PARAMETER DestinationPath
    Where the ZIP archive should be written.
.PARAMETER CompressionLevel
    Optimal, Fastest, or NoCompression.
.OUTPUTS
    System.IO.FileInfo – the resulting archive file.
#>
function Compress-File {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$SourcePath,

        [Parameter(Mandatory=$true)]
        [string]$DestinationPath,

        [ValidateSet('Optimal','Fastest','NoCompression')]
        [string]$CompressionLevel = 'Optimal'
    )

    Compress-Archive -Path $SourcePath -DestinationPath $DestinationPath `
                     -CompressionLevel $CompressionLevel -Force
    return Get-Item $DestinationPath
}

<#
.SYNOPSIS
    Return all exported functions from a DLL using dumpbin.
.PARAMETER DllPath
    Full path to the DLL file.
.PARAMETER FilterPrefix
    Optional: only return symbols that start with this string.
.OUTPUTS
    String[] of exported symbol names.
#>
function Get-DllExports {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$DllPath,

        [string]$FilterPrefix = ''
    )

    $output = & dumpbin /exports $DllPath 2>&1
    $symbols = $output | Select-String '^\s+\d+\s+\w+\s+\w+\s+(\S+)' |
                ForEach-Object { $_.Matches.Groups[1].Value }

    if ($FilterPrefix) {
        $symbols = $symbols | Where-Object { $_ -like "$FilterPrefix*" }
    }
    return $symbols
}

<#
.SYNOPSIS
    Write an MCP JSON file for a list of invocables.
.PARAMETER Invocables
    Array of hashtables with keys: name, signature, confidence.
.PARAMETER OutputPath
    Destination .json file path.
#>
function Write-McpJson {
    param(
        [Parameter(Mandatory=$true)]
        [hashtable[]]$Invocables,

        [Parameter(Mandatory=$true)]
        [string]$OutputPath
    )

    $payload = @{ invocables = $Invocables } | ConvertTo-Json -Depth 5
    $payload | Set-Content -Path $OutputPath -Encoding UTF8
}

function ConvertTo-ConfidenceLabel {
    <#
    .SYNOPSIS
        Map a numeric score (0-100) to a confidence label string.
    .PARAMETER Score
        Integer 0–100.
    #>
    param([int]$Score)

    if ($Score -ge 90) { return 'guaranteed' }
    if ($Score -ge 70) { return 'high' }
    if ($Score -ge 40) { return 'medium' }
    return 'low'
}
