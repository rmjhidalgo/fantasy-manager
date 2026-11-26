# Builds the package for friends: release\FantasyManager-<version>.zip
#
# The zip holds everything needed to run the app on a Windows PC, with nothing to install:
#   Start Fantasy Manager.bat / Stop Fantasy Manager.bat / READ ME FIRST.txt
#   backend\app\      the app (no tests, no private test pages)
#   frontend\dist\    the built screens (served by the backend: no Node.js needed)
#   python\           a private copy of Python with the app's packages
#
# Nothing personal goes in: no data\, no saved Yahoo pages, no plan/status notes, no .claude\.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File tools\build_release.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content VERSION -Raw).Trim()
$name = "FantasyManager"
$staging = Join-Path $root "release\$name"
$zip = Join-Path $root "release\$name-$version.zip"
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "backend\.venv not found: run start.bat once first." }

Write-Host "Building Fantasy Manager $version"

# 1. Built screens
Push-Location frontend
npm run build | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
Pop-Location

# 2. Fresh staging folder
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force $staging | Out-Null

function Copy-Tree($from, $to, [string[]]$excludeDirs = @(), [string[]]$excludeFiles = @()) {
    $rc = @($from, $to, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($excludeDirs.Count) { $rc += "/XD"; $rc += $excludeDirs }
    if ($excludeFiles.Count) { $rc += "/XF"; $rc += $excludeFiles }
    & robocopy @rc | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copy failed: $from" }
}

# 3. The app (code only)
Copy-Tree "backend\app" "$staging\backend\app" @("__pycache__") @("*.pyc")
Copy-Tree "frontend\dist" "$staging\frontend\dist"
Copy-Item VERSION "$staging\VERSION"

# 4. Python: the base installation the app's virtual environment was made from, minus extras
$base = (& $venvPy -c "import sys; print(sys.base_prefix)").Trim()
Write-Host "Python from $base"
Copy-Tree $base "$staging\python" @("site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "Doc", "Scripts", "Tools", "tcl", "include", "libs", "__pycache__") @("*.pyc", "*.chm")
# The app's packages (without test tools and pip)
Copy-Tree (Join-Path $root "backend\.venv\Lib\site-packages") "$staging\python\Lib\site-packages" @("__pycache__", "tests", "pytest", "_pytest", "pytest-*", "pluggy", "pluggy-*", "iniconfig", "iniconfig-*", "pip", "pip-*") @("*.pyc", "py.py")

# 5. Launchers and the guide
Copy-Item "tools\release\Start Fantasy Manager.bat", "tools\release\Stop Fantasy Manager.bat", "tools\release\READ ME FIRST.txt" $staging

# 6. Privacy check: nothing personal may be in the package
$bad = Get-ChildItem -Recurse -File $staging | Where-Object {
    $rel = $_.FullName.Substring($staging.Length + 1)
    $_.Extension -in ".mhtml", ".mht", ".db", ".sqlite", ".sqlite3", ".env" -or
    $rel -match "^(data|Saved Pages|backups|\.claude|docs)\\" -or
    $rel -match "^backend\\(tests|\.venv)\\" -or
    $_.Name -in "PLAN.md", "STATUS.md", "yahoo_api_application.md"
}
if ($bad) { $bad | ForEach-Object { Write-Host "  PRIVATE: $($_.FullName)" }; throw "Private files found in the package" }

# 7. Smoke test: the bundled Python must load the whole app on its own (no PATH, no project venv)
$env:PATH = "$env:SystemRoot\system32;$env:SystemRoot"
& "$staging\python\python.exe" -c "import sys; sys.path.insert(0, r'$staging\backend'); import app.main, app.mcp_server; print('Self-test OK')"
if ($LASTEXITCODE -ne 0) { throw "The packaged app doesn't load" }

# 8. Zip
if (Test-Path $zip) { Remove-Item -Force $zip }
& tar.exe -a -c -f $zip -C (Join-Path $root "release") $name
if ($LASTEXITCODE -ne 0) { throw "Zip failed" }
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Done: $zip ($mb MB)"
