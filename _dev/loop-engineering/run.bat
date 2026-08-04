@echo off
:: Launcher for the loop-engineering orchestrator.
:: Usage examples:
::   run.bat --status
::   run.bat --phase 2
::   run.bat --until 3.3 --reviewer claude
::   run.bat --steps 1 --no-push
cd /d "%~dp0..\.."
venv\Scripts\python.exe "_dev\loop-engineering\loop_engineering.py" %*
