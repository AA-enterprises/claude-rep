@echo off
REM Futures Terminal (paper): fresh $2000 account, Asli/Freq/Big ke tareeqe alag sections mein. Chalte bots se bilkul alag.
REM Find Trades, leverage/margin chun kar trade lo, live chart, purani trades. Dashboard: http://127.0.0.1:8090
REM Paper budget (teeno sections ka milakar): $2000
cd /d "%~dp0"
git pull
python main.py scalp-terminal --port 8090 --budget 2000
pause
