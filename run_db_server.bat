@echo off
chcp 65001 >nul
title DB Server
cd /d "%~dp0"

echo 啟動資料庫伺服器中...
python -m database.db_server
echo.
pause
