@echo off
chcp 65001 >nul
cd /d "%~dp0"
python bot.py --update --quiet
python bot.py --ask
pause
