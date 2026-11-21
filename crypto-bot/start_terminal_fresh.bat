@echo off
REM Terminal ko PURA FRESH karke chalao: purani terminal trades/state/auto archive/ folder mein chali jati hain,
REM naya $2000 paper account, Auto sab OFF. (Bots ko kuch nahi hota.) Sirf jab naye sire se shuru karna ho.
cd /d "%~dp0"
git pull
python main.py scalp-terminal --port 8090 --budget 2000 --fresh
pause
