@echo off
:: Launch Ungoogled Chromium as dedicated STS automation browser
:: Auto-setup on first run: download, extract, prepare extensions
::
:: This script handles 3 things:
::   1. INSTALL - download/extract Chromium + Automa if missing
::   2. LAUNCH  - open Chromium if not already running (always with --load-extension)
::   3. VERIFY  - check extensions are loaded via CDP

setlocal enabledelayedexpansion

:: ── Resolve absolute paths (no ..\..\) ─────────────────────────────────
set "SCRIPT_DIR=%~dp0"
pushd "%~dp0..\..\.."
set "PROJECT_DIR=%CD%"
popd
set "CHROMIUM_DIR=%PROJECT_DIR%\bin\chromium"
set "BROWSER=%CHROMIUM_DIR%\ungoogled-chromium\chrome.exe"
set "PROFILE=%PROJECT_DIR%\data\chromium-profile"
set "GROK_EXT=%PROJECT_DIR%\_dev\automation\extensions\grok\STS-grok-sync"
set "GEMINI_EXT=%PROJECT_DIR%\_dev\automation\extensions\gemini\STS-gemini-sync"
set "RECORDER_EXT=%PROJECT_DIR%\_dev\automation\extensions\dom-activity-recorder"

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
if exist "%GROK_EXT%\manifest.json" (echo  [OK] Grok ready) else (echo  [!]  Grok missing)
if exist "%GEMINI_EXT%\manifest.json" (echo  [OK] Gemini ready) else (echo  [!]  Gemini missing)
if exist "%RECORDER_EXT%\manifest.json" (echo  [OK] DOM Recorder ready) else (echo  [!]  DOM Recorder missing)

:: -- Profile --
if not exist "%PROFILE%" mkdir "%PROFILE%"

:: ================================================================
:: STEP 2: LAUNCH (if not already running)
:: ================================================================

curl -s -o nul http://127.0.0.1:9222/json/version >nul 2>&1
if not errorlevel 1 (
  echo  [OK] Chromium already running on port 9222
  goto :verify
)

:: Build extension list
set "EXT_LIST="
if exist "%GROK_EXT%\manifest.json" set "EXT_LIST=%GROK_EXT%"
if exist "%GEMINI_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%GEMINI_EXT%") else (set "EXT_LIST=%GEMINI_EXT%")
)
if exist "%RECORDER_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%RECORDER_EXT%") else (set "EXT_LIST=%RECORDER_EXT%")
)

echo.
echo  Launching Chromium...

if defined EXT_LIST (
  start "" "%BROWSER%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run --disable-default-apps --window-position=100,100 --window-size=1400,900 --load-extension=%EXT_LIST% "http://localhost:5174/#/pipeline" "https://grok.com/imagine" "https://gemini.google.com/u/1/app?pageId=none"
) else (
  start "" "%BROWSER%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run --disable-default-apps --window-position=100,100 --window-size=1400,900 "http://localhost:5174/#/pipeline" "https://grok.com/imagine" "https://gemini.google.com/u/1/app?pageId=none"
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
:: STEP 3: VERIFY extensions via CDP
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
endlocal
exit /b 0
