@echo off
setlocal

cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8765"

if not exist "%PYTHON%" (
    echo Python environment not found:
    echo   %PYTHON%
    echo Run setup.ps1 first.
    pause
    exit /b 1
)

rem Reuse the worker-enabled workbench if it is already running.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%URL%' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if "%ERRORLEVEL%"=="0" (
    start "" "%URL%"
    exit /b 0
)

start "OpenSource Workbench (workers)" powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-workbench.ps1"

rem Wait for the local web server before opening the page.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(45); do { try { $r = Invoke-WebRequest -Uri '%URL%' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { Start-Process '%URL%'; exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); Write-Error 'Workbench did not become ready within 45 seconds.'; exit 1"
if not "%ERRORLEVEL%"=="0" (
    echo Workbench startup failed. Check the server window for details.
    pause
    exit /b 1
)

endlocal
