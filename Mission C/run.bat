@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Please run setup.bat first. See README.md.
  exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0collect.py" %*
exit /b %errorlevel%
