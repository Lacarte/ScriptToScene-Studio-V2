@echo off
setlocal EnableDelayedExpansion
title ScriptToScene Studio [DEV]
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
echo   %C%%B%ScriptToScene Studio%X%  %D%[DEV]%X%
echo   %D%----------------------------%X%
echo.

:: ── Git pull ────────────────────────────────────────────────────────────
call :do_git_pull
if errorlevel 1 (
    pause
    exit /b 1
)

:: ── Kill leftover dev processes ─────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5174 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Virtual environment ─────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo   %R%x%X% Virtual environment not found. Run %B%setup.bat%X% first.
    echo.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

:: ── Python dependency sync ──────────────────────────────────────────────
set "STAMP=venv\.requirements_stamp"
set "REQS=requirements.txt"

if not exist "%STAMP%" (
    echo   %D%~%X% Syncing Python dependencies...
    pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
    echo   %G%+%X% Python dependencies synced
    echo.
) else (
    fc /b "%REQS%" "%STAMP%" >nul 2>&1
    if errorlevel 1 (
        echo   %Y%~%X% Requirements changed — syncing...
        pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
        echo   %G%+%X% Python dependencies synced
        echo.
    )
)

:: ── Frontend dependency sync ────────────────────────────────────────────
if not exist "frontend\node_modules" (
    echo   %D%~%X% Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
    echo   %G%+%X% Frontend dependencies installed
    echo.
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

:: ── Automation browser ─────────────────────────────────────────────────
if not exist "bin\chromium\ungoogled-chromium\chrome.exe" (
    echo   %D%~%X% Chromium not installed - running setup...
    call "_dev\automation\browser\launch-chromium.bat"
) else (
    powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',9222)" >nul 2>&1
    if errorlevel 1 (
        echo   %D%~%X% Launching Chromium...
        call "_dev\automation\browser\launch-chromium.bat"
    ) else (
        echo   %G%+%X% Chromium already running
    )
)
:: Wait for Chromium CDP to be ready
set "CDP_READY=0"
set "RETRIES=0"
:wait_chromium
powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',9222)" >nul 2>&1
if not errorlevel 1 (
    set "CDP_READY=1"
    echo   %G%+%X% Chromium CDP ready
    goto :chromium_done
)
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
if %RETRIES% LSS 15 goto wait_chromium
echo   %Y%!%X% Chromium CDP not available - pipeline tab will be skipped
:chromium_done

:: ── Launch Flask (background, minimized) ────────────────────────────────
echo   %D%~%X% Starting Flask server...
set "STS_NO_BROWSER=1"
start "STS Flask" /min cmd /c "cd /d "%~dp0" && venv\Scripts\activate.bat && python app.py"

:: ── Wait for Flask ──────────────────────────────────────────────────────
set "RETRIES=0"
:wait_flask
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',5050)" >nul 2>&1
if errorlevel 1 (
    if %RETRIES% LSS 30 goto wait_flask
    echo   %R%x%X% Flask did not start within 30 seconds.
    pause
    exit /b 1
)
echo   %G%+%X% Flask ready
echo.

:: ── Info ────────────────────────────────────────────────────────────────
echo   %D%----------------------------%X%
echo   %B%Flask%X%  %D%:%X%  http://localhost:5050  %D%(API, minimized)%X%
echo   %B%Vite%X%   %D%:%X%  http://localhost:5174  %D%(UI)%X%
echo   %D%----------------------------%X%
echo.

:: ── Launch Vite dev server (background) ────────────────────────────────
start "STS Vite" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

:: ── Wait for Vite ─────────────────────────────────────────────────────
set "RETRIES=0"
:wait_vite
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',5174)" >nul 2>&1
if errorlevel 1 (
    if %RETRIES% LSS 30 goto wait_vite
    echo   %R%x%X% Vite did not start within 30 seconds.
    pause
    exit /b 1
)
echo   %G%+%X% Vite ready
echo.

:: ── Open Pipeline in Chromium ─────────────────────────────────────────
if "%CDP_READY%"=="1" (
    echo   %D%~%X% Opening pipeline in Chromium...
    powershell -Command "Invoke-RestMethod 'http://localhost:9222/json/new?http://localhost:5174/#/pipeline'" >nul 2>&1
    echo   %G%+%X% Pipeline tab opened
)

echo.
echo   %G%+%X% All services running. Press Ctrl+C to stop.
pause >nul
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
