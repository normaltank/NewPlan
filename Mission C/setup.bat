@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  py -3 -m venv "%~dp0.venv"
  if errorlevel 1 exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 exit /b 2
if /i "%~1"=="--full" (
  "%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements-browser.txt" -r "%~dp0requirements-ocr.txt"
  if errorlevel 1 exit /b 2
)
echo Mission C is ready. Run replay.bat for the offline combination demo.
echo Run run.bat --help for individual collection options.
