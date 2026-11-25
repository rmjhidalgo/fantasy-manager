@echo off
rem Fantasy Manager launcher: sets up on first run, then starts backend + frontend.
setlocal
cd /d "%~dp0"

rem --- Backend (Python) ---
if not exist "backend\.venv\Scripts\python.exe" (
    echo First run: setting up Python packages. This takes a minute...
    python -m venv backend\.venv || goto :fail
    backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt || goto :fail
)

rem --- Frontend (Node) ---
if not exist "frontend\node_modules" (
    echo First run: setting up the web interface. This takes a minute...
    pushd frontend
    call npm install --silent || (popd & goto :fail)
    popd
)

echo Starting Fantasy Manager...
start "Fantasy Manager - backend" /min cmd /c "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Fantasy Manager - frontend" /min cmd /c "cd /d frontend && npm run dev"

rem Give the servers a few seconds, then open the browser.
timeout /t 4 /nobreak >nul
start "" http://localhost:5173

echo.
echo Fantasy Manager is running at http://localhost:5173
echo To stop it, close the two minimized "Fantasy Manager" windows.
exit /b 0

:fail
echo.
echo Setup failed. Check that Python and Node.js are installed, then try again.
pause
exit /b 1
