@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
:: Launcher for the loop-engineering orchestrator.
:: Double-click       -> runs all remaining work phase by phase.
:: From a terminal:
::   run.bat --status
::   run.bat --phase 2
::   run.bat --until 3.3 --reviewer claude
::   run.bat --steps 1 --no-push
cd /d "%~dp0..\.."
title ScriptToScene Studio - Loop Engineering

if not exist "venv\Scripts\python.exe" (
    echo [run.bat] venv\Scripts\python.exe not found - run setup.bat first.
    goto :hold
)

set EXITCODE=0
if "%~1"=="" (
    echo ========================================================================
    echo [run.bat] LOOP STARTING - running all remaining work phase by phase.
    echo [run.bat] Opening a second window with detailed live agent activity.
    echo [run.bat] Press Ctrl+C here if you need to stop the engineering loop.
    echo ========================================================================
    echo.
    start "Loop Engineering - Live Activity" powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0watch.ps1"
    venv\Scripts\python.exe -u "_dev\loop-engineering\loop_engineering.py" --by-phase
) else (
    venv\Scripts\python.exe -u "_dev\loop-engineering\loop_engineering.py" %*
)
set EXITCODE=%errorlevel%

:hold
:: Keep the console open when launched by double-click from Explorer
:: (cmdcmdline then contains this script's full path; in a real terminal it doesn't).
echo %cmdcmdline% | find /i "%~f0" >nul && (
    echo.
    echo [run.bat] Run finished with exit code %EXITCODE%.
    echo [run.bat] Press any key to close this window.
    pause >nul
)
endlocal & exit /b %EXITCODE%
