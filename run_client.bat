@echo off
chcp 65001 >nul
title Lobby Client
cd /d "%~dp0"

echo ===========================================
echo   🎮 Lobby Client 啟動中...
echo   啟動時間：%date% %time%
echo ===========================================
echo.

python -m client.client_ui

echo.
echo 🛑 Client 已結束。
pause
