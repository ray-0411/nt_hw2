@echo off
chcp 65001 >nul
title Game Watch
cd /d "%~dp0"

echo ===============================
echo  🎮 啟動 Game Watch 中...
echo ===============================
python -m game.game_watch 140.113.66.30 10000
pause