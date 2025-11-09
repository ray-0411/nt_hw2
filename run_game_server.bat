@echo off
chcp 65001 >nul
title Game Server
cd /d "%~dp0"

echo ===============================
echo  🎮 啟動 Game Server 中...
echo ===============================
python -m game.game_server 10000
pause
