@echo off
REM Doosra (FREQ) paper bot: zyada trades (2 gates, 10 open, 0.2% risk). Alag files, dashboard: http://127.0.0.1:8060
REM Pehle wala start_bot.bat (validated bot) alag chalta rahe.
cd /d "%~dp0"
git pull
python main.py --scalp-config scalp_config_freq.json scalp-paper --state scalp_state_freq.json --trades scalp_trades_freq.csv --dashboard-port 8060
pause
