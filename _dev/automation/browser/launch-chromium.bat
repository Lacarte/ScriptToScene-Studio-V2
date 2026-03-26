@echo off
:: Launch Ungoogled Chromium as dedicated STS automation browser
:: Auto-setup on first run: download, extract, install extensions

setlocal enabledelayedexpansion

:: Paths: script is in _dev/automation/browser/, chromium lives in bin/chromium/
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%~dp0..\..\..
set CHROMIUM_DIR=%PROJECT_DIR%\bin\chromium
set BROWSER=%CHROMIUM_DIR%\ungoogled-chromium\chrome.exe
set PROFILE=%PROJECT_DIR%\data\chromium-profile
set AUTOMA_CRX=%SCRIPT_DIR%Automa-Chrome-Web-Store.crx
set AUTOMA_EXT=%CHROMIUM_DIR%\automa-unpacked
set GROK_EXT=%PROJECT_DIR%\_dev\automation\extensions\grok\STS-grok-automation
set GEMINI_EXT=%PROJECT_DIR%\_dev\automation\extensions\gemini\sts-gemini

echo.
echo  ============================================
echo   ScriptToScene - Automation Browser
echo  ============================================
echo.

:: ==========================================================
:: SETUP: Only runs if something is missing
:: ==========================================================

:: -- Ensure chromium dir exists --
if not exist "%CHROMIUM_DIR%" mkdir "%CHROMIUM_DIR%"

:: -- Chromium zip --
if exist "%BROWSER%" goto :chromium_ok

set BROWSER_ZIP=
for %%F in ("%CHROMIUM_DIR%\ungoogled-chromium*_windows_x64.zip") do set "BROWSER_ZIP=%%F"

if defined BROWSER_ZIP goto :extract_chromium

echo  [..] No Chromium found, fetching latest release...
for /f "delims=" %%U in ('powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $r=Invoke-RestMethod 'https://api.github.com/repos/ungoogled-software/ungoogled-chromium-windows/releases/latest'; $a=$r.assets | Where-Object {$_.name -match 'windows_x64\.zip$'} | Select-Object -First 1; Write-Output $a.browser_download_url}"') do set "DOWNLOAD_URL=%%U"

if not defined DOWNLOAD_URL (
  echo  [X] Could not find latest release. Download manually:
  echo      https://github.com/ungoogled-software/ungoogled-chromium-windows/releases
  echo      Place the windows_x64.zip in: %CHROMIUM_DIR%\
  pause
  exit /b 1
)

for %%F in ("%DOWNLOAD_URL%") do set "ZIP_NAME=%%~nxF"
set "BROWSER_ZIP=%CHROMIUM_DIR%\%ZIP_NAME%"

echo  [..] Downloading %ZIP_NAME%...
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%BROWSER_ZIP%'}" 2>nul
if not exist "%BROWSER_ZIP%" (
  echo  [X] Download failed. Download manually:
  echo      https://github.com/ungoogled-software/ungoogled-chromium-windows/releases
  pause
  exit /b 1
)
echo  [OK] Download complete

:extract_chromium
echo  [..] Extracting Chromium...
powershell -Command "Expand-Archive -Path '%BROWSER_ZIP%' -DestinationPath '%CHROMIUM_DIR%\' -Force"
if exist "%BROWSER%" goto :chromium_ok
:: Zip may extract to a versioned subfolder - rename it
for /d %%D in ("%CHROMIUM_DIR%\ungoogled-chromium*") do (
  if exist "%%D\chrome.exe" (
    if not "%%~nxD"=="ungoogled-chromium" (
      ren "%%D" "ungoogled-chromium"
    )
  )
)
if not exist "%BROWSER%" (
  echo  [X] Extraction failed - chrome.exe not found
  pause
  exit /b 1
)

:chromium_ok
echo  [OK] Chromium ready

:: -- Automa extension --
if exist "%AUTOMA_EXT%\manifest.json" (
  echo  [OK] Automa ready
  goto :automa_ok
)
if not exist "%AUTOMA_CRX%" (
  echo  [!]  Automa .crx not found - place it in: %CHROMIUM_DIR%\
  goto :automa_ok
)
echo  [..] Extracting Automa .crx...
if not exist "%AUTOMA_EXT%" mkdir "%AUTOMA_EXT%"
:: CRX3: strip header (magic 4B + version 4B + header_len 4B + header) then unzip
powershell -Command "& {$b=[System.IO.File]::ReadAllBytes('%AUTOMA_CRX%');$hl=[BitConverter]::ToUInt32($b,8);$zs=12+$hl;$zb=New-Object byte[] ($b.Length-$zs);[Array]::Copy($b,$zs,$zb,0,$zb.Length);[System.IO.File]::WriteAllBytes('%AUTOMA_EXT%\_automa.zip',$zb)}"
powershell -Command "Expand-Archive -Path '%AUTOMA_EXT%\_automa.zip' -DestinationPath '%AUTOMA_EXT%' -Force"
del "%AUTOMA_EXT%\_automa.zip" 2>nul
if exist "%AUTOMA_EXT%\manifest.json" (
  echo  [OK] Automa extracted
) else (
  echo  [!]  Automa extraction failed
)

:automa_ok
:: -- Grok + Gemini extensions --
if exist "%GROK_EXT%\manifest.json" (echo  [OK] Grok ready) else (echo  [!]  Grok extension not found)
if exist "%GEMINI_EXT%\manifest.json" (echo  [OK] Gemini ready) else (echo  [!]  Gemini extension not found)

:: -- Profile --
if not exist "%PROFILE%" mkdir "%PROFILE%"

:: ==========================================================
:: LAUNCH
:: ==========================================================

:: Only use --load-extension on first run to register them in the profile.
:: After that, Chromium remembers them and we skip it to avoid re-install popups.
set EXT_FLAG_FILE=%PROFILE%\.extensions-loaded

if exist "%EXT_FLAG_FILE%" goto :launch_normal

:: First run: load extensions into profile
set EXT_LIST=
if exist "%AUTOMA_EXT%\manifest.json" set "EXT_LIST=%AUTOMA_EXT%"
if exist "%GROK_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%GROK_EXT%") else (set "EXT_LIST=%GROK_EXT%")
)
if exist "%GEMINI_EXT%\manifest.json" (
  if defined EXT_LIST (set "EXT_LIST=!EXT_LIST!,%GEMINI_EXT%") else (set "EXT_LIST=%GEMINI_EXT%")
)

echo.
echo  First launch - registering extensions...
echo.

start "" "%BROWSER%" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%PROFILE%" ^
  --no-first-run ^
  --disable-default-apps ^
  --window-position=100,100 ^
  --window-size=1400,900 ^
  --load-extension="%EXT_LIST%" ^
  "https://grok.com/imagine" ^
  "https://gemini.google.com/app"

echo done> "%EXT_FLAG_FILE%"
goto :launched

:launch_normal
echo.
echo  Launching...
echo.

start "" "%BROWSER%" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%PROFILE%" ^
  --no-first-run ^
  --disable-default-apps ^
  --window-position=100,100 ^
  --window-size=1400,900 ^
  "https://grok.com/imagine" ^
  "https://gemini.google.com/app"

:launched

echo  [OK] Chromium started - port 9222
echo  [OK] Tabs: Pipeline, Grok, Gemini
echo.

endlocal
