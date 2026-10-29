@echo off
setlocal
set "PYTHONUTF8=1"
if not defined MISSION_C_PYTHON set "MISSION_C_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%MISSION_C_PYTHON%" (
  echo Run setup.bat first. See README.md.
  exit /b 2
)
"%MISSION_C_PYTHON%" "%~dp0run.py" %*
exit /b %errorlevel%
