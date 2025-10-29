@echo off
chcp 65001 >nul
title Lobby Client
cd /d "%~dp0"

python -m client.client_ui

echo.
echo 🛑 Client 已結束。
pause
