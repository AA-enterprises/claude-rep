@echo off
rem Windows launcher: works from PowerShell, Command Prompt or a double-click.
rem Uses npm.cmd/npx.cmd so PowerShell's script execution policy doesn't apply.

rem Re-run inside "cmd /k" so the window stays open and any error stays visible.
if not defined GLITCH_BOT_INNER (
  set "GLITCH_BOT_INNER=1"
  cmd /k call "%~f0" %*
  exit /b
)

setlocal EnableDelayedExpansion
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 goto :no_node

if exist "node_modules\playwright\package.json" goto :ready
echo Pehli dafa setup ho raha hai, thora intezar karein...
call npm.cmd install --no-audit --no-fund
if errorlevel 1 goto :install_failed
call npx.cmd playwright install chromium
if errorlevel 1 goto :install_failed

:ready
if not "%~1"=="" goto :with_args

echo.
set "URL="
set /p "URL=Website ka link likhein, jaise https://mysite.com : "
if "!URL!"=="" goto :no_url
echo.
echo Scan shuru ho raha hai: !URL!
echo.
node bot.js "!URL!"
goto :finished

:with_args
node bot.js %*

:finished
set "CODE=!ERRORLEVEL!"
echo.
if "!CODE!"=="3" echo Bot crash ho gaya. Upar wala error ka screenshot bhej dein.
if "!CODE!"=="2" echo Link ya option ghalat hai. Upar wala message dekhein.
if !CODE! LSS 2 if exist "glitch-report\report.html" (
  echo Report khul rahi hai: %CD%\glitch-report\report.html
  start "" "glitch-report\report.html"
)
goto :end

:no_node
echo Node.js nahi mila. https://nodejs.org se LTS version install karein,
echo phir yeh window band karke scan.cmd dobara chalayein.
goto :end

:install_failed
echo Setup fail ho gaya. Upar wala error ka screenshot bhej dein.
goto :end

:no_url
echo Koi link nahi diya. scan.cmd dobara chalayein.

:end
echo.
echo Kaam khatam. Yeh window band karne ke liye "exit" likhein ya X dabayein.
endlocal
