@echo off
chcp 65001 >nul
title Lobby Server
cd /d "%~dp0"

echo ===========================================
echo   🌐 Central Lobby Server 啟動中...
echo   啟動時間：%date% %time%
echo ===========================================
echo.

REM 以模組模式啟動，確保可找到 common、database 套件
python -m lobby.lobby_server

echo.
echo 🛑 伺服器已關閉。
pause
