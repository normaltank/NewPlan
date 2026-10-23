$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        uv venv .venv --python 3.12
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
    }
    uv pip sync --python .venv/Scripts/python.exe requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
} finally { Pop-Location }
