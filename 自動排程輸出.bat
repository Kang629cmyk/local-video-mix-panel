@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo 使用 auto_schedule.txt 建立排程並輸出...
echo.

python scripts\auto_schedule.py auto_schedule.txt
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
    echo 執行失敗，請檢查上方訊息。
) else (
    echo 全部完成。
)
pause
exit /b %ERR%
