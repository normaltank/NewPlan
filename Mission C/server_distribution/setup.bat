@echo off
setlocal
set "PYTHONUTF8=1"
if not exist "%~dp0.venv\Scripts\python.exe" (
  if defined MISSION_C_PYTHON (
    "%MISSION_C_PYTHON%" -m venv "%~dp0.venv"
  ) else (
    py -3 -m venv "%~dp0.venv"
  )
  if errorlevel 1 exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 exit /b 2
if not exist "%~dp0input" mkdir "%~dp0input"
echo Ready. Run start.bat demo, then start.bat preview or start.bat watch. See README.md.
