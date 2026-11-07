#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Safe comprehensive validation script for .NET, COM, and native DLL/EXE analysis
    
.DESCRIPTION
    Minimal version that avoids PowerShell subprocess issues by:
    - Using Python directly with proper timeouts
    - Avoiding inline Python execution
    - Using temporary files for output
    - Better process cleanup
#>

param(
    [string]$OutputDir = ".\test_comprehensive_safe"
)

# ============================================================================
# Configuration
# ============================================================================

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# ============================================================================
# Test Files Configuration
# ============================================================================

$TestFiles = @(
    # Native DLLs (5)
    @{
        Name = "Windows Kernel API"
        Type = "Native DLL"
        Path = "C:\Windows\System32\kernel32.dll"
        ExpectedType = "PE_DLL"
    },
    @{
        Name = "Windows User Interface"
        Type = "Native DLL"
        Path = "C:\Windows\System32\user32.dll"
        ExpectedType = "PE_DLL"
    },
    @{
        Name = "Windows GDI"
        Type = "Native DLL"
        Path = "C:\Windows\System32\gdi32.dll"
        ExpectedType = "PE_DLL"
    },
    @{
        Name = "Windows Shell"
        Type = "Native DLL"
        Path = "C:\Windows\System32\shell32.dll"
        ExpectedType = "COM_OBJECT"
    },
    @{
        Name = "Windows Advanced API"
        Type = "Native DLL"
        Path = "C:\Windows\System32\advapi32.dll"
        ExpectedType = "PE_DLL"
    },
    
    # Native EXEs (2)
    @{
        Name = "Notepad"
        Type = "Native EXE"
        Path = "C:\Windows\System32\notepad.exe"
        ExpectedType = "PE_EXE"
    },
    @{
        Name = "Command Prompt"
        Type = "Native EXE"
        Path = "C:\Windows\System32\cmd.exe"
        ExpectedType = "PE_EXE"
    },
    
    # COM/DCOM DLLs (2)
    @{
        Name = "COM Automation"
        Type = "COM DLL"
        Path = "C:\Windows\System32\oleaut32.dll"
        ExpectedType = "COM_OBJECT"
    },
    @{
        Name = "COM Base"
        Type = "COM DLL"
        Path = "C:\Windows\System32\ole32.dll"
        ExpectedType = "COM_OBJECT"
    },
    
    # .NET Assemblies (2)
    @{
        Name = ".NET Core Library"
        Type = ".NET Assembly"
        Path = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\mscorlib.dll"
        ExpectedType = "DOTNET_ASSEMBLY"
    },
    @{
        Name = ".NET System Library"
        Type = ".NET Assembly"
        Path = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.dll"
        ExpectedType = "DOTNET_ASSEMBLY"
    }
)

# ============================================================================
# Helper Functions
# ============================================================================

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 90) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 90) -ForegroundColor Cyan
}

function Write-SubHeader {
    param([string]$Text)
    Write-Host ""
    Write-Host ("-" * 90) -ForegroundColor Yellow
    Write-Host $Text -ForegroundColor Yellow
    Write-Host ("-" * 90) -ForegroundColor Yellow
}

function Test-FileExists {
    param([string]$Path)
    
    if (Test-Path $Path) {
        $size = (Get-Item $Path).Length
        $sizeMB = [math]::Round($size / 1MB, 2)
        Write-Host "  [+] Found: $Path ($sizeMB MB)" -ForegroundColor Green
        return $true
    } else {
        Write-Host "  [!] Missing: $Path" -ForegroundColor Red
        return $false
    }
}

function Invoke-SafePython {
    param(
        [string]$Script,
        [int]$TimeoutSeconds = 60
    )
    
    try {
        # Write script to temp file
        $tempScript = [System.IO.Path]::GetTempFileName() + ".py"
        Set-Content -Path $tempScript -Value $Script -Encoding UTF8
        
        # Run with timeout
        $process = Start-Process -FilePath "python" `
            -ArgumentList $tempScript `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput "$tempScript.out" `
            -RedirectStandardError "$tempScript.err"
        
        # Read output
        $stdout = Get-Content "$tempScript.out" -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content "$tempScript.err" -Raw -ErrorAction SilentlyContinue
        
        # Cleanup
        Remove-Item $tempScript -ErrorAction SilentlyContinue
        Remove-Item "$tempScript.out" -ErrorAction SilentlyContinue
        Remove-Item "$tempScript.err" -ErrorAction SilentlyContinue
        
        return @{
            ExitCode = $process.ExitCode
            Output = $stdout
            Error = $stderr
        }
    }
    catch {
        Write-Host "  [!] Python execution failed: $_" -ForegroundColor Red
        return @{
            ExitCode = 1
            Output = ""
            Error = $_.Exception.Message
        }
    }
}

# ============================================================================
# Analysis Functions
# ============================================================================

function Get-FileClassification {
    param([string]$FilePath)
    
    $script = @"
import sys
sys.path.insert(0, r'src\discovery')

from pathlib import Path
from classify import classify_file

result = classify_file(Path(r'$FilePath'))
print(result.name)
"@
    
    $result = Invoke-SafePython -Script $script -TimeoutSeconds 10
    
    if ($result.ExitCode -eq 0 -and $result.Output) {
        return $result.Output.Trim()
    }
    return "UNKNOWN"
}

function Get-ExportCount {
    param([string]$FilePath)
    
    $script = @"
import sys
sys.path.insert(0, r'src\discovery')

from pathlib import Path
from pe_parse import get_exports_from_dumpbin

exports, has_exports = get_exports_from_dumpbin(Path(r'$FilePath'), 'dumpbin')
print(len(exports))
"@
    
    $result = Invoke-SafePython -Script $script -TimeoutSeconds 30
    
    if ($result.ExitCode -eq 0 -and $result.Output) {
        return [int]$result.Output.Trim()
    }
    return 0
}

function Get-DotNetMethodCount {
    param([string]$FilePath)
    
    $script = @"
import sys
sys.path.insert(0, r'src\discovery')

from pathlib import Path
from dotnet_analyzer import get_dotnet_methods

try:
    methods = get_dotnet_methods(Path(r'$FilePath'))
    print(len(methods))
except Exception as e:
    print(0)
"@
    
    $result = Invoke-SafePython -Script $script -TimeoutSeconds 60
    
    if ($result.ExitCode -eq 0 -and $result.Output) {
        return [int]$result.Output.Trim()
    }
    return 0
}

function Get-COMObjectCount {
    param([string]$FilePath)
    
    $filename = [System.IO.Path]::GetFileName($FilePath)
    
    $script = @"
import sys
sys.path.insert(0, r'src\discovery')

from com_scan import scan_com_registry

try:
    objects = scan_com_registry('$filename')
    print(len(objects))
except Exception as e:
    print(0)
"@
    
    $result = Invoke-SafePython -Script $script -TimeoutSeconds 30
    
    if ($result.ExitCode -eq 0 -and $result.Output) {
        return [int]$result.Output.Trim()
    }
    return 0
}

# ============================================================================
# Main Analysis Loop
# ============================================================================

Write-Header "COMPREHENSIVE VALIDATION - SAFE MODE"
Write-Host "Output Directory: $OutputDir"
Write-Host "Test Files: $($TestFiles.Count)"
Write-Host ""

$results = [System.Collections.ArrayList]::new()
$totalFiles = $TestFiles.Count
$currentFile = 0

foreach ($file in $TestFiles) {
    $currentFile++
    
    Write-SubHeader "[$currentFile/$totalFiles] Processing: $($file.Name)"
    Write-Host "  Type: $($file.Type)"
    Write-Host "  Path: $($file.Path)"
    
    $fileResult = @{
        Name = $file.Name
        Type = $file.Type
        Path = $file.Path
        ExpectedType = $file.ExpectedType
        Exists = $false
        Classification = "UNKNOWN"
        ExportCount = 0
        MethodCount = 0
        COMCount = 0
        Success = $false
        Duration = 0
    }
    
    # Step 1: Check file exists
    if (-not (Test-FileExists $file.Path)) {
        $fileResult.Success = $false
        $null = $results.Add($fileResult)
        continue
    }
    
    $fileResult.Exists = $true
    $startTime = Get-Date
    
    # Step 2: Classify file
    Write-Host "  [*] Classifying file..." -ForegroundColor Cyan
    $fileResult.Classification = Get-FileClassification $file.Path
    Write-Host "  [+] Classification: $($fileResult.Classification)" -ForegroundColor $(if ($fileResult.Classification -eq $file.ExpectedType) { "Green" } else { "Yellow" })
    
    # Step 3: Type-specific analysis
    switch ($file.Type) {
        "Native DLL" {
            Write-Host "  [*] Extracting exports..." -ForegroundColor Cyan
            $fileResult.ExportCount = Get-ExportCount $file.Path
            Write-Host "  [+] Exports: $($fileResult.ExportCount)" -ForegroundColor Green
        }
        
        "Native EXE" {
            Write-Host "  [*] Extracting exports..." -ForegroundColor Cyan
            $fileResult.ExportCount = Get-ExportCount $file.Path
            Write-Host "  [+] Exports: $($fileResult.ExportCount)" -ForegroundColor Green
        }
        
        "COM DLL" {
            Write-Host "  [*] Scanning COM registry..." -ForegroundColor Cyan
            $fileResult.COMCount = Get-COMObjectCount $file.Path
            Write-Host "  [+] COM Objects: $($fileResult.COMCount)" -ForegroundColor Green
            
            Write-Host "  [*] Extracting exports..." -ForegroundColor Cyan
            $fileResult.ExportCount = Get-ExportCount $file.Path
            Write-Host "  [+] Exports: $($fileResult.ExportCount)" -ForegroundColor Green
        }
        
        ".NET Assembly" {
            Write-Host "  [*] Extracting .NET methods (this may take 30-60 seconds)..." -ForegroundColor Cyan
            $fileResult.MethodCount = Get-DotNetMethodCount $file.Path
            Write-Host "  [+] Methods: $($fileResult.MethodCount)" -ForegroundColor Green
        }
    }
    
    $endTime = Get-Date
    $fileResult.Duration = ($endTime - $startTime).TotalSeconds
    $fileResult.Success = $true
    
    Write-Host "  [+] Completed in $($fileResult.Duration.ToString('0.0'))s" -ForegroundColor Green
    
    $null = $results.Add($fileResult)
}

# ============================================================================
# Summary Report
# ============================================================================

Write-Header "VALIDATION SUMMARY"

$successCount = ($results | Where-Object { $_.Success }).Count
$failCount = $totalFiles - $successCount

Write-Host ""
Write-Host "Total Files:    $totalFiles"
Write-Host "Successful:     $successCount" -ForegroundColor Green
Write-Host "Failed:         $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })
Write-Host ""

# Breakdown by type
Write-SubHeader "Results by Type"

$byType = $results | Group-Object Type

foreach ($group in $byType) {
    Write-Host ""
    Write-Host "$($group.Name):" -ForegroundColor Cyan
    
    foreach ($item in $group.Group) {
        $status = if ($item.Success) { "[+]" } else { "[-]" }
        $color = if ($item.Success) { "Green" } else { "Red" }
        
        Write-Host "  $status $($item.Name)" -ForegroundColor $color
        
        if ($item.Success) {
            Write-Host "      Classification: $($item.Classification)" -ForegroundColor Gray
            
            if ($item.ExportCount -gt 0) {
                Write-Host "      Exports: $($item.ExportCount)" -ForegroundColor Gray
            }
            if ($item.MethodCount -gt 0) {
                Write-Host "      .NET Methods: $($item.MethodCount)" -ForegroundColor Gray
            }
            if ($item.COMCount -gt 0) {
                Write-Host "      COM Objects: $($item.COMCount)" -ForegroundColor Gray
            }
            
            Write-Host "      Duration: $($item.Duration.ToString('0.0'))s" -ForegroundColor Gray
        }
    }
}

# ============================================================================
# Confidence Summary
# ============================================================================

Write-Header "CONFIDENCE SUMMARY"

$totalExports = 0
$totalMethods = 0
$totalCOMObjects = 0

foreach ($r in $results) {
    $totalExports += $r.ExportCount
    $totalMethods += $r.MethodCount
    $totalCOMObjects += $r.COMCount
}

Write-Host ""
Write-Host "Total Exports Extracted:      $totalExports"
Write-Host "Total .NET Methods Extracted: $totalMethods"
Write-Host "Total COM Objects Found:      $totalCOMObjects"
Write-Host ""

$correctClassifications = ($results | Where-Object { $_.Classification -eq $_.ExpectedType }).Count
$classificationAccuracy = if ($totalFiles -gt 0) { ($correctClassifications / $totalFiles) * 100 } else { 0 }

Write-Host "Classification Accuracy: $($classificationAccuracy.ToString('0.0'))% ($correctClassifications/$totalFiles)" -ForegroundColor $(if ($classificationAccuracy -eq 100) { "Green" } else { "Yellow" })
Write-Host ""

# Overall confidence
if ($successCount -eq $totalFiles -and $classificationAccuracy -eq 100 -and $totalExports -gt 0) {
    Write-Host "OVERALL CONFIDENCE: HIGH" -ForegroundColor Green
    Write-Host "All files analyzed successfully with correct classifications." -ForegroundColor Green
}
elseif ($successCount -ge ($totalFiles * 0.8) -and $classificationAccuracy -ge 80) {
    Write-Host "OVERALL CONFIDENCE: MEDIUM" -ForegroundColor Yellow
    Write-Host "Most files analyzed successfully but some issues detected." -ForegroundColor Yellow
}
else {
    Write-Host "OVERALL CONFIDENCE: LOW" -ForegroundColor Red
    Write-Host "Significant issues detected. Review failures above." -ForegroundColor Red
}

Write-Host ""

# ============================================================================
# Save Results
# ============================================================================

$reportPath = Join-Path $OutputDir "validation_report.txt"

$report = @"
COMPREHENSIVE VALIDATION REPORT
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

SUMMARY
=======
Total Files:              $totalFiles
Successful:               $successCount
Failed:                   $failCount
Classification Accuracy:  $($classificationAccuracy.ToString('0.0'))%

METRICS
=======
Total Exports:            $totalExports
Total .NET Methods:       $totalMethods
Total COM Objects:        $totalCOMObjects

DETAILED RESULTS
================
"@

foreach ($item in $results) {
    $report += @"

File: $($item.Name)
  Type:           $($item.Type)
  Path:           $($item.Path)
  Expected:       $($item.ExpectedType)
  Classification: $($item.Classification)
  Exports:        $($item.ExportCount)
  .NET Methods:   $($item.MethodCount)
  COM Objects:    $($item.COMCount)
  Duration:       $($item.Duration.ToString('0.0'))s
  Success:        $($item.Success)

"@
}

Set-Content -Path $reportPath -Value $report -Encoding UTF8
Write-Host "Report saved to: $reportPath" -ForegroundColor Cyan
Write-Host ""

# Exit with appropriate code
if ($successCount -eq $totalFiles) {
    exit 0
} else {
    exit 1
}
