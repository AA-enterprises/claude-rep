@echo off
REM EXPERIMENT (paper): max 2 ghante ki hold, ~2-3 trades/ghanta, 2x leverage. Backtest mein har variant loss mein tha (~ -$700/hafta).
REM Trade open/close alerts ON (filter ke baad trades kam), 6 ghante ki report, Discord /positions command (DISCORD_BOT_TOKEN .env mein). Dashboard: http://127.0.0.1:8080
cd /d "%~dp0"
git pull
python main.py --scalp-config scalp_config_1h.json scalp-paper --state scalp_state_1h.json --trades scalp_trades_1h.csv --dashboard-port 8080
pause
