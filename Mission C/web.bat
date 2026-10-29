@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Please run setup.bat --web first.
  exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0web.py" --allow-live %*
