@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python -B bootstrap.py
) else (
    py -3 -B bootstrap.py
)
if errorlevel 1 (
    echo Startup failed. See README.md. Python 3.11+ is required.
    pause
)
