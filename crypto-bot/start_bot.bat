@echo off
REM Ek double-click: bot + dashboard shuru. (Is file ko crypto-bot folder mein rehne do.)
cd /d "%~dp0"
echo Code update (agar internet ho)...
git pull
echo.
echo Bot shuru ho raha hai. Dashboard: http://127.0.0.1:8050
python main.py scalp-paper --open
echo.
echo Bot band ho gaya. Koi key dabao...
pause
