@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo            SHORTS BOT
echo ==============================================
echo.
set /p LINK="YouTube link paste karein (ya links.txt) aur Enter dabayein: "
if "%LINK%"=="" goto end
python bot.py "%LINK%"
:end
echo.
echo Shorts "output" folder mein hain.
pause
