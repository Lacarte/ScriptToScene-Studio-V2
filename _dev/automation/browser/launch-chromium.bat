@echo off
:: Launch Ungoogled Chromium as dedicated STS automation browser
:: Auto-setup on first run: download, extract, prepare extensions
::
:: This script handles 4 things:
::   1. INSTALL  - download/extract Chromium if missing
::   2. SERVERS  - start ai-web-auto WebSocket server (background)
::   3. LAUNCH   - open Chromium with all extensions loaded
::   4. VERIFY   - check extensions are loaded via CDP

setlocal enabledelayedexpansion

:: ── Resolve absolute paths ────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
pushd "%~dp0..\..\.."
set "PROJECT_DIR=%CD%"
popd
set "CHROMIUM_DIR=%PROJECT_DIR%\bin\chromium"
set "BROWSER=%CHROMIUM_DIR%\ungoogled-chromium\chrome.exe"
set "PROFILE=%PROJECT_DIR%\data\chromium-profile"

:: ── Extensions ────────────────────────────────────────────────────────
set "GROK_EXT=%PROJECT_DIR%\_dev\automation\extensions\grok\STS-grok-sync"
set "GEMINI_EXT=%PROJECT_DIR%\_dev\automation\extensions\gemini\STS-gemini-sync"
set "DEVTOOLS_EXT=%PROJECT_DIR%\_dev\automation\extensions\sts-devtools\STS-devtools-extension"
set "AWA_EXT=D:\@Workspace\@Development\@Projects\ai-web-auto\ai-web-auto-extension"
set "AWA_ROOT=D:\@Workspace\@Development\@Projects\ai-web-auto"

:: ── Read browser tab URLs from .env ───────────────────────────────────
set "TAB_GROK="
set "TAB_GEMINI="
set "TAB_PIPELINE="
if exist "%PROJECT_DIR%\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_DIR%\.env") do (
    if "%%A"=="BROWSER_TAB_GROK" set "TAB_GROK=%%B"
    if "%%A"=="BROWSER_TAB_GEMINI" set "TAB_GEMINI=%%B"
    if "%%A"=="BROWSER_TAB_PIPELINE" set "TAB_PIPELINE=%%B"
  )
)

:: Build tab list
set "TABS="
if defined TAB_PIPELINE set "TABS=!TAB_PIPELINE!"
if defined TAB_GROK (
  if defined TABS (set "TABS=!TABS! !TAB_GROK!") else (set "TABS=!TAB_GROK!")
)
if defined TAB_GEMINI (
  if defined TABS (set "TABS=!TABS! !TAB_GEMINI!") else (set "TABS=!TAB_GEMINI!")
)

echo.
echo  ============================================
echo   ScriptToScene - Automation Browser
echo  ============================================
echo.

:: ================================================================
:: STEP 1: INSTALL (only if something is missing)
:: ================================================================

if not exist "%CHROMIUM_DIR%" mkdir "%CHROMIUM_DIR%"

:: -- Chromium binary --
if exist "%BROWSER%" goto :chromium_ok

set BROWSER_ZIP=
for %%F in ("%CHROMIUM_DIR%\ungoogled-chromium*_windows_x64.zip") do set "BROWSER_ZIP=%%F"
if defined BROWSER_ZIP goto :extract_chromium

echo  [..] No Chromium found, fetching latest release...
for /f "delims=" %%U in ('powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $r=Invoke-RestMethod 'https://api.github.com/repos/ungoogled-software/ungoogled-chromium-windows/releases/latest'; ($r.assets | Where-Object {$_.name -match 'windows_x64\.zip$'} | Select-Object -First 1).browser_download_url"') do set "DOWNLOAD_URL=%%U"

if not defined DOWNLOAD_URL (
  echo  [X] Could not find latest release. Download manually:
  echo      https://github.com/ungoogled-software/ungoogled-chromium-windows/releases
  pause
  exit /b 1
)

for %%F in ("%DOWNLOAD_URL%") do set "ZIP_NAME=%%~nxF"
set "BROWSER_ZIP=%CHROMIUM_DIR%\%ZIP_NAME%"

echo  [..] Downloading %ZIP_NAME%...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%BROWSER_ZIP%'" 2>nul
if not exist "%BROWSER_ZIP%" (
  echo  [X] Download failed.
  pause
  exit /b 1
)
echo  [OK] Download complete

:extract_chromium
echo  [..] Extracting Chromium...
powershell -NoProfile -Command "Expand-Archive -Path '%BROWSER_ZIP%' -DestinationPath '%CHROMIUM_DIR%' -Force"
if exist "%BROWSER%" goto :chromium_ok
for /d %%D in ("%CHROMIUM_DIR%\ungoogled-chromium*") do (
  if exist "%%D\chrome.exe" if not "%%~nxD"=="ungoogled-chromium" ren "%%D" "ungoogled-chromium"
)
if not exist "%BROWSER%" (
  echo  [X] Extraction failed - chrome.exe not found
  pause
  exit /b 1
)

:chromium_ok
echo  [OK] Chromium installed

:: -- Extensions check --
if exist "%GROK_EXT%\manifest.json" (echo  [OK] Grok extension ready) else (echo  [!]  Grok extension missing)
if exist "%GEMINI_EXT%\manifest.json" (echo  [OK] Gemini extension ready) else (echo  [!]  Gemini extension missing)
if exist "%DEVTOOLS_EXT%\manifest.json" (echo  [OK] STS DevTools extension ready) else (echo  [!]  STS DevTools extension missing)
if exist "%AWA_EXT%\manifest.json" (echo  [OK] AI Web-Auto extension ready) else (echo  [!]  AI Web-Auto extension missing)

:: -- Profile --
if not exist "%PROFILE%" mkdir "%PROFILE%"

:: ================================================================
:: STEP 2: START SERVERS (background)
:: ================================================================

:: -- ai-web-auto WebSocket server --
:: Check if already running on port 8765
curl -s -o nul http://127.0.0.1:8765 >nul 2>&1
if not errorlevel 1 (
  echo  [OK] ai-web-auto server already running on :8765
  goto :awa_done
)

if exist "%AWA_ROOT%\venv\Scripts\python.exe" (
  echo  [..] Starting ai-web-auto server...
  start "AI-Web-Auto Server" /min cmd /c "cd /d "%AWA_ROOT%" && venv\Scripts\python -m ai_web_auto_backend.automation_controller"
  echo  [OK] ai-web-auto server starting on ws://localhost:8765
) else if exist "%AWA_ROOT%\requirements.txt" (
  echo  [!]  ai-web-auto venv missing — run: cd "%AWA_ROOT%" ^&^& python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
) else (
  echo  [!]  ai-web-auto project not found at %AWA_ROOT%
)
:awa_done

:: ================================================================
:: STEP 3: LAUNCH CHROMIUM (if not already running)
:: ================================================================

curl -s -o nul http://127.0.0.1:9222/json/version >nul 2>&1
if not errorlevel 1 (
  echo  [OK] Chromium already running on port 9222
  goto :verify
)

:: Build extension list — all available extensions
set "EXT_LIST="
if exist "%GROK_EXT%\manifest.json" set "EXT_LIST=%GROK_EXT%"
if exist "%GEMINI_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%GEMINI_EXT%") else (set "EXT_LIST=%GEMINI_EXT%")
)
if exist "%DEVTOOLS_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%DEVTOOLS_EXT%") else (set "EXT_LIST=%DEVTOOLS_EXT%")
)
if exist "%AWA_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%AWA_EXT%") else (set "EXT_LIST=%AWA_EXT%")
)

echo.
echo  Launching Chromium...

if defined EXT_LIST (
  start "" "%BROWSER%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run --disable-default-apps --window-position=100,100 --window-size=1400,900 --load-extension=%EXT_LIST% %TABS%
) else (
  start "" "%BROWSER%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run --disable-default-apps --window-position=100,100 --window-size=1400,900 %TABS%
)

:: Wait for CDP
set "RETRIES=0"
:wait_cdp
timeout /t 1 /nobreak >nul
set /a RETRIES+=1
curl -s -o nul http://127.0.0.1:9222/json/version >nul 2>&1
if not errorlevel 1 goto :cdp_ready
if %RETRIES% LSS 15 goto wait_cdp
echo  [X] Chromium did not start on port 9222
exit /b 1

:cdp_ready
echo  [OK] Chromium started - port 9222

:: ================================================================
:: STEP 4: VERIFY extensions via CDP
:: ================================================================
:verify

:: Give extensions a moment to initialize
timeout /t 2 /nobreak >nul

:: Check extensions via CDP tab list
curl -s http://127.0.0.1:9222/json/list | findstr /i "chrome-extension" >nul 2>&1
if not errorlevel 1 (
  echo  [OK] Extensions active in browser
) else (
  echo  [!]  No extensions detected - they may need a page reload to activate
)

echo.
echo  ============================================
echo   Extensions loaded:
echo     - Grok Sync
echo     - Gemini Sync
echo     - STS DevTools
echo     - AI Web-Auto (CDP automation)
echo   Servers:
echo     - ai-web-auto ws://localhost:8765
echo  ============================================
echo.
endlocal
exit /b 0
