@echo off
rem Fantasy Manager: starts the app and opens it in your browser.
setlocal
cd /d "%~dp0"

rem Your league data lives in your user profile, so a new version of the app keeps it.
set "FM_DATA_DIR=%LOCALAPPDATA%\Fantasy Manager"

rem Already running? Then just open it.
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto open

echo Starting Fantasy Manager...
start "Fantasy Manager - close this window to stop the app" /min "%~dp0python\python.exe" -m uvicorn app.main:app --app-dir "%~dp0backend" --host 127.0.0.1 --port 8000

rem Wait until it answers (the very first start can take up to a minute).
powershell -NoProfile -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Fantasy Manager didn't start. Open the minimized "Fantasy Manager" window to see why,
    echo or send a screenshot of it to the person who gave you the app.
    pause
    exit /b 1
)

:open
start "" http://localhost:8000
exit /b 0
