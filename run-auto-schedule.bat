@echo off
setlocal
cd /d "%~dp0"

echo Building schedule from auto_schedule.txt...
echo.

python "scripts\auto_schedule.py" "auto_schedule.txt"
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
    echo Failed. Please check the messages above.
) else (
    echo Done.
)
pause
exit /b %ERR%
