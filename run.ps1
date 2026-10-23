param([ValidateSet('replay', 'live')][string]$Mode = 'replay')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .venv/Scripts/python.exe benchmark.py $Mode
    if ($LASTEXITCODE -ne 0) { throw 'Experiment failed; inspect its run directory' }
} finally { Pop-Location }
