@echo off
setlocal EnableDelayedExpansion
title ScriptToScene Studio
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
echo   %C%%B%ScriptToScene Studio%X%
echo   %D%----------------------------%X%
echo.

:: ── Git pull ────────────────────────────────────────────────────────────
call :do_git_pull
if errorlevel 1 (
    pause
    exit /b 1
)

:: ── Virtual environment ─────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo   %R%x%X% Virtual environment not found. Run %B%setup.bat%X% first.
    echo.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

:: ── Dependency sync ─────────────────────────────────────────────────────
set "STAMP=venv\.requirements_stamp"
set "REQS=requirements.txt"

if not exist "%STAMP%" (
    echo   %D%~%X% Syncing dependencies...
    pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
    echo   %G%+%X% Dependencies synced
    echo.
) else (
    fc /b "%REQS%" "%STAMP%" >nul 2>&1
    if errorlevel 1 (
        echo   %Y%~%X% Requirements changed — syncing...
        pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
        echo   %G%+%X% Dependencies synced
        echo.
    )
)

:: ── .env sanity check ───────────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        echo   %Y%!%X% No .env found — copied from .env.example
        copy .env.example .env >nul
        echo   %D%  Edit .env with your API keys before using webhooks%X%
        echo.
    )
)

:: ── Launch ──────────────────────────────────────────────────────────────
echo   %D%~%X% Starting server...
echo.
python app.py %*

:: ── Exit ────────────────────────────────────────────────────────────────
echo.
echo   %D%Server stopped.%X%
pause
endlocal
goto :eof

:: ── Subroutine: git pull ────────────────────────────────────────────────
:do_git_pull
ping -n 1 -w 1000 github.com >nul 2>&1
if errorlevel 1 (
    echo   %Y%!%X% No network — skipping git pull
    echo.
    exit /b 0
)
if not exist "tmp" mkdir "tmp"
echo   %D%~%X% git pull...
git pull >"tmp\git_pull_out.txt" 2>&1
if errorlevel 1 goto :git_pull_failed
findstr /i /c:"CONFLICT" /c:"error:" /c:"fatal:" /c:"Cannot" /c:"refusing" /c:"Please commit" /c:"not possible" "tmp\git_pull_out.txt" >nul 2>&1
if not errorlevel 1 goto :git_pull_failed
echo   %G%+%X% git pull OK
for /f "usebackq delims=" %%l in ("tmp\git_pull_out.txt") do echo   %D%  %%l%X%
del "tmp\git_pull_out.txt" >nul 2>&1
echo.
exit /b 0
:git_pull_failed
echo.
echo   %R%x%X% git pull failed:
echo.
type "tmp\git_pull_out.txt"
echo.
echo   %D%Common fixes:%X%
echo   %D%  - Merge conflicts  : resolve, then git add + git commit%X%
echo   %D%  - Uncommitted changes : git stash, then re-run%X%
echo   %D%  - Diverged branches   : git pull --rebase%X%
echo.
del "tmp\git_pull_out.txt" >nul 2>&1
exit /b 1
