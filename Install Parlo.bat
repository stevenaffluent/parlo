@echo off
setlocal
rem Parlo installer: downloads the latest Parlo release from GitHub into %LOCALAPPDATA%\Parlo,
rem then runs Setup.bat there. Because the folder is a git clone, Parlo can update itself later.
rem ParloSetup.exe carries this file; it can also be run on its own from anywhere (Downloads is fine).
title Parlo installer
set "REPO=https://github.com/stevenaffluent/parlo.git"
set "DEST=%LOCALAPPDATA%\Parlo"

where git >nul 2>nul
if errorlevel 1 if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
where git >nul 2>nul
if errorlevel 1 (
  echo Parlo needs Git, a free tool it uses to download itself and its updates.
  choice /m "Install Git for Windows now"
  if errorlevel 2 goto nogit
  winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
  set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
  where git >nul 2>nul
  if errorlevel 1 goto nogit
)

if exist "%DEST%\.git" (
  echo Parlo is already in %DEST%. Getting the latest version...
  git -C "%DEST%" pull --ff-only origin stable
) else (
  echo Downloading Parlo to %DEST% ...
  git clone --branch stable "%REPO%" "%DEST%"
  if errorlevel 1 goto failed
)
call "%DEST%\Setup.bat"
exit /b 0

:nogit
echo.
echo Git is not installed, so Parlo can't be downloaded. Install it from https://git-scm.com/download/win
echo (the default options are fine), then run this file again.
pause
exit /b 1

:failed
echo.
echo Parlo could not be downloaded. Check that:
echo  - you are connected to the internet, and
echo  - nothing such as a firewall is blocking github.com.
echo Then run this file again.
pause
exit /b 1
