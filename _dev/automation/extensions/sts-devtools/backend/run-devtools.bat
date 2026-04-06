@echo off
title STS - DevTools Backend
:: Run STS DevTools from the ScriptToScene-Studio project
cd /d "%~dp0..\..\..\..\.."
if exist "venv\Scripts\python.exe" (
  venv\Scripts\python _dev\automation\extensions\sts-devtools\backend\sts_devtools.py %*
) else (
  python _dev\automation\extensions\sts-devtools\backend\sts_devtools.py %*
)
