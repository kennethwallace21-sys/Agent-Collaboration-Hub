@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.10 or newer from https://www.python.org/downloads/ then try again.
  pause
  exit /b 1
)
py -3 install.py %*
pause
