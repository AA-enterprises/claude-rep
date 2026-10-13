@echo off
setlocal
rem Windows launcher: works from PowerShell, Command Prompt or a double-click.
rem Uses npm.cmd/npx.cmd so PowerShell's "running scripts is disabled" block doesn't apply.
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js nahi mila. Pehle https://nodejs.org se LTS version install karein,
  echo phir PowerShell band karke dobara kholein.
  pause
  exit /b 2
)

if not exist "node_modules\playwright" (
  echo Pehli dafa setup ho raha hai, thora intezar karein...
  call npm.cmd install --no-audit --no-fund
  if errorlevel 1 ( echo npm install fail ho gaya. & pause & exit /b 2 )
  call npx.cmd playwright install chromium
  if errorlevel 1 ( echo Chromium download fail ho gaya. & pause & exit /b 2 )
)

set "URL=%~1"
if "%URL%"=="" set /p "URL=Website ka link likhein (jaise https://mysite.com): "
if "%URL%"=="" ( echo Koi link nahi diya. & pause & exit /b 2 )

if "%~1"=="" (
  node bot.js "%URL%"
) else (
  node bot.js %*
)
set "CODE=%ERRORLEVEL%"

if exist "glitch-report\report.html" start "" "glitch-report\report.html"
if "%~1"=="" pause
exit /b %CODE%
