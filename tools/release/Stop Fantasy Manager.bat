@echo off
rem Stops Fantasy Manager (same as closing its minimized window).
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*uvicorn app.main:app*--port 8000*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Fantasy Manager has stopped.
timeout /t 2 /nobreak >nul
