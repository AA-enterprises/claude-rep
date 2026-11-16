@echo off
REM Teesra (BIG) paper bot: kam trades (sab 4 gates), badi position (~$1,000-1,500, 3x), risk 0.6%. Dashboard: http://127.0.0.1:8070
REM Validated bot (start_bot.bat, port 8050) aur FREQ bot (port 8060) alag chalte rahein.
cd /d "%~dp0"
git pull
python main.py --scalp-config scalp_config_big.json scalp-paper --state scalp_state_big.json --trades scalp_trades_big.csv --dashboard-port 8070
pause
