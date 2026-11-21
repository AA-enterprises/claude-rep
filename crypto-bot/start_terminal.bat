@echo off
REM Futures Terminal (paper): Asli + Freq + Big ek dashboard par. Bots ko alag se chalta rehne do.
REM Yahan se: Find Trades, leverage/margin chun kar trade lo, live chart, purani trades. Dashboard: http://127.0.0.1:8090
REM Paper budget (teeno bots ka milakar, haath wali trades): $2000
cd /d "%~dp0"
git pull
python main.py scalp-terminal --port 8090 --budget 2000
pause
