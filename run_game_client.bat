@echo off
chcp 65001 >nul
title Game Client
cd /d "%~dp0"

echo ===============================
echo  🕹️ 啟動 Game Client 中...
echo ===============================
python -m game.client_game
pause
