@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
:: Launcher for the loop-engineering orchestrator.
:: Double-click       -> runs all remaining work phase by phase.
:: From a terminal:
::   run.bat --status
::   run.bat --phase 2
::   run.bat --until 3.3 --builder codex --reviewer codex
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
    echo [run.bat] Codex will build and review; live activity appears below.
    echo [run.bat] Press Ctrl+C here if you need to stop the engineering loop.
    echo ========================================================================
    echo.
    venv\Scripts\python.exe -u "_dev\loop-engineering\loop_engineering.py" --by-phase --builder codex --reviewer codex
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
