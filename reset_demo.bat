@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reset_demo.ps1"
if errorlevel 1 (
  echo.
  echo Demo reset failed. See the message above.
)
pause
endlocal
