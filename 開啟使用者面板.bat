@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0scripts\panel_app.py"
  timeout /t 2 /nobreak >nul
  start "" http://127.0.0.1:5010
  exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
  start "" py -3 "%~dp0scripts\panel_app.py"
  timeout /t 2 /nobreak >nul
  start "" http://127.0.0.1:5010
  exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
  start "" python "%~dp0scripts\panel_app.py"
  timeout /t 2 /nobreak >nul
  start "" http://127.0.0.1:5010
  exit /b 0
)

echo Unable to launch panel. Please run scripts\panel_app.py directly.
pause
exit /b 1
