@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Parlo is not installed yet. Double-click Setup.bat first.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app\main.py"
