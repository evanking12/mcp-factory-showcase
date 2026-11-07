@echo off
:: sample.bat — Demo Windows Batch script for MCP Factory script_analyzer tests.
::
:: Exercises: labelled subroutines, CALL :label syntax, and GOTO dispatching.
:: Each :label becomes an "invocable" in batch analysis.

setlocal enableextensions enabledelayedexpansion

:: ──────────────────────────────────────────────────────────────────────
:: Entry point
:: ──────────────────────────────────────────────────────────────────────
:main
    if "%~1"=="" (
        echo Usage: sample.bat ^<command^> [args]
        echo Commands: compress, list_exports, score_confidence, write_json
        exit /b 1
    )
    call :%~1 %2 %3 %4
    exit /b 0

:: ──────────────────────────────────────────────────────────────────────
:compress
::   Compress a file using PowerShell.
::   %1  source_path
::   %2  dest_path
    if "%~1"=="" ( echo ERROR: source_path required & exit /b 1 )
    if "%~2"=="" ( echo ERROR: dest_path required  & exit /b 1 )
    powershell -NoProfile -Command ^
        "Compress-Archive -Path '%~1' -DestinationPath '%~2' -Force"
    echo Compressed: %~1 to %~2
    exit /b 0

:: ──────────────────────────────────────────────────────────────────────
:list_exports
::   Print exported symbols from a PE DLL.
::   %1  dll_path
::   %2  filter_prefix  (optional)
    if "%~1"=="" ( echo ERROR: dll_path required & exit /b 1 )
    set "_filter=%~2"
    for /f "tokens=4" %%S in ('dumpbin /exports "%~1" ^| findstr /R "^ *[0-9][0-9]* "') do (
        if defined _filter (
            echo %%S | findstr /B "!_filter!" >nul 2>&1 && echo %%S
        ) else (
            echo %%S
        )
    )
    exit /b 0

:: ──────────────────────────────────────────────────────────────────────
:score_confidence
::   Echo a confidence label.
::   %1  name
::   %2  has_doc   (1 or 0)
::   %3  is_signed (1 or 0)
    set "_name=%~1"
    set "_doc=%~2"
    set "_sig=%~3"
    if "!_doc!"=="1" if "!_sig!"=="1" ( echo guaranteed & exit /b 0 )
    if "!_doc!"=="1" ( echo high & exit /b 0 )
    if "!_sig!"=="1" ( echo high & exit /b 0 )
    echo !_name! | findstr /B "_" >nul 2>&1
    if errorlevel 1 ( echo medium ) else ( echo low )
    exit /b 0

:: ──────────────────────────────────────────────────────────────────────
:write_json
::   Write a minimal MCP JSON stub to stdout.
::   %1  source_file
::   %2  count
    if "%~1"=="" ( echo ERROR: source_file required & exit /b 1 )
    set "_src=%~1"
    set "_cnt=%~2"
    if not defined _cnt set "_cnt=0"
    echo {
    echo   "source_file": "!_src!",
    echo   "invocable_count": !_cnt!,
    echo   "invocables": []
    echo }
    exit /b 0
