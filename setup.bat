@echo off
setlocal EnableDelayedExpansion
title ScriptToScene Studio - Setup
cd /d "%~dp0"

:: ── ANSI escape ─────────────────────────────────────────────────────────
for /f %%a in ('echo prompt $E ^| cmd') do set "E=%%a"

set "C=%E%[36m"
set "G=%E%[32m"
set "Y=%E%[33m"
set "R=%E%[31m"
set "D=%E%[90m"
set "B=%E%[1m"
set "X=%E%[0m"

:: ── Header ──────────────────────────────────────────────────────────────
echo.
echo   %C%%B%ScriptToScene Studio%X%  %D%Setup%X%
echo   %D%----------------------------%X%
echo.

:: ── Check Python ────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo   %R%x%X% Python not found. Install Python 3.10+ first.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   %G%+%X% %PYVER%

:: ── Create venv ─────────────────────────────────────────────────────────
if not exist "venv" (
    echo   %D%~%X% Creating virtual environment...
    python -m venv venv
    echo   %G%+%X% Virtual environment created
) else (
    echo   %D%-%X% Virtual environment already exists
)

:: ── Activate and install ────────────────────────────────────────────────
echo   %D%~%X% Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo   %G%+%X% Dependencies installed
echo.

:: ── Done ────────────────────────────────────────────────────────────────
echo   %D%----------------------------%X%
echo   %G%%B%Setup complete!%X%
echo   %D%Run%X% %B%runner.bat%X% %D%or%X% %B%start-dev.bat%X% %D%to start.%X%
echo.
pause
