@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
:: Launcher for the loop-engineering orchestrator.
:: Double-click       -> choose an agent profile, then run phase by phase.
:: From a terminal:
::   run.bat --status
::   run.bat --phase 2
::   run.bat --until 3.3 --builder codex --fixer codex --reviewer codex
::   run.bat --steps 1 --no-push
cd /d "%~dp0..\.."
title ScriptToScene Studio - Loop Engineering

if not exist "venv\Scripts\python.exe" (
    echo [run.bat] venv\Scripts\python.exe not found - run setup.bat first.
    goto :hold
)

set EXITCODE=0
if not "%~1"=="" goto :with_args

:menu
echo ========================================================================
echo [run.bat] Choose the agents for this run:
echo.
echo   [1] Codex builds, fixes, and reviews
echo   [2] Claude builds, fixes, and reviews
echo   [3] Codex builds; Claude fixes and reviews
echo   [4] Claude builds; Codex fixes and reviews
echo   [Q] Cancel
echo.
choice /c 1234Q /n /m "Select 1, 2, 3, 4, or Q: "
if errorlevel 5 goto :cancelled
if errorlevel 4 goto :claude_build_codex_fix
if errorlevel 3 goto :codex_build_claude_fix
if errorlevel 2 goto :all_claude

:all_codex
set "PROFILE=Codex builds, fixes, and reviews"
set "RUNARGS=--by-phase --builder codex --fixer codex --reviewer codex"
set "USES_CLAUDE=0"
goto :launch

:all_claude
set "PROFILE=Claude builds, fixes, and reviews"
set "RUNARGS=--by-phase --builder claude --fixer claude --reviewer claude"
set "USES_CLAUDE=1"
goto :launch

:codex_build_claude_fix
set "PROFILE=Codex builds; Claude fixes and reviews"
set "RUNARGS=--by-phase --builder codex --fixer claude --reviewer claude"
set "USES_CLAUDE=1"
goto :launch

:claude_build_codex_fix
set "PROFILE=Claude builds; Codex fixes and reviews"
set "RUNARGS=--by-phase --builder claude --fixer codex --reviewer codex"
set "USES_CLAUDE=1"
goto :launch

:launch
echo.
echo ========================================================================
echo [run.bat] LOOP STARTING - %PROFILE%.
echo [run.bat] Press Ctrl+C here if you need to stop the engineering loop.
echo ========================================================================
echo.
if "%USES_CLAUDE%"=="1" start "Loop Engineering - Claude Activity" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch.ps1"
venv\Scripts\python.exe -u "_dev\loop-engineering\loop_engineering.py" %RUNARGS%
set EXITCODE=%errorlevel%
goto :hold

:with_args
venv\Scripts\python.exe -u "_dev\loop-engineering\loop_engineering.py" %*
set EXITCODE=%errorlevel%
goto :hold

:cancelled
echo.
echo [run.bat] Cancelled - nothing was started.
set EXITCODE=0

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
