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
        echo   %Y%~%X% Requirements changed - syncing...
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
        echo   %Y%!%X% No .env found - copied from .env.example
        copy .env.example .env >nul
        echo   %D%  Edit .env with your API keys before using webhooks%X%
        echo.
    )
)

:: ════════════════════════════════════════════════════════════════════════
:: 1) INSTALL Chromium + extensions (if missing)
:: ════════════════════════════════════════════════════════════════════════
echo   %D%~%X% Checking Chromium installation...
if not exist "bin\chromium\ungoogled-chromium\chrome.exe" (
    echo   %D%~%X% Chromium not installed - running setup...
    call "_dev\automation\browser\launch-chromium.bat"
    if errorlevel 1 (
        pause
        exit /b 1
    )
    :: launch-chromium.bat also launched it, so skip to Flask
    goto :start_flask
)
echo   %G%+%X% Chromium installed

:: ════════════════════════════════════════════════════════════════════════
:: 2) START Flask first (extensions need WebSocket on :5050)
:: ════════════════════════════════════════════════════════════════════════
:start_flask
echo   %D%~%X% Starting Flask server...
set "STS_NO_BROWSER=1"
start "STS Flask" /min /d "%CD%" cmd /c "venv\Scripts\activate.bat && python app.py"

set "RETRIES=0"
:wait_flask
timeout /t 2 /nobreak >nul
set /a RETRIES+=1
curl -s -o nul -w "" http://127.0.0.1:5050/ >nul 2>&1
if not errorlevel 1 goto :flask_ready
if %RETRIES% LSS 30 goto wait_flask
echo   %R%x%X% Flask did not start within 60 seconds.
pause
exit /b 1
:flask_ready
echo   %G%+%X% Flask ready (WebSocket available)
echo.

:: ════════════════════════════════════════════════════════════════════════
:: 3) OPEN Chromium (if not already running) - after Flask so WS works
:: ════════════════════════════════════════════════════════════════════════
set "CDP_READY=0"
curl -s -o nul http://127.0.0.1:9222/json/version >nul 2>&1
if not errorlevel 1 (
    set "CDP_READY=1"
    echo   %G%+%X% Chromium already running
    goto :chromium_done
)

echo   %D%~%X% Launching Chromium...
call "_dev\automation\browser\launch-chromium.bat"
if errorlevel 1 (
    echo   %Y%!%X% Chromium launch failed - continuing without it
    goto :chromium_done
)

:: Wait for CDP
set "RETRIES=0"
:wait_cdp
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
curl -s -o nul http://127.0.0.1:9222/json/version >nul 2>&1
if not errorlevel 1 (
    set "CDP_READY=1"
    echo   %G%+%X% Chromium CDP ready
    goto :chromium_done
)
if %RETRIES% LSS 15 goto wait_cdp
echo   %Y%!%X% Chromium CDP not available

:chromium_done

:: ════════════════════════════════════════════════════════════════════════
:: 4) START Vite
:: ════════════════════════════════════════════════════════════════════════
echo   %D%~%X% Starting Vite...
start "STS Vite" /min /d "%CD%\frontend" cmd /c "npm run dev"

set "RETRIES=0"
:wait_vite
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
curl -s -o nul http://localhost:5174/ >nul 2>&1
if errorlevel 1 (
    if %RETRIES% LSS 30 goto wait_vite
    echo   %R%x%X% Vite did not start within 30 seconds.
    pause
    exit /b 1
)
echo   %G%+%X% Vite ready
echo.

:: ════════════════════════════════════════════════════════════════════════
:: 5) OPEN Pipeline tab in Chromium (Vite is now serving)
:: ════════════════════════════════════════════════════════════════════════
echo   %D%~%X% Opening pipeline in Chromium...
curl -s -o nul http://localhost:9222/json/version >nul 2>&1
if not errorlevel 1 (
    curl -s http://localhost:9222/json/list | findstr /i "localhost:5174" >nul 2>&1
    if errorlevel 1 (
        curl -s -o nul "http://localhost:9222/json/new?http://localhost:5174/#/pipeline"
        echo   %G%+%X% Pipeline tab opened
    ) else (
        echo   %G%+%X% Pipeline tab already open
    )
) else (
    echo   %Y%!%X% CDP not available - open http://localhost:5174/#/pipeline manually
)

:: ════════════════════════════════════════════════════════════════════════
:: 6) CHECK extension WebSocket connections
:: ════════════════════════════════════════════════════════════════════════
if "%CDP_READY%"=="1" (
    :: Give extensions a moment to connect to Flask WS
    timeout /t 3 /nobreak >nul
    echo   %D%~%X% Checking extension connections...
    curl -s http://127.0.0.1:5050/api/health >nul 2>&1
    echo   %G%+%X% Extensions ready
    echo   %D%    Gemini: ws://localhost:5050/ws/image-gemini%X%
    echo   %D%    Grok:   ws://localhost:5050/ws/animator-grok-video-grabber%X%
)

:: ── Status ────────────────────────────────────────────────────────────
echo.
echo   %D%----------------------------%X%
echo   %B%Flask%X%    %D%:%X%  http://localhost:5050  %D%(API)%X%
echo   %B%Vite%X%     %D%:%X%  http://localhost:5174  %D%(UI)%X%
echo   %B%Chromium%X% %D%:%X%  http://localhost:9222  %D%(CDP)%X%
echo   %D%----------------------------%X%
echo.
echo   %G%+%X% All services running. Press Ctrl+C to stop.
pause >nul
goto :eof

:: ── Subroutine: git pull ────────────────────────────────────────────────
:do_git_pull
ping -n 1 -w 1000 github.com >nul 2>&1
if errorlevel 1 (
    echo   %Y%!%X% No network - skipping git pull
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
