@echo off
rem Installs Parlo into this folder (Python 3.11, libraries, the speech and AI models) and adds shortcuts.
rem Bypass applies to this one run only: a script unzipped from a download is otherwise blocked.
rem The graphical installer opens; if it cannot start, the same steps run in this console instead.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0installer.ps1"
if errorlevel 1 (
  echo The graphical installer could not start. Running setup in this window instead...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  echo.
  pause
)
