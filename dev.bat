@echo off
setlocal
title ScriptToScene Studio [DEV]
cd /d "%~dp0"

echo.
echo   ScriptToScene Studio [DEV]
echo   ==========================
echo.

:: ── Git pull (must succeed before anything else) ─────────────────────────
call :do_git_pull
if errorlevel 1 (
    pause
    exit /b 1
)

:: ── Kill leftover dev processes ───────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5174 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Virtual environment ─────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo   [ERROR] Virtual environment not found.
    echo           Run setup.bat first.
    echo.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

:: ── Python dependency sync ────────────────────────────────────────────
set "STAMP=venv\.requirements_stamp"
set "REQS=requirements.txt"

if not exist "%STAMP%" (
    echo   Syncing Python dependencies...
    pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
    echo.
) else (
    fc /b "%REQS%" "%STAMP%" >nul 2>&1
    if errorlevel 1 (
        echo   Requirements changed — syncing Python dependencies...
        pip install -r "%REQS%" --quiet && copy /y "%REQS%" "%STAMP%" >nul
        echo.
    )
)

:: ── Frontend dependency sync ──────────────────────────────────────────
if not exist "frontend\node_modules" (
    echo   Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
    echo.
)

:: ── .env sanity check ─────────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        echo   [WARN] No .env file found. Copying .env.example to .env
        copy .env.example .env >nul
        echo           Edit .env with your API keys before using webhooks.
        echo.
    )
)

:: ── Launch Flask (background, minimized) ──────────────────────────────
echo   Starting Flask server...
set "STS_NO_BROWSER=1"
start "STS Flask" /min cmd /c "cd /d "%~dp0" && venv\Scripts\activate.bat && python app.py"

:: ── Wait for Flask to be ready ────────────────────────────────────────
echo   Waiting for Flask on :5050...
set "RETRIES=0"
:wait_flask
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',5050)" >nul 2>&1
if errorlevel 1 (
    if %RETRIES% LSS 30 goto wait_flask
    echo   [ERROR] Flask did not start within 30 seconds.
    pause
    exit /b 1
)
echo   Flask ready.
echo.

:: ── Launch Vite dev server (opens browser when ready) ─────────────────
echo   Flask  :  http://localhost:5050  (API, minimized)
echo   Vite   :  http://localhost:5174  (UI)
echo.
cd /d "%~dp0frontend"
npm run dev
goto :eof

:: ── Subroutine: git pull with validation ────────────────────────────────
:do_git_pull
ping -n 1 -w 1000 github.com >nul 2>&1
if errorlevel 1 (
    echo   [WARN] No network — skipping git pull
    echo.
    exit /b 0
)
if not exist "tmp" mkdir "tmp"
echo   [SYNC] git pull ...
git pull >"tmp\git_pull_out.txt" 2>&1
if errorlevel 1 goto :git_pull_failed
findstr /i /c:"CONFLICT" /c:"error:" /c:"fatal:" /c:"Cannot" /c:"refusing" /c:"Please commit" /c:"not possible" "tmp\git_pull_out.txt" >nul 2>&1
if not errorlevel 1 goto :git_pull_failed
echo   [SYNC] OK
type "tmp\git_pull_out.txt"
del "tmp\git_pull_out.txt" >nul 2>&1
echo.
exit /b 0
:git_pull_failed
echo.
echo   [ERROR] git pull failed:
echo.
type "tmp\git_pull_out.txt"
echo.
echo   Fix the issue above before starting the server.
echo   Common fixes:
echo     - Merge conflicts : resolve them, then git add + git commit
echo     - Uncommitted changes : git stash, then re-run this script
echo     - Diverged branches : git pull --rebase
echo.
del "tmp\git_pull_out.txt" >nul 2>&1
exit /b 1
