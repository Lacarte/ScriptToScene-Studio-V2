@echo off
setlocal
:: Launcher for the loop-engineering orchestrator.
:: Double-click       -> shows the plan status and keeps the window open.
:: From a terminal:
::   run.bat --status
::   run.bat --phase 2
::   run.bat --until 3.3 --reviewer claude
::   run.bat --steps 1 --no-push
cd /d "%~dp0..\.."

if not exist "venv\Scripts\python.exe" (
    echo [run.bat] venv\Scripts\python.exe not found - run setup.bat first.
    goto :hold
)

set EXITCODE=0
if "%~1"=="" (
    echo [run.bat] No arguments given - showing plan status.
    echo [run.bat] To execute steps, run from a terminal, e.g.:
    echo [run.bat]     _dev\loop-engineering\run.bat --phase 2
    echo.
    venv\Scripts\python.exe "_dev\loop-engineering\loop_engineering.py" --status
) else (
    venv\Scripts\python.exe "_dev\loop-engineering\loop_engineering.py" %*
)
set EXITCODE=%errorlevel%

:hold
:: Keep the console open when launched by double-click from Explorer
:: (cmdcmdline then contains this script's full path; in a real terminal it doesn't).
echo %cmdcmdline% | find /i "%~f0" >nul && (
    echo.
    pause
)
endlocal & exit /b %EXITCODE%
